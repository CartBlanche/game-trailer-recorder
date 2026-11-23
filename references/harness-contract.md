# The harness contract

The scripts are generic; the game is not. Every game needs a small dev-only "autopilot" that follows this contract. Build it into the game behind a compile switch (so it cannot ship), driven by environment variables.

Items are marked **required** or **if you have it** (a menu, multiplayer, a score). A one-window game with no menus needs only: window, seed, the release gate, cue lines, and a quit timer.

## 1. Input: environment variables

Names are yours (Vector Rumble uses a `VR_` prefix). You need these kinds of setting, passed per copy through `trailer.json`:

- **Identity** (if you have players): the player name, ship/character/colour, so four copies look different.
- **Window** (required): position and size from one string (e.g. "x,y,w,h"). Size it to the final video size in POINTS (if the game draws a fixed canvas of another shape, such as 800x480, it is letterboxed inside the window: accept the black bars, or make the window the canvas shape, or add a dev-only layout for 16:9): a window smaller than 1920x1080 pixels once scaled looks soft. On a Retina Mac with a game that is not HiDPI aware, back-buffer pixels equal window points, so 1280x720 points captured at 2x is sharp enough for 1080p. Print the real back buffer size at start so you know.
- **Determinism** (required): a seed for AI and randomness, a fixed level, a fixed background, and anything that depends on the date, the time, the locale, the machine or saved settings (a seasonal theme that changes with the calendar, a random daily challenge). The same seed should play the same match if the game is unchanged: best effort only. Games with physics, navigation meshes or frame-rate dependent AI will vary, so add a stuck rescue and an unconditional time cap.
- **Autopilot** (required, in some form: AI, a replay, or a scripted camera): `AI flies every ship`, plus anything the story needs (end the match at a score limit, e.g. first to 5; quit some seconds after the game-over screen; quit at a hard cap).
- **Start screen** (if you have menus): which screen to open on (main menu, or a screen deep in the menu tree so a joining copy starts where the viewer needs it).
- **Menu walk** (if you have menus): a list of menu items to select in order ("Play,Multiplayer,Host a game"), with a highlight pause before each press (about 0.7 s) and a short wait after (about 0.8 s). It should WAIT for the release signal file before starting.
- **Clean settings** (if you save settings): a switch that ignores the developer's saved settings (volume, graphics options, an idle "pause when nothing happens" feature), so the take is the same on every machine.
- **Autopilot behaviour for shooters and action games**: make the player invincible in the dev build, pulse the fire button instead of holding it, check line of sight before aiming, and guard against falling or getting stuck.
- **Release gate** (required, even with no menus): the game holds itself, frozen or on its first screen, until the release file appears. This is what makes the game's timing line up with the start of the recording: OBS has to be recording before the show starts.
- **Joiners and discovery** (if you have multiplayer): joiners start BEFORE the host, so decide how a joiner can show the host's game appearing. If your game has a live session browser, park the joiner on it (cue `browser-open`) and it will list the host's game by itself. If the search is a one-shot snapshot (press Find, get a list), park the joiner just before the search and use two signals: `find-<Name>` (press Find once the host is in its lobby), wait for the `session-visible` cue, then `go-<Name>` (select and join). See the story pattern in `config.md`.
- **Signal files**: paths the copy polls: a "go" file (a joining copy presses Join when it appears), a "start" file (the host presses Start), a "release" file (the host begins its menu walk).

Several windows on a small screen: stack them with only part of the lower ones visible, or overlap them, but check in a test take that each OBS scene still delivers frames; a covered window may stall, and that is only visible in a real recording.

## 2. Output: cue lines

Print to stdout, one per line, flushed:

```
[anything] cue <name> unix-ms <milliseconds since the Unix epoch>
```

The scripts only look for `cue <name> unix-ms <n>`. Print one at every story beat you might cut on or wait for: `browser-open` (parked and ready), `session-visible`, `join-highlight`, `join-pressed`, `joined`, `ready`, `host-lobby`, `match-start`, `game-over`. Use wall-clock time, not game time: `edit.py` subtracts the recording's start time from these stamps.

## 3. Behaviour rules

- **Unique window title** (required): set the window title to something only this game has (for example the game name), because `window_match` in the config is matched against it and you cannot check it without OBS running.
- **No idle pause**: a copy waiting in a menu must not pop up a Paused screen or sleep.
- **Focus** (required with several windows): only one window has the keyboard focus, and an unfocused one may draw its menus without a highlight, ignore input or sleep. In the dev build force the game to act as focused and turn off the inactive sleep.
- **Menu sounds** (if your game has any; check first, by pressing through the menus yourself: some games have none, and then the first seconds are silent by design) **must play** for scripted actions. If your sound code is called from the input handler, a scripted press skips it: route the scripted press through the same cue call, or the first 20 seconds of the trailer are silent.
- **Quit by itself** (required; without it the take hangs until the watchdog): when the show or match is over, and at a hard cap so a stuck one ends. The host quitting ends the take, so give joiners a shorter quit delay than the host (a joiner leaving first can trigger an "opponent left" screen on the host).
- **Visible highlight** before each scripted press: the viewer needs to see what is being chosen. Pace it like a player who knows what they want.
- **Dev-only tweaks to look better** (bigger name labels, a hop timed to dodge a shot, a nicer level) go behind the same compile switch, never into release play.
- **A real network match, if there are several players.** It is more convincing than a canned replay, it tests your code, and every copy sees the other copies' ships.

## 4. What makes the story feel right

Show a human-readable sequence, not a feature list: host picks the mode; cut to a second player who sees the host's game appear and joins; quick cuts to the others; back to the host's lobby with everyone present; the match; the result screen. Keep menu steps about 1.5 s each at most; cut the dead wait before the host presses Start in the edit; pick the calmest level and a short score limit so the AI looks good and the take is short.
