# Example: Unity, a one-window first person shooter

This is the setup used for the real trailer of the Unity FPS Microgame (the Unity 6 first person shooter template), recorded on macOS as a standalone player. It is the one-window case: no joining players, one copy of the game that plays itself from the menu until the level is won (about 25 seconds of play in this small level).

The story: the main menu, Play is pressed, the hero fights through the level (an AI pilot walks the navmesh, aims, fires in pulses, is invincible), kills the hover bot, steps out of cover, draws the turret's fire, ducks behind cover and steps out again, then destroys the turret so the game shows "All objectives completed". The edit opens with a "COMING UP..." card and a 2.8 s teaser of the cover moment (centred on the `cover-peek` cue the game prints), cuts the level-load wait, and ends with the "Directed by ..." credits card over the fading game sound.

## Files

- `trailer.json`: the config (`launch` ends with `-logFile -`: without it no cue line reaches the recorder on macOS).
- `harness/TrailerBuild.cs`: the batch build method (unique product name, Retina support, `extraScriptingDefines = TRAILER`). Goes in `Assets/<anything>/Editor/`.
- `harness/TrailerInput.cs`, `TrailerHarness.cs`, `TrailerPilot.cs`: the dev-only autopilot, all inside `#if TRAILER`, in the game's own assembly (the project uses assembly definitions, so the hook has to live there).
- `harness/PlayerInputHandler.patch`: the five small `#if TRAILER` blocks that make the game's input class read the autopilot instead of the keyboard and mouse.

These are tied to this project (its scenes, enemy and turret classes, its input class). Use them as a model for how a Unity harness fits together, not as drop-in code; `references/other-engines.md` explains the rules behind each part.

## What to know

- Run: build once (about 5 minutes cold; use `--no-build` for later takes), then `OBS_PASSWORD=... python3 -I <skill>/scripts/record.py trailer.json --obs --no-build`. The game must not run while Unity builds.
- With Retina support on, `Screen.SetResolution` takes pixels: a 1280x720 point window is 2560x1440 (the harness does this with `TRAILER_SCALE=2`). The title bar of that window is 32 points, so `title_bar_crop` is 64.
- Falling off the map kills the hero even when invincible, so the pilot has a floor guard and a stuck rescue, and prints `cue failed` instead of `show-end` if the level is lost. Check the cue timeline of every take.
- A fixed seed does not make a Unity run play the same way twice: the cover beat is scheduled by time, not by waiting for an event.
