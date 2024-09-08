package net.micro.adb.Lister;

import java.io.*;
import java.util.List;
import java.security.cert.*;
import java.security.MessageDigest;
import java.lang.reflect.*;
// import org.json.*;

import android.app.*;
import android.content.Context;
import android.content.Intent;
import android.content.pm.*;
import android.os.*;

import com.google.gson.stream.JsonWriter;


@SuppressWarnings("deprecation")
public final class Lister {
    public static final String SELF;

    static {
        SELF = System.getProperty("java.class.path").split(File.pathSeparator)[0];
        // Workarounds.init();
        // System.out.println("Hello from Lister");
        
        // Cannot load system libraries (thanks Android)
        // Unless... https://fadeevab.com/accessing-system-private-api-through-namespace/
        
        // System.loadLibrary("android");
        // System.loadLibrary("android_runtime");
        // System.loadLibrary("binder");
    }
    
    public static void main(String[] args) throws Exception {
        delete_self();
        // experiment(args); return;
        // System.out.println("Hello from main");

        new Lister().run();

        // By default, the Java process exits when all non-daemon threads are terminated.
        // The Android SDK might start some non-daemon threads internally, preventing the program to exit.
        // So force the process to exit explicitly.
        System.exit(0);
    }
    
    static void delete_self() throws Exception {
        if (SELF.startsWith("/data/local/tmp") && SELF.endsWith(".jar")) {
            // keep device clean
            new File(SELF).delete();
        }
    }
    
    static void experiment(String[] args) throws Exception {
        Looper.prepareMainLooper();
        // Looper.prepare();
        // Handler h = new Handler();
        // Looper.loop();
        
        // Context ctx = Workarounds.getSystemContext();
        ActivityThread thr = ActivityThread.systemMain();
        Context ctx = thr.getSystemUiContext();
        PackageManager pm = ctx.getPackageManager();
        
        String pkg = "org.fdroid.fdroid";
        String apk = String.format("/data/app/%s-MPnyVgMbHQ_n0hKMy_AF4Q==/base.apk", pkg);
        Context ctx2 = ctx.createPackageContext(pkg, Context.CONTEXT_IGNORE_SECURITY | Context.CONTEXT_INCLUDE_CODE);

        ApplicationInfo info = pm.getApplicationInfo(pkg, PackageManager.GET_SHARED_LIBRARY_FILES);
        PackageInfo pinfo = pm.getPackageInfo(pkg, PackageManager.GET_ACTIVITIES);
        thr.installSystemApplicationInfo(info, Lister.class.getClassLoader());
        System.setProperty("java.class.path", apk);
        // Thread thread = new Thread(new Runnable() {
        //     public void run() {
        //         ActivityThread.main(args);
        //     }
        // });
        // thread.start();

        // find main activity
        ActivityInfo[] activities = pinfo.activities;

        for (ActivityInfo activityInfo : activities) {
            Intent intent = new Intent(Intent.ACTION_MAIN);
            intent.addCategory(Intent.CATEGORY_LAUNCHER);
            intent.setClassName(pkg, activityInfo.name);
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);

            // Check if this activity can handle the intent
            if (intent.resolveActivity(pm) != null) {
                ctx2.startActivity(intent);
                return;
            }
        }
    }
    

    private ActivityThread thr;
    private Context ctx;
    private PackageManager pm;
    private JsonWriter jw;

    private Lister() {
        // NOTE: MUST run the app with  app_process  command
        // (comment if you use Workarounds.java)
        Looper.prepareMainLooper();
        
        // Context ctx = Workarounds.getSystemContext();
        thr = ActivityThread.systemMain();
        ctx = thr.getSystemContext();
        pm = ctx.getPackageManager();
    }

    void run() throws Exception {
        // build json & print to stdout, buffered
        FileOutputStream fout = new FileOutputStream(java.io.FileDescriptor.out);
        // PrintWriter buff = new PrintWriter(new BufferedWriter(new OutputStreamWriter(fout, "UTF-8"), 4096));
        try (
            // BufferedOutputStream buff = new BufferedOutputStream(new DataOutputStream(fout), 4096);
            BufferedWriter buff = new BufferedWriter(new OutputStreamWriter(fout, "UTF-8"), 4096);
            JsonWriter _jw = new JsonWriter(buff);
        ) {
            jw = _jw;
            jw.setIndent("  ");
            jw.setSerializeNulls(true);

            jw.beginObject();
            jw.name("device"); print_device_json();
            jw.name("apps"); print_apps_json();
            jw.endObject();
            
            buff.flush();
            jw = null;
        }
    }

    void print_device_json() throws Exception {
        jw.beginObject();
        jw.name("arch").value(System.getProperty("os.arch"));
        // jw.name("abi").value(Build.CPU_ABI);
        
        // jw.name("all_abi"); jw.beginArray();
        // for (String s : Build.SUPPORTED_ABIS) { jw.value(s); }
        // jw.endArray();

        jw.name("build"); consts2json(Build.class);
        jw.endObject();
    }

    void any2json(Object v) throws Exception {
        if (v == null) {
            jw.nullValue();
            return;
        }

        Class<?> vc = v.getClass();
        if (v instanceof String)        jw.value((String)v);
        else if (v instanceof Number)   jw.value((Number)v);
        else if (v instanceof Boolean)  jw.value((Boolean)v);
        else if (vc.isArray())          array2json(v);
        else if (vc.isMemberClass())    consts2json(vc);
        else                            obj2json(v);
    }

    void array2json(Object a) throws Exception {
        jw.beginArray();
        int length = Array.getLength(a);
        for (int i = 0; i < length; i ++) {
            Object av = Array.get(a, i);
            any2json(av);
        }
        jw.endArray();
    }

    void obj2json(Object o) throws Exception {
        jw.beginObject();
        for (Field f : o.getClass().getDeclaredFields()) {
            f.setAccessible(true);
            Object v = null;
            try { v = f.get(o); } catch (Throwable ex) {}
            jw.name(f.getName()); any2json(v);
        }
        jw.endObject();
    }

    void consts2json(Class<?> cls) throws Exception {
        jw.beginObject();
        for (Field f : cls.getDeclaredFields()) {
            f.setAccessible(true);
            Object v = null;
            try { v = f.get(null); } catch (Throwable ex) {}
            jw.name(f.getName()); any2json(v);
        }
        for (Class<?> c : cls.getDeclaredClasses()) {
            String[] cname = c.getSimpleName().split("\\$");
            jw.name(cname[cname.length - 1]); consts2json(c);
        }
        jw.endObject();
    }
    
    void print_apps_json() throws Exception {
        // get packages
        int flags = PackageManager.MATCH_UNINSTALLED_PACKAGES;
        List<ApplicationInfo> apps = pm.getInstalledApplications(flags);
        
        // jw.beginArray();
        jw.beginObject();
        for (ApplicationInfo appInfo : apps) {
            app2json(appInfo);
        }
        // jw.endArray();
        jw.endObject();
    }
    
    void app2json(ApplicationInfo app) throws Exception {
        int sys = ApplicationInfo.FLAG_SYSTEM;
        int inst = ApplicationInfo.FLAG_INSTALLED;
        
        boolean is_inst = (app.flags & inst) == inst;
        
        jw.name(app.packageName);
        jw.beginObject();
        jw.name("uid").value(app.uid);
        jw.name("pkg").value(app.packageName);
        jw.name("removed").value(!is_inst);
        jw.name("system").value((app.flags & sys) == sys);
        jw.name("label").value(pm.getApplicationLabel(app).toString());
        
        // get version and signature sha256
        Long vcode = null;
        String vname = null;
        String signer = null;
        if (is_inst) {
            PackageInfo pInfo = null;
            try {
                pInfo = pm.getPackageInfo(app.packageName, PackageManager.GET_META_DATA | PackageManager.GET_SIGNATURES);
                if (android.os.Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    vcode = pInfo.getLongVersionCode();
                } else {
                    vcode = (long)pInfo.versionCode;
                }
                vname = pInfo.versionName;
            } catch (Exception e) {}

            if (pInfo != null)
                signer = pkg2signer(pInfo);
        }
        jw.name("vcode").value(vcode);
        jw.name("vname").value(vname);
        jw.name("signer").value(signer);
        
        // get installer package
        String instInfo = null;
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) 
                instInfo = pm.getInstallSourceInfo(app.packageName).getInstallingPackageName();
            else
                instInfo = pm.getInstallerPackageName(app.packageName);
        } catch (Exception e) {}
        jw.name("installer").value(instInfo);
        
        jw.endObject();
    }

    String pkg2signer(PackageInfo pInfo) throws Exception {
        // APKs can have multiple signatures, just get the first
        Signature[] sigs = pInfo.signatures;
        if (sigs == null)
            return "";
        
        for (Signature sig : sigs) {
            final byte[] rawCert = sig.toByteArray();
            MessageDigest md = MessageDigest.getInstance("SHA256");
            md.update(rawCert);
            final byte[] rawsha = md.digest();

            StringBuilder sb = new StringBuilder();
            for (byte b : rawsha) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
            
            // InputStream certStream = new ByteArrayInputStream(rawCert);
            // try {
            //     CertificateFactory certFactory = CertificateFactory.getInstance("X509");
            //     X509Certificate x509Cert = (X509Certificate) certFactory.generateCertificate(certStream);
            //     sb.append("Certificate subject: " + x509Cert.getSubjectDN() + "<br>");
            //     sb.append("Certificate issuer: " + x509Cert.getIssuerDN() + "<br>");
            //     sb.append("Certificate serial number: " + x509Cert.getSerialNumber() + "<br>");
            //     sb.append("<br>");
            // } catch (CertificateException e) {
            //     // e.printStackTrace();
            // }
        }
        return "";
    }
}
