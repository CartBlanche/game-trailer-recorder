# game-trailer-recorder

Let your game film its own trailer. A small dev-only "autopilot" in the game plays a scripted match and prints timestamped cue lines; this toolkit starts one copy of the game per player, records every window through OBS, cuts between the scenes automatically from the cues, and edits the result with ffmpeg (title card, teaser, dead time removed). Every take is repeatable: change the game, run one command, get a new video, with the game's own sound.

It is packaged as an agent skill ([`SKILL.md`](SKILL.md), in the Claude Code skill format) so an AI agent can set it up in your game, but the scripts are ordinary Python and work without one.

## Not just games

Nothing in the recording or edit side knows it is filming a game. It starts a program, records its window through OBS, and cuts from the cue lines the program prints. So the same method should work for almost any app that you can drive from a dev-only script: a drawing tool, a music app, a simulator, a desktop or Electron app, a web app in its own window. The app needs the same small harness (walk its own screens, print cue lines at the story beats, quit by itself), and "one copy per player" becomes "one copy per window or role" (or just one window). It has only been tried on games so far, so expect to adjust the harness contract ([`references/harness-contract.md`](references/harness-contract.md)) to your app.

## What you get

- [`scripts/record.py`](scripts/record.py): builds and starts the game copies in the right order, drives OBS, follows a story of cuts, stops cleanly (watchdog, Ctrl-C safe, restores your OBS scene).
- [`scripts/edit.py`](scripts/edit.py): cuts a dead wait, adds a title card, a teaser and an optional credits card ("Directed by ...") from the cue times, outputs 1080p 60 fps H.264.
- [`scripts/obs.py`](scripts/obs.py): a standard-library OBS WebSocket v5 client with `bind-all`, `cut`, `clean` and friends.
- [`references/`](references/): the harness contract (what your game must do), every config key, pitfalls that cost real takes, a MonoGame and a Unity harness explained, and an untested Godot sketch.
- [`examples/monogame/`](examples/monogame/): a real config for a four-player pretend LAN match (Vector Rumble), with the harness code. [The trailer it made](https://www.youtube.com/watch?v=2u5Ls6-l_-A).
- [`examples/unity/`](examples/unity/): a one-window setup for a Unity first person shooter, with the harness code. [The trailer it made](https://www.youtube.com/watch?v=RauPj0VTOPQ).

## Requirements

- OBS 28 or later (install notes below) with the WebSocket server on, and `OBS_PASSWORD` exported in your shell (never stored by these scripts).
- The OBS scene transitions you ask for. A fresh OBS has Cut and Fade; add others in OBS's Scene Transitions dock with the + button.
- ffmpeg and ffprobe (install notes below).
- Python 3.9 or later (standard library only).
- Chrome, for the title card.
- A game you can build with a dev switch, and that can run several copies side by side.
- Tested only on macOS, with MonoGame (C#) games and one Unity game, and only with Claude as the agent. Windows and Linux are untested.
- Other engines need their own harness (the contract is engine independent).

### Installing OBS

| System | Command |
|---|---|
| macOS | `brew install --cask obs` |
| Windows | `winget install -e --id OBSProject.OBSStudio` |
| Linux | `flatpak install flathub com.obsproject.Studio` |

Installers: https://obsproject.com. Then enable the WebSocket server (Tools > WebSocket Server Settings: turn on the server and authentication, set a password, press Apply; the default port is 4455) and export that password as `OBS_PASSWORD`.

### Installing ffmpeg (and ffprobe, which comes with it)

| System | Command |
|---|---|
| macOS | `brew install ffmpeg` |
| Windows | `winget install Gyan.FFmpeg` (or `choco install ffmpeg`, or `scoop install ffmpeg`); open a new terminal afterwards so `ffmpeg` is on the PATH |
| Debian, Ubuntu | `sudo apt install ffmpeg` |
| Fedora | `sudo dnf install ffmpeg` (enable RPM Fusion first if it is not found) |
| Arch | `sudo pacman -S ffmpeg` |

Check it with `ffmpeg -version` and `ffprobe -version`; the build needs H.264 (`libx264`), which these packages include. Python 3 and Chrome (`CHROME=<path>` if it is not found) are installed the usual way. `record.py` currently uses `pkill` and the config's `launch` often starts with `caffeinate` (both macOS or Unix tools), so on Windows or Linux expect to adapt those first.

## Quick start

1. Add a dev-only harness to your game (see [`references/harness-contract.md`](references/harness-contract.md); [`references/monogame-example.md`](references/monogame-example.md) and [`references/unity.md`](references/unity.md) explain two real harnesses, with the code in [`examples/`](examples/)).
2. Write a `trailer.json` (start from [`examples/`](examples/), keys in [`references/config.md`](references/config.md)).
3. Dry run, no OBS needed: `python3 -I scripts/record.py trailer.json --work video/dry --cap 60`
4. Record: `python3 -I scripts/record.py trailer.json --obs`
5. Edit: `python3 -I scripts/edit.py trailer.json "<recording>.mov" --kill-at <seconds>`

## Using it with an AI agent

- **Claude Code:** put this folder in your skills directory and ask for "a scripted gameplay trailer of my game"; the skill triggers by itself.
- **Other agents with a shell and file access** (Codex, Cursor, Copilot agent mode and similar): open this repository and tell the agent to "read [`AGENTS.md`](AGENTS.md) and [`SKILL.md`](SKILL.md) and follow them". [`AGENTS.md`](AGENTS.md) is the file many such tools read automatically. These agents have not been tested with it; the instructions are plain markdown and should carry over.
- **A chat assistant with no shell** (for example ChatGPT in the browser): it cannot start games or reach OBS, so it can only explain the method and help you write the game harness. You would run the scripts yourself.

## Using it without an agent

1. Read [`references/harness-contract.md`](references/harness-contract.md) and add the dev-only autopilot to your game (about 100 to 300 lines).
2. Copy [`examples/monogame/trailer.json`](examples/monogame/trailer.json), change the game command, windows, env variables and story (every key is in [`references/config.md`](references/config.md)).
3. Dry run until the cue timeline looks right, then record with `--obs`, check the frames and sound with ffmpeg, then edit.

## Other engines

The scripts do not care what engine the game uses; only the in-game autopilot is engine specific. See [`references/unity.md`](references/unity.md) for a Unity harness that ran end to end, and [`references/other-engines.md`](references/other-engines.md) for an untested Godot sketch.

## Status

Used for four games so far: a four-player LAN shooter, a two-player LAN artillery game and a one-window AI demo (all MonoGame), and a Unity first person shooter (one real recording). Expect to need about ten takes for a polished trailer; [`references/pitfalls.md`](references/pitfalls.md) lists the mistakes that cost the most. Ideas not built: music in the edit, portrait output, Windows and Linux notes.

## Licence

MIT, see `LICENSE`.
