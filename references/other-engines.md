# Other engines: Unity (tried once) and Godot (untested sketch)

The scripts need only four things from a game, whatever engine it uses:

1. It starts from one command (the config's `launch`), several copies at once.
2. It reads settings from environment variables (or command line arguments, if you put them in `launch`).
3. It prints cue lines to standard output: `cue <name> unix-ms <n>`.
4. It can place and size its window, set a unique window title, play from a script, and quit by itself.

Everything else (OBS, cuts, edit) is the same. The Unity section comes from a real attempt (dry runs only so far, see its notes); the Godot section is untested. Check API names against your engine version.

## Unity (tried once, on a first person shooter; macOS standalone player)

Everything below was found by an agent building a harness for a Unity 6 project. Check names against your version.

**Dev switch.** Do not edit Player Settings. Write one editor build method and pass the define in code with `BuildPlayerOptions.extraScriptingDefines`, so a normal build never contains the harness:

```csharp
// Assets/TrailerHarness/Editor/TrailerBuild.cs
public static class TrailerBuild
{
    public static void Build()
    {
        string oldName = PlayerSettings.productName;
        PlayerSettings.productName = "MyGameTrailer";     // the product name is both the binary name and the window title
        try
        {
            var opts = new BuildPlayerOptions {
                scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray(),
                locationPathName = "Builds/MyGameTrailer.app",
                target = BuildTarget.StandaloneOSX,
                extraScriptingDefines = new[] { "TRAILER" } };
            var report = BuildPipeline.BuildPlayer(opts);
            if (report.summary.result != BuildResult.Succeeded) EditorApplication.Exit(1);
        }
        finally { PlayerSettings.productName = oldName; }
    }
}
```

Run it in batch mode (Unity must have a licence; the Hub being signed in is enough; only one Unity process may use a project at a time, so close the editor first):

    /Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity -batchMode -quit -projectPath . -buildTarget StandaloneOSX -executeMethod TrailerBuild.Build -logFile video/build.log

A cold build of a mid-sized project took about 4 minutes, an incremental one about 20 seconds. Do NOT put this in `trailer.json`'s `build` key (it would run on every take; use `--no-build` or leave `build` out), run it yourself in the background and poll the log.

**Launch.** Start the binary directly: `caffeinate -d -i Builds/MyGameTrailer.app/Contents/MacOS/MyGameTrailer -logFile -` (on macOS, `open` merges copies into one). `launch` has no `{work}` substitution, so pass per-copy settings through environment variables in `trailer.json`.

**Cue lines (important).** On macOS, `Console.Out.WriteLine` does NOT reach standard output by itself: it goes only to `~/Library/Logs/<Company>/<Product>/Player.log`. You MUST add `-logFile -` to `launch`; then `Console.Out.WriteLine("cue ready unix-ms " + ms); Console.Out.Flush();` arrives on standard output (and Unity's own log lines do too). A first dry run with no cues usually means this flag is missing.

**Window.** Product Name is the window title (set it in the build method, unique to this game, and use it as `window_match`). In code: `Screen.SetResolution(w, h, FullScreenMode.Windowed);` wait two frames, then `yield return Screen.MoveMainWindowTo(Screen.mainWindowDisplayInfo, new Vector2Int(x, y));`. The position is relative to the display's top-left. Also set `Application.runInBackground = true` and `QualitySettings.vSyncCount = 0`. You can only confirm the window's title and place once OBS is running (`obs.py windows`). **Sharpness:** a Unity macOS player is not Retina by default, so a 1280x720 point window is captured at 1x (1280x728 px) and upscaled about 1.5x to 1080p, which looks soft; turn on Mac Retina support in Player Settings so the window renders 2560x1440 px (as the MonoGame games did), or use a 1920x1080 window if the screen is big enough. At 1x the title bar is about 28 px, so set `title_bar_crop` to match the capture scale (56 for 2x, 28 for 1x) and look at a frame to check no strip or game edge is cropped wrongly.

**Harness structure.**
- Put the autopilot in a `MonoBehaviour` created from a `[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]` method, wrapped in `#if TRAILER`, and only start it when an environment variable such as `TRAILER_RELEASE` is set, so a double-clicked dev build plays normally.
- Hold on the first screen until the release file appears (a coroutine with `while (!File.Exists(path)) yield return null;`), then run the story as a coroutine: `yield return new WaitForSeconds(0.7f)`, `SceneManager.LoadScene(...)`, `yield return new WaitUntil(...)`. For a menu, select the button with the EventSystem, wait, then invoke `onClick`; if the menu is a single Play button that only loads a scene, loading the scene directly is simpler.
- **Assembly definitions.** Many Unity template games put their code in `.asmdef` files, and a script in plain `Assets/` (the default assembly) cannot be referenced from them. Put the input hook as a static class INSIDE the game's own assembly (wrapped in `#if TRAILER`), have the autopilot write to it, and have the game's single input-reading class read it. This is also how to drive the player with the new Input System: patch the project's input wrapper, do not synthesise key events.
- **Cursor lock.** If the game ignores input unless `Cursor.lockState` is `Locked`, bypass that check under `#if TRAILER`.
- **Physics games are not repeatable.** Frame-rate dependent physics and NavMesh mean the same seed gives a different run. Count on best effort: an invincible hero, a stuck rescue (warp or re-route after a few seconds without progress), a guard against walking off ledges, and an unconditional time cap.
- **Shooters.** A fire button held down may fire once if the game shoots on a fresh press: pulse it. Aim with smoothed yaw and pitch, check line of sight, and keep the player moving toward the next enemy.
- **Show length.** The show timer should start at the first gameplay frame, not at process start; loading and menus are dead time that `edit.cut` can remove (for a single window set `start` to `{"cue":"released","players":["Game"],...}` and `end` to the first gameplay cue).
- **Mute switch.** `AudioListener.volume = 0` when an environment variable is set, for dry runs.

## Godot (4.x)

- **Dev switch:** run a dev scene or an autoload only when a user argument is present: `OS.get_cmdline_user_args()` (arguments after `--`), or `OS.has_feature("trailer")` with a custom feature tag set in an export preset.
- **Settings:** `OS.get_environment("TRAILER_SEED")`. Starting several copies of the exported binary (or `godot --path <project>`) is fine.
- **Cue lines:** `print("cue %s unix-ms %d" % [name, int(Time.get_unix_time_from_system() * 1000.0)])` goes to standard output.
- **Window:** `DisplayServer.window_set_size(Vector2i(w, h))`, `DisplayServer.window_set_position(Vector2i(x, y))`, `DisplayServer.window_set_title("MyGame")`.
- **Autopilot:** an autoload with `await get_tree().create_timer(0.7).timeout` between steps, and a loop that waits for a file to appear (`FileAccess.file_exists(path)`). For menus, call `grab_focus()` on the Button, wait, then `emit_signal("pressed")`.
- **Quit:** `get_tree().quit()`.
- **Focus:** `Engine.max_fps` and low-processor mode can slow an unfocused window: turn them off in the dev build (`OS.low_processor_usage_mode = false`).

## What to expect

Most of the effort is the harness, as in the C# MonoGame examples: the menu walk, the release gate, signal files, the quit timer, and the cue lines. Use `monogame-example.md` as the shape of it (the wait-script is the same idea in every engine), and keep the rest of `harness-contract.md` as the checklist.
