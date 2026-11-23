# trailer.json reference

All paths are relative to where you run the scripts (the project root). `{work}`, `{name}` and `{window}` inside an instance's `env` values are replaced with the absolute work folder, the instance's name and its window string.

## Top level

| key | meaning |
|---|---|
| `name` | label written to `timing.txt` |
| `window_match` | text that the OBS window title ("[process] title") contains, to find the game windows. Check with `OBS_WINDOW_MATCH=text python3 -I scripts/obs.py windows` while a copy of the game is running. Needed for `--obs` |
| `scene_prefix` | prefix for the OBS scenes and sources this tool makes ("Prefix - Name"). OBS source names are global: use one that is only yours |
| `title_bar_crop` | capture pixels of title bar cropped off the top of each window (default 56, which is a 28 point title bar captured at 2x; use 28 when the game window is captured at 1x, such as a non-Retina Unity player, and 0 for borderless windows) |
| `work_dir` | where logs, signal files and `timing.txt` go (default `video`; keep it out of git) |
| `build` | shell command that builds the game with the harness (skipped by `--no-build`) |
| `launch` | command that starts ONE copy of the game, as a plain argument list (no shell features, and no `{work}` or `{name}` substitution here: pass per-copy values through the instance `env`). A `caffeinate -d -i` prefix keeps the display awake on macOS |
| `kill_pattern` | optional, passed to `pkill -f` to remove leftover game windows before a take. Write it as `[V]ectorRumble.dll`: the bracket stops the pattern matching the command that contains it |
| `max_seconds` | cap for the match; the watchdog stops everything 90 s after it, so a stuck match cannot record for ever (default 420) |
| `settle_seconds` | wait after the host starts, before binding OBS windows (default 4) |
| `pre_roll` | seconds of the first screen recorded before the host starts moving (default 1.5) |
| `release_file` | name of the signal file (in `work_dir`) that starts the host's scripted walk, touched after the recording starts. The harness must wait for it. Its path in the host's `env` must be `{work}/<this name>`: the two have to agree |
| `signals` | optional list of extra signal file names to delete before each take. Signal files named in the story and `release_file` are deleted automatically; list any that only the harness knows about, or a leftover file from the last take will fire early |
| `mute_inputs` | OBS inputs to mute when recording (default `["Mic/Aux"]`) |
| `env` | environment variables for every copy |
| `instances` | the copies, in LAUNCH order, host last (see below) |
| `story` | the director's script (see below) |
| `edit` | settings for `edit.py` (see below) |

## instances

Each: `name` (used for the log file, the OBS scene and the cues), `window` (a string your harness understands, here "x,y,w,h"; passed through `{window}`), `env` (extra environment), and optional `ready_cue` (a cue this copy prints when parked and ready; the next copies start only after every non-host copy printed it) and `ready_timeout` (seconds, default 60). The LAST instance in the list is the host (there is no "host" key): it starts after the others are ready, gets the highest window id, and when it exits the take ends. The host's `ready_cue` is not used. A single-window game has just one instance, which is the host. `start_gap` (top level, default 0.8 s) separates launches so the window ids ascend in launch order, which is how OBS windows are matched to names.

## Story pattern for a joiner

Live session browser (the joiner is parked on it, the host's game shows up by itself):

```json
{"cut": "John"}, {"wait": "John:session-visible", "timeout": 20}, {"sleep": 0.8}, {"signal": "go-John"}, {"wait": "John:joined", "timeout": 30}
```

One-shot search (the joiner presses Find only once the host is in its lobby):

```json
{"wait": "Host:host-lobby", "timeout": 90}, {"cut": "John"}, {"signal": "find-John"}, {"wait": "John:session-visible", "timeout": 20},
{"sleep": 0.8}, {"signal": "go-John"}, {"wait": "John:joined", "timeout": 30}
```

## Minimal config for a single-window game

```json
{
  "window_match": "My Game",
  "launch": "dotnet MyGame/bin/Release/net8.0/MyGame.dll",
  "build": "dotnet build -c Release -p:DevShots=true -v q --nologo",
  "release_file": "go",
  "env": {"MG_SEED": "1", "MG_SHOWSECONDS": "20"},
  "instances": [{"name": "Game", "window": "0,30,1280,720", "env": {"MG_WIN": "{window}", "MG_RELEASE": "{work}/go"}}],
  "story": [{"cut": "Game"}, {"wait": "Game:game-over", "timeout": 60}],
  "edit": {"card": false}
}
```

The game must hold itself (frozen or on its first screen) until the release file appears: that is what lines the game's timing up with the start of the recording. A game that quits itself at the end of its show is what ends the take. For one window the `cut` step is only there to select the scene.

## story

A list of steps, run in order after the recording has started and the release file is touched:

- `{"cut": "Name"}`: switch OBS to that instance's scene
- `{"wait": "Name:cue", "timeout": 30}`: wait for that cue line in that copy's log; after the timeout it carries on (and says so), so one missed cue never hangs a take
- `{"sleep": 1.2}`: seconds (these are your pacing knobs: shot lengths)
- `{"signal": "go-John"}`: create that file in `work_dir`; the harness polls for it and acts (e.g. a joining player presses Join)

## edit

- `card`: `{"text", "font" (a font file path), "color"}`, or `false` for no card. Default text is "COMING UP...". The card is drawn in headless Chrome, because many ffmpeg builds have no `drawtext`.
- `teaser`: `{"before": 2.55, "length": 3.3}`: the teaser starts `before` seconds ahead of `--kill-at` and lasts `length`.
- `cut`: removes the dead wait. `start`: `{"cue", "players", "pick": "last"|"first", "offset"}`, the cut begins at that cue time (the last of those players' cues) plus the offset. `end`: `{"player", "cue", "offset"}`, the cut ends at that cue time plus the offset (a negative offset keeps the press sound and stops just before a loading screen). The sound is joined with an 80 ms crossfade.

- `credits`: a closing (or opening) card of text lines, for example "Directed by ..." and "Implemented by ...". Keys: `directed_by` and `implemented_by` (each makes one line), or `lines` (a list, used as is, which also suits a studio name); `at` (`"end"`, the default, or `"start"`); `seconds` (default 4); `font`, `color`, `size` (default 64). At the end, `after` is `{"player", "cue", "hold"}`: the picture holds `hold` seconds (default 5) after that cue (use the game-over cue, so the scoreboard stays on screen), fades to black, and the card fades in while the game's own sound carries on underneath and fades out. Without `after` it starts `seconds` before the end of the recording. The recording must run on past `cue + hold + seconds`, so make the game keep running after the end (for example a quit-after-over delay of 9 s or more); `edit.py` stops with a message when the tail is too short. `implemented_by` is the agent's own name: the agent that made the trailer writes it in, and a trailer made by hand leaves it out.

A minimal `edit` for a one-window trailer: `{"card": false}`. Leave `cut` out when there is no dead wait to remove, and leave out `--kill-at` when you do not want a teaser (the script then lists the loudest sounds, which you can ignore).

## Portrait and odd-shaped games

`obs.py` scales each window to fit the OBS canvas and centres it, so a portrait game is pillarboxed on black in a landscape canvas. For a portrait trailer, set OBS's canvas (Settings > Video) to a portrait size such as 1080x1920 first. `edit.py` makes 1920x1080 output (the pillarboxed picture is kept as is, which is fine for YouTube), so for a true portrait video set the canvas first and change the output size in `edit.py`.

## Dry runs

`record.py` prints every cue as it appears (`[  12.3s] John cue joined`), how long each story wait took, and a list of cues that never came. Use `--cap` on a dry run so a stuck game is stopped, but set it above the length of the whole show (a match still running at the cap is killed, with exit code -15), and `--work` so the logs of a good take survive. After the run it prints a table of every cue each copy printed, in order, as seconds since the start: check that the order makes sense. Dry runs play the game's sound on your speakers; add a mute switch to the dev build (an env var that sets the master volume to 0) and pass it with `--env` for dry runs. Put the dry-run work folder inside the project (for example `video/dry`), next to your real one, and keep it out of git.

## Files in work_dir

`<Name>.log` (game output, with cue lines), `timing.txt` (`recording_started_unix=` and `recording_file=`), and the signal files. `edit.py` needs `timing.txt` and the logs of the take it is editing: pass `--work <folder>` to `record.py` for each take (or dry run) so they are kept apart, and the same `--work <folder>` to `edit.py`.
