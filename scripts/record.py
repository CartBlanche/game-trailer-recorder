#!/usr/bin/env python3
"""Records a scripted gameplay trailer: starts one copy of the game per "player", points OBS at each window, records, and cuts
between the scenes by following the games' own cue lines. Everything about the game and the story is in a trailer.json.

  OBS_PASSWORD=... record.py <trailer.json> [--obs] [--no-build] [--env KEY=VALUE ...]

  --obs          drive OBS: make the scenes, record, cut, stop when the host game quits. Needs OBS_PASSWORD (never stored) and
                 optionally OBS_HOST / OBS_PORT. Without --obs the games just play the script, which is how you check a story
                 and its cues (no recording, no OBS needed). Do this first, many times.
  --no-build     skip the "build" command of the config
  --cap S        stop everything after S seconds (default: the config's max_seconds + 90). Use a small one on dry runs so a stuck
                 game cannot hang for minutes; the games should quit by themselves well before it
  --work DIR     use this work folder instead of the config's work_dir (so a test run does not overwrite a take's logs)
  --env K=V      set an environment variable for every copy of the game (wins over the config), e.g. a seed or a level

Run it from the project's root folder (paths in the config are relative to where you run it), in a terminal, with the display awake.
The files go in the config's "work_dir": <Name>.log per copy (with the cue lines), timing.txt, and the signal files.
See references/config.md for every key of the config.
"""
import json, os, re, shlex, signal, subprocess, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs as obsmod

CUE = re.compile(r"cue (\S+) unix-ms (\d+)")


def die(msg):
    print("record.py: " + msg, file=sys.stderr)
    sys.exit(1)


class Run:
    def __init__(self, cfg, use_obs, build, extra_env, cap=None):
        self.cfg = cfg
        self.use_obs = use_obs
        self.build = build
        self.extra_env = extra_env
        self.cap = cap
        self.t0_unix = time.time()
        self.t0 = time.time()
        self.work = os.path.abspath(cfg.get("work_dir", "video"))
        self.procs = {}
        self.recording = False
        self.watchdog = None
        self.stop = threading.Event()
        self.missed = []
        self.prev_scene = None
        self.rec_started = None
        self.obs = None
        self.names = [i["name"] for i in cfg["instances"]]
        self.host = cfg["instances"][-1]

    # ---- files, logs, cues -------------------------------------------------------------------------------------------
    def path(self, name):
        return os.path.join(self.work, name)

    def log_text(self, name):
        try:
            return open(self.path(name + ".log"), errors="replace").read()
        except OSError:
            return ""

    def cues(self, name):
        return [m.group(1) for m in CUE.finditer(self.log_text(name))]

    def wait_cue(self, name, cue, timeout):
        begin = time.time()
        end = begin + timeout
        while time.time() < end and not self.stop.is_set():
            if cue in self.cues(name):
                print("record: [%6.1fs] waited %.1fs for %s:%s" % (time.time() - self.t0, time.time() - begin, name, cue), flush=True)
                return True
            time.sleep(0.1)
        if not self.stop.is_set():
            print("record: !!! MISSED CUE: no %r from %s after %ds, carrying on" % (cue, name, timeout), file=sys.stderr, flush=True)
            self.missed.append("%s:%s" % (name, cue))
        return False

    def echo_cues(self):
        """Print every cue line the games print, with the seconds since the start, so a dry run can be read at a glance."""
        seen = set()
        while not self.stop.is_set():
            for n in self.names:
                for i, m in enumerate(CUE.finditer(self.log_text(n))):
                    if (n, i) not in seen:
                        seen.add((n, i))
                        print("record: [%6.1fs] %s cue %s" % (time.time() - self.t0, n, m.group(1)), flush=True)
            time.sleep(0.2)

    def sub(self, text, inst):
        return (text.replace("{work}", self.work).replace("{name}", inst["name"]).replace("{window}", inst.get("window", "")))

    # ---- the games ---------------------------------------------------------------------------------------------------
    def launch(self, inst):
        env = dict(os.environ)
        for k, v in list(self.cfg.get("env", {}).items()) + list(inst.get("env", {}).items()):
            env[k] = self.sub(str(v), inst)
        env.update(self.extra_env)
        log = open(self.path(inst["name"] + ".log"), "ab")
        cmd = shlex.split(self.cfg["launch"])
        print("record: starting %s" % inst["name"], flush=True)
        self.procs[inst["name"]] = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        time.sleep(self.cfg.get("start_gap", 0.8))   # so the windows have ascending ids, in launch order

    def kill_games(self):
        for p in self.procs.values():
            if p.poll() is None:
                p.terminate()

    # ---- OBS ---------------------------------------------------------------------------------------------------------
    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        time.sleep(2)
        out = ""
        try:
            out = self.obs.request("StopRecord").get("outputPath", "")
        except (RuntimeError, OSError) as e:
            print("record: could not stop OBS: %s (stop it by hand!)" % e, file=sys.stderr)
        print("Recording: %s" % out, flush=True)
        with open(self.path("timing.txt"), "a") as f:
            f.write("recording_file=%s\n" % out)
        if out:
            # OBS finishes writing the file a moment after "stop": try for up to 30 s
            for _ in range(15):
                r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height",
                                    "-show_entries", "format=duration", "-of", "compact", out], capture_output=True, text=True)
                if r.returncode == 0 and r.stdout.strip():
                    print(r.stdout.strip(), flush=True)
                    break
                time.sleep(2)

    def cleanup(self):
        self.stop.set()
        if self.watchdog:
            self.watchdog.cancel()
        self.stop_recording()
        self.kill_games()
        if self.obs and self.prev_scene:
            try:
                self.obs.request("SetCurrentProgramScene", {"sceneName": self.prev_scene})
            except (RuntimeError, OSError):
                pass
        if self.obs:
            self.obs.close()

    # ---- the story ---------------------------------------------------------------------------------------------------
    def cut(self, name):
        if self.obs:
            self.obs.request("SetCurrentProgramScene", {"sceneName": obsmod.scene_of(name)})
        print("record: cut to %s" % name, flush=True)

    def tell_story(self):
        for step in self.cfg["story"]:
            if self.stop.is_set():
                return
            if "cut" in step:
                self.cut(step["cut"])
            elif "wait" in step:
                who, cue = step["wait"].split(":", 1)
                self.wait_cue(who, cue, step.get("timeout", 30))
            elif "sleep" in step:
                time.sleep(step["sleep"])
            elif "signal" in step:
                open(self.path(step["signal"]), "w").close()
            else:
                print("record: unknown story step %r" % (step,), file=sys.stderr)
        print("record: story finished", flush=True)

    def print_timeline(self):
        """A table of every cue each copy printed, in order, as seconds since the start: easy to check the order is sane."""
        base = self.rec_started or self.t0_unix
        print("record: cue timeline (seconds since %s):" % ("the RECORDING started: these match the video and edit.py" if self.rec_started else "the run started"))
        for n in self.names:
            stamps = []
            for m in CUE.finditer(self.log_text(n)):
                stamps.append((int(m.group(2)) / 1000.0, m.group(1)))
            if stamps:
                first = min(t for t, _ in stamps)
                print("  %-10s %s" % (n, "  ".join("%s %+.1f" % (c, t - base) for t, c in stamps)))

    # ---- the whole take ----------------------------------------------------------------------------------------------
    def go(self):
        cfg = self.cfg
        self.t0 = time.time()
        self.t0_unix = self.t0
        os.makedirs(self.work, exist_ok=True)
        if self.build and cfg.get("build"):
            subprocess.run(cfg["build"], shell=True, check=True)
        if self.use_obs:
            if not os.environ.get("OBS_PASSWORD"):
                die("--obs needs the OBS_PASSWORD environment variable (the OBS WebSocket password): export it in this shell first (never as an argument), and make sure OBS is running with its WebSocket server on")
            obsmod.WINDOW_MATCH = cfg["window_match"]
            obsmod.PREFIX = cfg.get("scene_prefix", obsmod.PREFIX)
            obsmod.TITLE_BAR = int(cfg.get("title_bar_crop", obsmod.TITLE_BAR))
            self.obs = obsmod.Obs(os.environ.get("OBS_HOST", "localhost"), int(os.environ.get("OBS_PORT", "4455")),
                                  os.environ["OBS_PASSWORD"])
            self.prev_scene = self.obs.request("GetSceneList").get("currentProgramSceneName")   # put back when the take is over
            # fail early, and never touch a recording somebody else started
            if self.obs.request("GetRecordStatus")["outputActive"]:
                die("OBS is already recording: stop that first (this script only stops a recording it started)")
            for mic in cfg.get("mute_inputs", ["Mic/Aux"]):
                try:
                    self.obs.request("SetInputMute", {"inputName": mic, "inputMuted": True})
                except RuntimeError:
                    pass

        pattern = cfg.get("kill_pattern")
        if pattern and subprocess.run(["pkill", "-f", pattern], capture_output=True).returncode == 0:
            print("record: stopped a leftover game window", file=sys.stderr)
            time.sleep(2)

        # fresh signals for the copies and the story, empty logs, fresh timing
        signals = {s["signal"] for s in cfg["story"] if "signal" in s} | {cfg["release_file"]} | set(cfg.get("signals", []))
        for s in signals:
            try:
                os.remove(self.path(s))
            except OSError:
                pass
        for n in self.names:
            open(self.path(n + ".log"), "w").close()
        with open(self.path("timing.txt"), "w") as f:
            f.write("script=%s\n" % cfg.get("name", "trailer"))

        # 1) every copy but the host first, each parked where it waits; 2) the host last (so it has the highest window id)
        for inst in cfg["instances"][:-1]:
            self.launch(inst)
        for inst in cfg["instances"][:-1]:
            cue = inst.get("ready_cue")
            if cue and not self.wait_cue(inst["name"], cue, inst.get("ready_timeout", 60)):
                die("%s never printed the %r cue (look at %s)" % (inst["name"], cue, self.path(inst["name"] + ".log")))
        self.launch(self.host)

        # the watchdog: whatever goes wrong, the games (and so the recording) end after the cap
        cap = self.cap if self.cap else cfg.get("max_seconds", 420) + 90
        def too_long():
            print("record: !!! hit the watchdog limit of %ds and stopped the games (exit code -15 means this killed them): raise --cap above the length of the whole show" % cap, file=sys.stderr, flush=True)
            self.kill_games()
        self.watchdog = threading.Timer(cap, too_long)
        self.watchdog.daemon = True
        self.watchdog.start()
        threading.Thread(target=self.echo_cues, daemon=True).start()

        time.sleep(cfg.get("settle_seconds", 4))
        if self.use_obs:
            obsmod.bind_all(self.obs, self.names)
            self.cut(self.host["name"])
            started = time.time()
            self.rec_started = started
            self.obs.request("StartRecord")
            self.recording = True
            with open(self.path("timing.txt"), "a") as f:
                f.write("recording_started_unix=%.3f\n" % started)
        time.sleep(cfg.get("pre_roll", 1.5))     # a moment of the first screen before the host starts moving
        open(self.path(cfg["release_file"]), "w").close()

        story = threading.Thread(target=self.tell_story, daemon=True)
        story.start()
        # the host quits by itself some seconds after the match ends (or at its own cap); then stop everything
        code = self.procs[self.host["name"]].wait()
        print("record: [%6.1fs] the host game exited with code %s" % (time.time() - self.t0, code), flush=True)
        time.sleep(2)
        self.cleanup()
        story.join(timeout=5)
        self.print_timeline()
        if self.missed:
            print("record: !!! %d story cue(s) never came: %s" % (len(self.missed), ", ".join(self.missed)), file=sys.stderr)
        print("Done. Logs and timing are in %s" % self.work)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 1
    cfg_path, use_obs, build, extra, work, cap = argv[0], False, True, {}, None, None
    it = iter(argv[1:])
    for a in it:
        if a == "--obs":
            use_obs = True
        elif a == "--no-build":
            build = False
        elif a == "--cap":
            cap = float(next(it))
        elif a == "--work":
            work = next(it)
        elif a == "--env":
            k, _, v = next(it).partition("=")
            extra[k] = v
        else:
            die("unknown option " + a)
    cfg = json.load(open(cfg_path))
    if work:
        cfg["work_dir"] = work
    for key in ("launch", "instances", "story", "release_file"):
        if key not in cfg:
            die("the config has no %r" % key)
    if use_obs and "window_match" not in cfg:
        die("the config needs window_match (text in the game window's title) to use --obs")
    run = Run(cfg, use_obs, build, extra, cap)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        run.go()
    except KeyboardInterrupt:
        print("record: interrupted, cleaning up", file=sys.stderr)
        run.cleanup()
        return 130
    except BaseException:
        run.cleanup()
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
