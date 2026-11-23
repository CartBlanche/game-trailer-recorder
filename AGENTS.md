# Instructions for AI coding agents

This repository is a toolkit for recording a scripted gameplay trailer. If the user asks for a trailer, gameplay video, promo clip or automated demo recording of their game, read `SKILL.md` and follow it, then read the files in `references/` that it points to when you reach those steps. The scripts in `scripts/` are plain Python 3 (standard library only); run them with `python3 -I`.

Ground rules (they are explained in `SKILL.md`):
- Never ask the user to paste the OBS password into the chat, and never write it into a file or a command line. It is read from the `OBS_PASSWORD` environment variable only.
- Do not start or stop an OBS recording you did not start, and never leave one running.
- Dry-run first (no `--obs`), and show the user frames or a take before committing anything.
- Commit only when the user asks.
