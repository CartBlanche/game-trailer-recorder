# Other engines: Godot (untested sketch)

The scripts need only four things from a game, whatever engine it uses:

1. It starts from one command (the config's `launch`), several copies at once.
2. It reads settings from environment variables (or command line arguments, if you put them in `launch`).
3. It prints cue lines to standard output: `cue <name> unix-ms <n>`.
4. It can place and size its window, set a unique window title, play from a script, and quit by itself.

Everything else (OBS, cuts, edit) is the same. Unity has a full run: see [`unity.md`](unity.md). The Godot section below is untested; check API names against your engine version.

## Godot (4.x)

- **Dev switch:** run a dev scene or an autoload only when a user argument is present: `OS.get_cmdline_user_args()` (arguments after `--`), or `OS.has_feature("trailer")` with a custom feature tag set in an export preset.
- **Settings:** `OS.get_environment("TRAILER_SEED")`. Starting several copies of the exported binary (or `godot --path <project>`) is fine.
- **Cue lines:** `print("cue %s unix-ms %d" % [name, int(Time.get_unix_time_from_system() * 1000.0)])` goes to standard output.
- **Window:** `DisplayServer.window_set_size(Vector2i(w, h))`, `DisplayServer.window_set_position(Vector2i(x, y))`, `DisplayServer.window_set_title("MyGame")`.
- **Autopilot:** an autoload with `await get_tree().create_timer(0.7).timeout` between steps, and a loop that waits for a file to appear (`FileAccess.file_exists(path)`). For menus, call `grab_focus()` on the Button, wait, then `emit_signal("pressed")`.
- **Quit:** `get_tree().quit()`.
- **Focus:** `Engine.max_fps` and low-processor mode can slow an unfocused window: turn them off in the dev build (`OS.low_processor_usage_mode = false`).

## What to expect

Most of the effort is the harness, as in the C# MonoGame examples: the menu walk, the release gate, signal files, the quit timer, and the cue lines. Use [`monogame-example.md`](monogame-example.md) or [`unity.md`](unity.md) as the shape of it (the wait-script is the same idea in every engine), and keep the rest of [`harness-contract.md`](harness-contract.md) as the checklist.
