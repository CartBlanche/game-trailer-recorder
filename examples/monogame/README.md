# Example: MonoGame (C#), a four-player pretend LAN match

This is the config used for the real trailer of Vector Rumble, a vector-graphics space shooter built with MonoGame (C#). The game's own dev harness is the model for `references/monogame-example.md`. Four copies of the game run on one Mac as four windows, each its own OBS scene.

`trailer.json` here is that config.

The story: the host picks Play, Multiplayer, Host a game; cut to the first joiner, whose Multiplayer screen shows the host's game appearing, who joins; quick cuts to the second and third joiners; back to the host's lobby with all four ships; the host starts; the battle (first to 5 kills, AI flies every ship) and the victory screen. The edit then cuts the wait before Start, adds a "COMING UP..." card and a short kill teaser at the start.

The names (Alex, John, Jane, Alison, and the credits) are placeholders: put the real names the video should show. The arena and ships are picked by the game's own settings (`VR_PICK`, `VR_SHIP`, `VR_COLOUR`): look up your own game's values, do not copy these.

How to read it:
- `env` and each instance's `env` are the game's own dev-harness variables (the `VR_` ones are specific to this game; yours will differ). See `references/harness-contract.md` for what a game's harness must provide.
- `instances` are in launch order; the joiners start first and park on the Multiplayer screen (their `ready_cue`), the host (last) starts after them.
- `story` is the director's script: cut, wait for a cue, sleep, signal (touch a file the game polls).
- `edit` is read by `scripts/edit.py`.

Run it from the game's project root, with the game built with its dev switch:

    python3 -I <skill>/scripts/record.py examples/monogame/trailer.json --work video/dry --cap 300      # a dry run, no OBS
    OBS_PASSWORD=... python3 -I <skill>/scripts/record.py trailer.json --obs                                   # a recording
    python3 -I <skill>/scripts/edit.py trailer.json "<recording>.mov" --kill-at 100                             # the edit
