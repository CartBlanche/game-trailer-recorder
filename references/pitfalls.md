# Pitfalls (each one cost a real take)

## Windows and picture
- A window capture renders the game at the window's size. A window smaller than the video looks soft once scaled. Size every copy to the final video size in points (see `harness-contract.md`) and check the printed back buffer size.
- A covered or minimised window is throttled and its game stalls. Keep every window on screen. Overlapping the top edge of the others is fine as long as OBS can still capture all of it; check each scene in a test take.
- A game that draws a fixed canvas smaller than its window leaves bars at the sides. Check the bars in a test frame: they can show leftover pixels (a stale buffer, or another window showing through) in the recording. Clear the whole back buffer every frame in the dev build, or crop the capture.
- Keep the display awake (`caffeinate -d -i` in the launch command on macOS).
- `screencapture` and similar may be blocked in an agent's environment. Get frames from the game's own screenshot hook, or from ffmpeg on the recording.

## Focus
- Only one window has the keyboard focus. In an unfocused window a game may draw its menus without the highlight, ignore input, or sleep when inactive. Force the game to act as focused and disable the inactive sleep in the dev build (found when two copies of a LAN game ran side by side).

## Start order and the Paused screen
- A copy idling in a menu can pop up a Paused screen. Start every other copy first and wait until each prints its ready cue, start the host last, start OBS recording, and only then release the host's scripted walk with a signal file. Also turn the idle-pause off for scripted copies.
- Joining copies should start already on the screen the viewer needs. Do not walk them through the menus the host used; cut straight to them.

## Pacing and story
- Menu steps of about 3 s feel dead. Aim for 1.5 s at most from one selection to the next.
- The wait when everybody is ready and the host presses Start is the first thing to cut in the edit.
- Pick a short score limit and the calmest level. A busy level makes AI pilots look twitchy.
- Tune the timing constants in the story, not sleeps scattered in the harness.

## Sound
- Menu sounds missing means a silent first 20 s: scripted actions skipped the sound call.
- Window capture carries the game's own sound; mute the mic input (the launcher does).
- Check audio with `ffmpeg -af volumedetect` and `silencedetect`, not only by ear. A muted Mac can fool your own listening, though not the recording.

## OBS
- Source names are global across all scenes and projects. Use a unique scene prefix, unique source names per run (the script adds a run id), and never edit another project's sources.
- A source removed a moment ago keeps its name busy; the script waits and retries.
- A window-capture source repointed at a new window can sit at 0x0 and record nothing. The script creates fresh sources every run.
- Only one recording can run at a time. Do not start or stop a recording you did not start. The launcher checks first.
- Never leave a recording running: it keeps growing (one reached 1.3 GB). Use the watchdog, and stop a take with Ctrl-C so cleanup runs. Killing a background task can leave OBS recording; stop it with `obs.py stop`.
- Never ask OBS for the property list of an `sck_audio_capture` input: it crashed OBS.
- The recording file is not readable the instant OBS stops ("moov atom not found"). Retry ffprobe for up to 30 s.
- After every recording, ffprobe the file (video and audio streams, duration) and look at a few frames before saying it worked.
- Bind scenes in the order the games were started: windows are matched by window id.
- Never store, echo or paste the OBS password. It comes from `OBS_PASSWORD` in the user's own terminal.

## Shell and tools
- `pkill -f foo` can match your own command line and kill your shell. Use the bracket trick (`[V]ectorRumble.dll`) or kill by pid.
- Do not rebuild while a game is running from the same binary.
- Many ffmpeg builds have no `drawtext`. Draw title cards in headless Chrome and overlay the image.
- Python text-mode edits turn CRLF into LF in a CRLF repo; use an editor tool or open with `newline=""`.
- Anchor `.gitignore` entries (`/video/`), or `video/` also ignores `itch/video/`. Never commit `__pycache__`, recordings or logs.
- A background watcher waiting on a file that a killed script will never write never ends; stop it.
- Dry runs overwrite the work folder: use `--work` so the logs and `timing.txt` of a take you still want to edit survive.

## Working with the person
- Show them frames or a take before committing a new look, and re-read their requests literally ("don't walk John through Play" meant: cut straight to John on the right screen).
- Names and labels that are tiny in play are unreadable in a trailer: enlarge or recolour them behind the dev switch.
- Plan on about ten takes. Fix startup order, window sharpness and silent menus first; they cost the most.
