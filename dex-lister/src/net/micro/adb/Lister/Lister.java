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
    static {
        // Workarounds.init();
        // System.out.println("Hello from Lister");
        
        // Cannot load system libraries (thanks Android)
        // Unless... https://fadeevab.com/accessing-system-private-api-through-namespace/
        
        // System.loadLibrary("android");
        // System.loadLibrary("android_runtime");
        // System.loadLibrary("binder");
        
        // NOTE: MUST run the app with  app_process  command
        // ~~(commented because loop is prepared in Workarounds.java)~~
        Looper.prepareMainLooper();
    }
    
    private Lister() {
        // not instantiable
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
        
        // get version code
        Long vcode = null;
        if (is_inst) {
            try {
                final PackageInfo pInfo = pm.getPackageInfo(app.packageName, PackageManager.GET_META_DATA);
                if (android.os.Build.VERSION.SDK_INT >= Build.VERSION_CODES.P)
                    vcode = pInfo.getLongVersionCode();
                else
                    vcode = (long)pInfo.versionCode;
            } catch (Exception e) {}
        }
        json.name("vcode").value(vcode);
        
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
    
    public static void main(String[] args) throws Exception {
        // System.out.println("Hello from main");
        
        // Context ctx = Workarounds.getSystemContext();
        Context ctx = ActivityThread.systemMain().getSystemContext();
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
}
