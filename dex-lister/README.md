# Lister

Helper to retrieve device information through adb.

This is a fake APK — a simple JAR with dexed classes and empty manifest, launched with the following procedure:

```nginx
adb push  lister.jar  /data/local/tmp
adb exec-out "
    export CLASSPATH=/data/local/tmp/lister.jar
    app_process / net.micro.adb.Lister.Lister
"
```

## Background

At the time of writing, Android has no ADB tool to retrieve a list of packages with their respective labels (not in the user locale nor english). However, such information is provided through some Java API and hidden methods.

## Dependencies

<details open><summary><b>Development</b></summary>

| Name                  | ≥ Version | Notes                                                                                    |
| --------------------- | --------- | ---------------------------------------------------------------------------------------- |
| Android SDK           | 34        |                                                                                          |
| Android framework jar |           | must be taken from an android image, then [de-dexed](https://github.com/pxb1988/dex2jar) |
| Java JDK              | 8         |                                                                                          |
| Google Gson           | 2.10.1    | [jar download](https://mavenlibs.com/jar/file/com.google.code.gson/gson)                 |

The build script can retrieve the framework jar from your device for development purposes,
but it's discouraged for distribution since it can contain specific vendor methods.

Instead, use [this script](../bin/get-lineageos-libs.sh) which downloads the latest LineageOS OTA update for Pixel 4 "flame",
then extracts all of its system base libraries.
</details>

## Building

```nginx
bash build.sh;  # [--help] [jar|run]
```

## Credits

- [Android Stack Exchange — Obtain package name AND common name of apps via ADB](https://android.stackexchange.com/a/250521)

- [scrcpy — server development](https://github.com/Genymobile/scrcpy/blob/master/doc/develop.md#server)

- [Eli Billauer Blog — Android: Compiling and running a Java command-line utility](https://billauer.co.il/blog/2022/10/android-java-dalvikvm-command-line/)

- [Racoon downloader — How to run Java programs directly on Android (without creating an APK)](https://raccoon.onyxbits.de/blog/run-java-app-android/)

- [elinux.org — Android Zygote Startup](https://elinux.org/Android_Zygote_Startup)

### (unused but interesting)

- [Racoon downloader — Programmatically calling into the Android runtime from ADB shell commands](https://raccoon.onyxbits.de/blog/programmatically-talking-to-the-android-system-adb-shell/)

- [Alexander Fadeev's Blog — Bypassing the Android Linker Namespace](https://fadeevab.com/accessing-system-private-api-through-namespace/)
