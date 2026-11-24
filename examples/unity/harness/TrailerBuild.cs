using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

// Builds the dev-only trailer player. The harness is compiled in only by the TRAILER define passed here.
//   Unity -batchMode -quit -projectPath . -buildTarget StandaloneOSX -executeMethod TrailerBuild.Build -logFile video/build.log
public static class TrailerBuild
{
    public const string Name = "FPSMicrogameTrailer";   // product name = binary name = window title; unique to this build

    public static void Build()
    {
        string oldName = PlayerSettings.productName;
        bool oldRetina = PlayerSettings.macRetinaSupport;
        try
        {
            PlayerSettings.productName = Name;
            PlayerSettings.macRetinaSupport = true;        // render 2x so a 1280x720 point window is captured sharp
            PlayerSettings.runInBackground = true;
            var opts = new BuildPlayerOptions
            {
                scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray(),
                locationPathName = "Builds/" + Name + ".app",
                target = BuildTarget.StandaloneOSX,
                options = BuildOptions.None,
                extraScriptingDefines = new[] { "TRAILER" }
            };
            var report = BuildPipeline.BuildPlayer(opts);
            Debug.Log("TrailerBuild result: " + report.summary.result);
            if (report.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded) EditorApplication.Exit(1);
        }
        finally
        {
            PlayerSettings.productName = oldName;
            PlayerSettings.macRetinaSupport = oldRetina;
        }
    }
}
