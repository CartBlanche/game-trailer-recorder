# Unity: the harness contract in a Unity game (macOS standalone player)

A Unity 6 first person shooter (the FPS Microgame) was recorded end to end with this. The working code is in [`examples/unity/`](../examples/unity/); this page explains the rules behind it. Check API names against your Unity version.

## Setup

**Dev switch.** Do not edit Player Settings. Write one editor build method and pass the define in code with `BuildPlayerOptions.extraScriptingDefines`, so a normal build never contains the harness:

The working method is [`examples/unity/harness/TrailerBuild.cs`](../examples/unity/harness/TrailerBuild.cs). It sets a unique product name (the binary name and the window title) for the build and puts it back afterwards.

Run it in batch mode (Unity must have a licence; the Hub being signed in is enough; only one Unity process may use a project at a time, so close the editor first):

    /Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity -batchMode -quit -projectPath . -buildTarget StandaloneOSX -executeMethod TrailerBuild.Build -logFile video/build.log

A cold build of a mid-sized project took about 4 minutes, an incremental one about 20 seconds. Do NOT put this in `trailer.json`'s `build` key (it would run on every take; use `--no-build` or leave `build` out), run it yourself in the background and poll the log.

**Launch.** Start the binary directly: `caffeinate -d -i Builds/MyGameTrailer.app/Contents/MacOS/MyGameTrailer -logFile -` (on macOS, `open` merges copies into one). `launch` has no `{work}` substitution, so pass per-copy settings through environment variables in `trailer.json`.

**Cue lines (important).** On macOS, `Console.Out.WriteLine` does NOT reach standard output by itself: it goes only to `~/Library/Logs/<Company>/<Product>/Player.log`. You MUST add `-logFile -` to `launch`; then `Console.Out.WriteLine("cue ready unix-ms " + ms); Console.Out.Flush();` arrives on standard output (and Unity's own log lines do too). A first dry run with no cues usually means this flag is missing.

**Window.** Product Name is the window title (set it in the build method, unique to this game, and use it as `window_match`). In code: `Screen.SetResolution(w, h, FullScreenMode.Windowed);` wait two frames, then `yield return Screen.MoveMainWindowTo(Screen.mainWindowDisplayInfo, new Vector2Int(x, y));`. The position is relative to the display's top-left. Also set `Application.runInBackground = true` and `QualitySettings.vSyncCount = 0`. You can only confirm the window's title and place once OBS is running (`obs.py windows`). **Sharpness:** a Unity macOS player is not Retina by default, so a 1280x720 point window is captured at 1x (1280x728 px) and upscaled about 1.5x to 1080p, which looks soft. Turn on Mac Retina support in Player Settings (as the MonoGame games did; see More findings for the resolution units), or use a 1920x1080 window if the screen is big enough. Set `title_bar_crop` to match the capture scale (28 for 1x; 64 for the 2x window below) and look at a frame to check no strip or game edge is cropped wrongly.

**Harness structure.**
- Put the autopilot in a `MonoBehaviour` created from a `[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]` method, wrapped in `#if TRAILER`, and only start it when an environment variable such as `TRAILER_RELEASE` is set, so a double-clicked dev build plays normally.
- Hold on the first screen until the release file appears (a coroutine with `while (!File.Exists(path)) yield return null;`), then run the story as a coroutine: `yield return new WaitForSeconds(0.7f)`, `SceneManager.LoadScene(...)`, `yield return new WaitUntil(...)`. For a menu, select the button with the EventSystem, wait, then invoke `onClick`; if the menu is a single Play button that only loads a scene, loading the scene directly is simpler.
- **Assembly definitions.** Many Unity template games put their code in `.asmdef` files, and a script in plain `Assets/` (the default assembly) cannot be referenced from them. Put the input hook as a static class INSIDE the game's own assembly (wrapped in `#if TRAILER`), have the autopilot write to it, and have the game's single input-reading class read it. This is also how to drive the player with the new Input System: patch the project's input wrapper, do not synthesise key events.
- **Cursor lock.** If the game ignores input unless `Cursor.lockState` is `Locked`, bypass that check under `#if TRAILER`.
- **Physics games are not repeatable.** Frame-rate dependent physics and NavMesh mean the same seed gives a different run. Count on best effort: an invincible hero, a stuck rescue (warp or re-route after a few seconds without progress), a guard against walking off ledges, and an unconditional time cap.
- **Shooters.** A fire button held down may fire once if the game shoots on a fresh press: pulse it. Aim with smoothed yaw and pitch, check line of sight, and keep the player moving toward the next enemy.
- **Show length.** The show timer should start at the first gameplay frame, not at process start; loading and menus are dead time that `edit.cut` can remove (for a single window set `start` to `{"cue":"released","players":["Game"],...}` and `end` to the first gameplay cue).
- **Mute switch.** `AudioListener.volume = 0` when an environment variable is set, for dry runs.

## More findings

- Check Player Settings first: the project may already have Mac Retina support on. With it on, `Screen.SetResolution` takes PIXELS: asking for 1280x720 gave a 640x360 point window; ask for 2560x1440 to get a 1280x720 point window (the example uses a scale variable). The title bar of such a window is 32 points, so `title_bar_crop` is 64.
- A kill at a low Y (falling off the map) ignores invincibility. An autopilot that warps the hero (a stuck rescue) can drop it through the world. Keep a floor guard that warps back to the last good navmesh position, only warp onto `NavMesh.SamplePosition` points, and make the harness print a "failed" cue and not the end cue when the lose scene loads.
- A level that ends when the last enemy dies will load the win scene in the middle of your show: the pilot must not kill the last enemy.
- A fixed seed does not make a Unity run play the same way twice. Schedule the key beat (here, a cover duck) by time after the start of gameplay, and print cues around it so the edit's `teaser.cue` can centre on it.
- Frames can be checked without OBS and without `screencapture` (often blocked) by having the game save its own screenshots under a dev env variable.
- Game audio may be quiet in the recording (mean about -35 to -45 dB for this game); check it with `volumedetect` and tell the user.
