package net.micro.adb.Lister;

import java.io.*;
import java.util.List;
// import org.json.*;

import android.app.*;
import android.content.Context;
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
    
    private Lister() {
        // not instantiable
    }
    
    public static void delete_self() throws Exception {
        if (SELF.startsWith("/data/local/tmp") && SELF.endsWith(".jar")) {
            // keep phone clean
            new File(SELF).delete();
        }
    }
    
    public static void app2json(PackageManager pm, ApplicationInfo app, JsonWriter json) throws IOException {
        int sys = ApplicationInfo.FLAG_SYSTEM;
        int inst = ApplicationInfo.FLAG_INSTALLED;
        
        boolean is_inst = (app.flags & inst) == inst;
        
        json.beginObject();
        json.name("uid").value(app.uid);
        json.name("pkg").value(app.packageName);
        json.name("removed").value(!is_inst);
        json.name("system").value((app.flags & sys) == sys);
        json.name("label").value(pm.getApplicationLabel(app).toString());
        
        // get version
        Long vcode = null;
        String vname = null;
        if (is_inst) {
            try {
                final PackageInfo pInfo = pm.getPackageInfo(app.packageName, PackageManager.GET_META_DATA);
                if (android.os.Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    vcode = pInfo.getLongVersionCode();
                } else {
                    vcode = (long)pInfo.versionCode;
                }
                vname = pInfo.versionName;
            } catch (Exception e) {}
        }
        json.name("vcode").value(vcode);
        json.name("vname").value(vname);
        
        // get installer package
        String instInfo = null;
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) 
                instInfo = pm.getInstallSourceInfo(app.packageName).getInstallingPackageName();
            else
                instInfo = pm.getInstallerPackageName(app.packageName);
        } catch (Exception e) {}
        json.name("installer").value(instInfo);
        
        json.endObject();
    }
    
    public static void print_apps_json() throws Exception {
        // NOTE: MUST run the app with  app_process  command
        // (comment if you use Workarounds.java)
        Looper.prepareMainLooper();
        
        // Context ctx = Workarounds.getSystemContext();
        ActivityThread thr = ActivityThread.systemMain();
        Context ctx = thr.getSystemContext();
        PackageManager pm = ctx.getPackageManager();
        
        // get packages
        int flags = PackageManager.MATCH_UNINSTALLED_PACKAGES;
        List<ApplicationInfo> apps = pm.getInstalledApplications(flags);
        
        // build json & print to stdout, buffered
        FileOutputStream fout = new FileOutputStream(java.io.FileDescriptor.out);
        // PrintWriter buff = new PrintWriter(new BufferedWriter(new OutputStreamWriter(fout, "UTF-8"), 4096));
        try (
            // BufferedOutputStream buff = new BufferedOutputStream(new DataOutputStream(fout), 4096);
            BufferedWriter buff = new BufferedWriter(new OutputStreamWriter(fout, "UTF-8"), 4096);
            JsonWriter jw = new JsonWriter(buff);
        ) {
            jw.setIndent("  ");
            jw.setSerializeNulls(true);
            jw.beginArray();
            for (ApplicationInfo appInfo : apps) {
                app2json(pm, appInfo, jw);
            }
            jw.endArray();
            buff.flush();
        }
        
        // By default, the Java process exits when all non-daemon threads are terminated.
        // The Android SDK might start some non-daemon threads internally, preventing the program to exit.
        // So force the process to exit explicitly.
        System.exit(0);
    }
    
    public static void experiment(String[] args) throws Exception {
        Looper.prepare();
        Handler h = new Handler();
        Looper.loop();
        
        // Context ctx = Workarounds.getSystemContext();
        ActivityThread thr = ActivityThread.systemMain();
        Context ctx = thr.getSystemContext();
        PackageManager pm = ctx.getPackageManager();
        
        ApplicationInfo info = pm.getApplicationInfo("org.fdroid.fdroid", PackageManager.GET_SHARED_LIBRARY_FILES);
        thr.installSystemApplicationInfo(info, Lister.class.getClassLoader());
        System.setProperty("java.class.path", "/data/app/org.fdroid.fdroid-MPnyVgMbHQ_n0hKMy_AF4Q==/base.apk");
        Thread thread = new Thread(new Runnable() {
            public void run() {
                ActivityThread.main(args);
            }
        });
        thread.start();
    }
    
    public static void main(String[] args) throws Exception {
        delete_self();
        // System.out.println("Hello from main");
        print_apps_json();
    }
}
