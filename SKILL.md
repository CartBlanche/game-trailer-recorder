---
name: game-trailer-recorder
description: Make a scripted gameplay trailer or demo video of a game by letting the game play itself, with real sound. It runs one copy of the game per player (a pretend multiplayer match works well), records every window through OBS, cuts between the scenes automatically from cue lines the game prints, then edits with ffmpeg (title card, teaser, dead time cut). Use this whenever the user wants a trailer, gameplay video, promo clip, itch.io or YouTube video, "scripted recording", "record the game with OBS", or an automated or repeatable demo of their game, even if they never say "skill", "OBS" or "director".
compatibility: Needs OBS 28+ with the WebSocket server enabled, ffmpeg and ffprobe, Python 3, headless Chrome for the title card, and a game that can run several copies side by side. Tested on macOS only.
---

# Game trailer recorder

The game films itself. You give it a small dev-only "autopilot", it prints timestamped cue lines at the story beats, and three small scripts do the rest: `record.py` (start the games, drive OBS, cut between scenes), `edit.py` (ffmpeg edit from the cue times) and `obs.py` (the OBS WebSocket client both use). A take is repeatable: change the game, run one command, get a new take.

Why this way, and not screen-recording by hand: timing from human hands is slow and different every time, a hand recording cannot show four players at once, and menus idle into a "Paused" screen while you fumble. Cue lines let the director wait for events instead of guessing durations, and they let the edit find its cut points exactly.

## Before the first recording (prerequisites)

- **OBS** 28 or later is open, with the WebSocket server enabled (Tools > WebSocket Server Settings) and a password set.
- **`OBS_PASSWORD` is exported** in the shell that runs `record.py --obs` (add `export OBS_PASSWORD=...` to the shell profile, or export it in the terminal). It is the only way the scripts get the password: it is never a command line argument, never written to a file. Check it without printing it: `[ -n "$OBS_PASSWORD" ] && echo set || echo missing`. If the OBS server is not on localhost:4455, also set `OBS_HOST` and `OBS_PORT`.
- ffmpeg, ffprobe, Python 3 and (for the title card) Chrome are installed; the game builds with its dev switch.

Without `--obs` none of the OBS items are needed, so dry runs work on any machine.

## Who does what

The user owns: the OBS password (they export `OBS_PASSWORD` in their own terminal; never ask them to paste it in chat, never write it to a file), judging each take by eye and ear, and approving before anything is committed. If they do paste it, tell them to change it. You own the harness, the config, the dry runs, frame and audio checks, and the edit.

## Workflow

1. **Interview** (keep it short). Ask for the names and labels that will be visible in the video (player names, level, ship choices): an example config uses placeholder names, and a take recorded with them shows them. What is the story, in beats? One player or several? Engine and how to run a dev build? How is a window named? Which screen sizes? Read `references/harness-contract.md` before touching the game.
2. **Add the harness to the game** (dev-only, compiled out of release builds). It must be driven by environment variables, walk the menus by itself, let AI fly or play, end the match at a score limit, print cue lines, and quit the process. The contract is in `references/harness-contract.md`; a worked C# (MonoGame) example is in `references/monogame-example.md`.
3. **Write `trailer.json`** from `examples/monogame/trailer.json`. Every key is explained in `references/config.md`. The story is a list of steps (cut to, wait for a cue, sleep, touch a signal file).
4. **Dry-run without OBS** until the story and the cues are right: `python3 -I <skill>/scripts/record.py trailer.json --work video/dry --cap 60`. Run it from the project root; keep the work folder inside the project and out of git. Each dry run plays the whole script in real windows, so it needs the display on and the windows visible, and it plays sound on the speakers unless your game has a mute switch. Set `--cap` above the length of the whole show (a cap below it kills the games mid-match, exit code -15). It prints every cue as it appears, how long each wait took, and a list of cues that never came; the full game output is in `<work>/<Name>.log`. The cue timeline printed at the end is in seconds since the RECORDING started when you use `--obs`, so its times match the video and `edit.py`; the live lines (`[ 12.3s]`) count from the start of the run, which is earlier. A one-window game works too: see the minimal config in `references/config.md`. Expect several.
5. **Record with OBS**: `OBS_PASSWORD=... python3 -I <skill>/scripts/record.py trailer.json --obs` (the user runs it, or runs it in a terminal you can see; their terminal holds the password). Never kill it with a signal that skips cleanup; Ctrl-C is fine, it stops OBS first. Afterwards check the file with ffprobe, and look at frames with `ffmpeg -ss T -i FILE -frames:v 1 x.png`. Check the audio with `volumedetect` and `silencedetect`, especially the first 20 seconds.
6. **Show the user**. They approve or give notes ("too slow", "names too small", "the wait is dead", "the AI got stuck"). Plan on about ten takes. Fix the cause (usually timing constants in the story, or a harness gap), not the symptom. Give every take its own `--work` folder and keep its recording, so any of them can still be edited later. Before the cue timeline looks fine, look at a few frames: a take can have every cue and still show a player stuck on scenery.
   **Do not run the edit until the user has picked the take.** Say which recordings exist (path, length, anything odd in the cue timeline) and ask which one to use; then edit exactly that one (pass its `--work` folder to `edit.py`). Re-editing is cheap, so also offer a different `--kill-at` or card text if they have notes.
7. **Transition**: OBS changes scenes with whatever transition it has set (often Swipe or Fade). For hard cuts, or any other look, set `transition` in the config (for example `{"name": "Cut"}`); `obs.py transitions` lists the names, and the user's setting is put back after the take.
8. **Credits**: ask who is to be credited as director (and whether they want a card at the end or the start), and put it in `edit.credits` (see `references/config.md`). Write your own name in `implemented_by`; never invent a credit for someone else. The game must run on a few seconds after the end of the story so the sound can fade under the card.
9. **Edit**: `python3 -I <skill>/scripts/edit.py trailer.json <recording>`. Without `--kill-at` it lists the loudest sounds so you can pick a teaser moment from frames; then re-run with `--kill-at S`. The result is `<recording> final.mp4`.
10. **Tidy up**: the scenes and sources this tool made stay in the user's OBS. `OBS_SCENE_PREFIX=<scene_prefix> python3 -I <skill>/scripts/obs.py clean` removes exactly those (and only those). `record.py` already switches OBS back to the scene that was showing before the take.
9. Commit only when the user asks. Keep the work folder (logs, recordings) out of git.

## The things that cost the most time

Read `references/pitfalls.md` before the first take; it is short and every item cost a real take. The three that matter most: start every other copy first and the host last (a copy idling in a menu pops up a Paused screen); keep every window at the final video's size and fully visible (small or covered windows look soft or stall); and make scripted actions play the same menu sounds as real input (or the first 20 seconds are silent).

## Layout of this skill

- `scripts/record.py`, `scripts/edit.py`, `scripts/obs.py`, `scripts/card.html`: generic, driven by `trailer.json`.
- `references/config.md`: every key of `trailer.json`.
- `references/harness-contract.md`: what a game must do (engine-independent).
- `references/monogame-example.md`: the contract implemented in a MonoGame game.
- `references/other-engines.md`: untested sketches of the contract for Unity and Godot.
- `references/pitfalls.md`: mistakes already made, and the fix for each.
- `examples/monogame/trailer.json`: a real, working config (four-player pretend LAN match).
- `examples/unity/`: a real one-window Unity config plus the harness code (read it for any Unity game).

## Limits to say out loud to the user

A game with no sound at all makes a silent trailer (the audio check will show total silence; that is not a bug in the recording). Say so, and offer music in the edit. `edit.py` writes 1920x1080 landscape; a portrait game recorded on a landscape OBS canvas is pillarboxed on black.

Tested on macOS only (window capture, `caffeinate`, `pkill`). Windows and Linux need different window capture settings and launch wrappers; say so, and treat them as untested. The harness cannot be made generic: each engine needs its own, and you write it. OBS must already be running with the WebSocket server on.
