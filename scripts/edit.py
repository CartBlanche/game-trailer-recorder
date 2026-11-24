#!/usr/bin/env python3
"""Turns the OBS recording that record.py made into the finished video, using the cue times from the games' logs.

  edit.py <trailer.json> <recording> [--kill-at S] [--out FILE] [--card TEXT | --no-card] [--no-cut]

  <recording>   the file OBS wrote (also on the "recording_file=" line of <work_dir>/timing.txt)
  --kill-at S   (or edit.teaser.cue in the config: a cue to centre on) the second of the recording where the best moment happens (a "kill"): the video opens with a short clip leading
                up to it, as a teaser. Without it there is no teaser, and the loudest sounds after the story's end cue are listed,
                so you can look at the frames around them (ffmpeg -ss T -i FILE -frames:v 1 x.png) and pick one.
  --card TEXT   the title card shown before the teaser (default from the config, "COMING UP..."); --no-card leaves it out
  --no-cut      keep the dead wait that the config's "cut" would remove
  --work DIR    the work folder of that take (default: the config's work_dir): the logs and timing.txt that record.py wrote
  --out FILE    default: "<the recording's name> final.mp4" next to the recording

Config "edit.credits" adds a closing (or opening) card of lines such as "Directed by ..." and "Implemented by ...".
At the end it follows the scoreboard: the picture holds, fades to black, the card fades in, and the game's own sound carries on under
it and fades out (so the recording must run on a few seconds past the end of the match).

The recipe, in order: title card (fades in and out, silent) | teaser (fades in, dips to black, its sound fades out) | the recording,
with the dead wait cut out and the sound joined with a short crossfade. One pass, 1080p 60 fps H.264 (crf 18) and AAC.
Needs ffmpeg, ffprobe, python3, and Chrome for the card (set CHROME to its binary if it is not found).
See references/config.md ("edit") for the config keys.
"""
import array, html as htmllib, json, math, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CUE = re.compile(r"cue (\S+) unix-ms (\d+)")


def probe(*a):
    return subprocess.check_output(a).decode().strip()


def find_chrome():
    for c in (os.environ.get("CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chrome")):
        if c and os.path.exists(c):
            return c
    return None


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cfg = json.load(open(argv[0]))
    ed = cfg.get("edit", {})
    rec_file, kill_at, out, cut, work_arg = None, None, None, True, None
    card = ed.get("card", {}).get("text", "COMING UP...") if ed.get("card", True) is not False else None
    it = iter(argv[1:])
    for a in it:
        if a == "--kill-at": kill_at = float(next(it))
        elif a == "--out": out = next(it)
        elif a == "--work": work_arg = next(it)
        elif a == "--card": card = next(it)
        elif a == "--no-card": card = None
        elif a == "--no-cut": cut = False
        elif a.startswith("--"): sys.exit("Unknown option: " + a)
        else: rec_file = a
    if not rec_file:
        print(__doc__)
        return 1
    work = os.path.abspath(work_arg or cfg.get("work_dir", "video"))
    out = out or re.sub(r"\.[^.]+$", "", rec_file) + " final.mp4"

    # the cue times, as seconds into the recording
    timing = open(os.path.join(work, "timing.txt")).read()
    rec_start = float(re.search(r"recording_started_unix=([\d.]+)", timing).group(1))

    def cues(name):
        found = {}
        path = os.path.join(work, name + ".log")
        if os.path.exists(path):
            for line in open(path, errors="replace"):
                m = CUE.search(line)
                if m:
                    found.setdefault(m.group(1), []).append(int(m.group(2)) / 1000.0 - rec_start)
        return found

    cut_cfg = ed.get("cut")
    a_cut = b_cut = None
    end_time = 0.0       # where the story's dead wait ends: the loudest sounds are listed after it
    if cut_cfg:
        s, e = cut_cfg["start"], cut_cfg["end"]
        starts = [t for n in s["players"] for t in cues(n).get(s["cue"], [])]
        ends = cues(e["player"]).get(e["cue"], [])
        if not ends:
            sys.exit("No %r cue in %s: was this the recording that the work folder describes?" % (e["cue"], os.path.join(work, e["player"] + ".log")))
        end_time = ends[0]
        if starts:
            a_cut = (max(starts) if s.get("pick", "last") == "last" else min(starts)) + s.get("offset", 0.0)
            b_cut = end_time + e.get("offset", 0.0)
    duration = float(probe("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", rec_file))

    tzc = ed.get("teaser", {}).get("cue")
    if kill_at is None and tzc:     # the teaser is centred on a cue the game printed (for example the hero peeking out of cover)
        hits = cues(tzc["player"]).get(tzc["cue"], [])
        if not hits:
            sys.exit("No %r cue in %s.log for the teaser" % (tzc["cue"], tzc["player"]))
        kill_at = hits[0] + float(tzc.get("offset", 0.0))
        print("Teaser centred on the %r cue at %.2f s" % (tzc["cue"], kill_at))

    if kill_at is None:
        pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", rec_file, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"])
        a = array.array("h"); a.frombytes(pcm)
        win = 400
        env = [(i * 0.05, math.sqrt(sum(x * x for x in a[i * win:(i + 1) * win]) / win)) for i in range(len(a) // win)]
        loud = sorted((e for e in env if e[0] > end_time + 2), key=lambda e: -e[1])
        picked = []
        for t, v in loud:
            if all(abs(t - p) > 2 for p, _ in picked):
                picked.append((t, v))
            if len(picked) == 8:
                break
        print("No --kill-at, so no teaser. The loudest sounds after the story's end cue (seconds, level):")
        for t, v in sorted(picked):
            print("  %6.2f s  %d" % (t, v))
        print("Look at the frames around one (ffmpeg -ss T -i FILE -frames:v 1 x.png): pick a moment with a build-up before it.")

    tmp = tempfile.mkdtemp(prefix="trailer-edit-")
    chrome = None

    def render_card(name, lines, cc, size, spacing):
        nonlocal chrome
        chrome = chrome or find_chrome()
        if not chrome:
            sys.exit("Chrome not found for the cards (set CHROME, or use --no-card and leave out credits)")
        font = cc.get("font")
        face = ('@font-face{font-family:CardFont;src:url("file://%s")}' % os.path.abspath(font)) if font else ""
        family = "CardFont" if font else "Helvetica Neue, Arial, sans-serif"
        html = open(os.path.join(HERE, "card.html")).read()
        text = "<br>".join(htmllib.escape(l) for l in lines)
        for k, v in (("{{FONT_FACE}}", face), ("{{FAMILY}}", family), ("{{COLOR}}", cc.get("color", "#ff9a1f")),
                     ("{{SIZE}}", str(cc.get("size", size))), ("{{SPACING}}", str(spacing)), ("{{TEXT}}", text)):
            html = html.replace(k, v)
        open(os.path.join(tmp, name + ".html"), "w").write(html)
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--window-size=1920,1080", "--virtual-time-budget=2000", "--screenshot=" + os.path.join(tmp, name + ".png"),
                        "file://" + os.path.join(tmp, name + ".html")], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return os.path.join(tmp, name + ".png")

    if card:
        cc = ed.get("card", {}) if isinstance(ed.get("card"), dict) else {}
        card_png = render_card("card", [card], cc, 190, 10)

    cr = ed.get("credits")
    credits_png = None
    cr_secs = cr_main_end = 0.0
    if cr:
        cr_secs = float(cr.get("seconds", 4.0))
        lines = list(cr["lines"]) if "lines" in cr else \
            [l for l in ("Directed by " + cr["directed_by"] if cr.get("directed_by") else None,
                         "Implemented by " + cr["implemented_by"] if cr.get("implemented_by") else None) if l]
        if not lines:
            sys.exit('edit.credits needs "lines", or "directed_by" and/or "implemented_by"')
        credits_png = render_card("credits", lines, cr, 64, 4)
        if cr.get("at", "end") == "end":
            af = cr.get("after")
            if af:
                hits = cues(af["player"]).get(af["cue"], [])
                if not hits:
                    sys.exit("No %r cue in %s.log for credits.after" % (af["cue"], af["player"]))
                cr_main_end = hits[0] + float(af.get("hold", 5.0))
            else:
                cr_main_end = duration - cr_secs
            if cr_main_end + cr_secs > duration + 0.05:
                sys.exit("The recording is %.1f s long but the credits need it to run to %.1f s (the picture holds to %.1f s, then %.1f s of card "
                         "with the game's sound underneath). Make the game keep running longer after the end (its quit-after-over delay) or shorten hold/seconds."
                         % (duration, cr_main_end + cr_secs, cr_main_end, cr_secs))

    tz = ed.get("teaser", {})
    before, length = tz.get("before", 2.55), tz.get("length", 3.3)
    cmd = ["ffmpeg", "-v", "error", "-y"]
    idx = 0
    chain = []

    def inp(*a):
        nonlocal idx
        cmd.extend(a); idx += 1
        return idx - 1

    final = []
    if cr and cr.get("at", "end") == "start":
        c0 = inp("-loop", "1", "-framerate", "60", "-t", "%.2f" % cr_secs, "-i", credits_png)
        s0 = inp("-f", "lavfi", "-t", "%.2f" % cr_secs, "-i", "anullsrc=r=48000:cl=stereo")
        chain.append(f"[{c0}:v]fps=60,format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st={cr_secs - 0.4:.2f}:d=0.4,setpts=PTS-STARTPTS[xv]")
        chain.append(f"[{s0}:a]aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[xa]")
        final += ["[xv]", "[xa]"]
    if card:
        c = inp("-loop", "1", "-framerate", "60", "-t", "1.0", "-i", card_png)
        s_ = inp("-f", "lavfi", "-t", "1.0", "-i", "anullsrc=r=48000:cl=stereo")
        chain.append(f"[{c}:v]fps=60,format=yuv420p,fade=t=in:st=0:d=0.25,fade=t=out:st=0.75:d=0.25,setpts=PTS-STARTPTS[cv]")
        chain.append(f"[{s_}:a]aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[ca]")
        final += ["[cv]", "[ca]"]
    if kill_at is not None:
        start = max(0.0, kill_at - before)
        t = inp("-ss", "%.3f" % start, "-t", "%.3f" % length, "-i", rec_file)
        chain.append(f"[{t}:v]fps=60,format=yuv420p,fade=t=in:st=0:d=0.2,fade=t=out:st={length - 0.4:.2f}:d=0.4,setpts=PTS-STARTPTS[tv]")
        chain.append(f"[{t}:a]aresample=48000,aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.1,afade=t=out:st={length - 0.7:.2f}:d=0.7,asetpts=PTS-STARTPTS[ta]")
        final += ["[tv]", "[ta]"]
    m = inp("-i", rec_file)
    cut_done = False
    if cut and a_cut is not None and b_cut > a_cut + 0.5:
        print("Cutting %.2f s to %.2f s (%.2f s of dead wait)" % (a_cut, b_cut, b_cut - a_cut))
        chain.append(f"[{m}:v]split=2[m1][m2]")
        chain.append(f"[m1]trim=0:{a_cut:.3f},setpts=PTS-STARTPTS[m1v]")
        chain.append(f"[m2]trim=start={b_cut:.3f},setpts=PTS-STARTPTS[m2v]")
        chain.append("[m1v][m2v]concat=n=2:v=1:a=0,fps=60,format=yuv420p,fade=t=in:st=0:d=0.3[mv]")
        chain.append(f"[{m}:a]asplit=2[a1][a2]")
        chain.append(f"[a1]atrim=0:{a_cut:.3f},asetpts=PTS-STARTPTS[a1t]")
        chain.append(f"[a2]atrim=start={b_cut:.3f},asetpts=PTS-STARTPTS[a2t]")
        chain.append("[a1t][a2t]acrossfade=d=0.08,aresample=48000,aformat=channel_layouts=stereo[ma]")
        cut_done = True
    if not cut_done:
        chain.append(f"[{m}:v]fps=60,format=yuv420p,fade=t=in:st=0:d=0.3,setpts=PTS-STARTPTS[mv]")
        chain.append(f"[{m}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[ma]")
    if cr and cr.get("at", "end") == "end":
        removed = (b_cut - a_cut) if cut_done and cr_main_end > b_cut else 0.0
        te = cr_main_end - removed
        print("Credits: the picture holds to %.2f s, then %.1f s of card over the fading game sound" % (cr_main_end, cr_secs))
        chain.append(f"[mv]trim=0:{te:.3f},setpts=PTS-STARTPTS,fade=t=out:st={te - 0.6:.3f}:d=0.6[mvt]")
        chain.append("[ma]asplit=2[mb][mc]")
        chain.append(f"[mb]atrim=0:{te:.3f},asetpts=PTS-STARTPTS[mat]")
        chain.append(f"[mc]atrim=start={te:.3f}:end={te + cr_secs:.3f},asetpts=PTS-STARTPTS,afade=t=out:st=0:d={cr_secs:.3f}[tail]")
        k = inp("-loop", "1", "-framerate", "60", "-t", "%.2f" % cr_secs, "-i", credits_png)
        chain.append(f"[{k}:v]fps=60,format=yuv420p,fade=t=in:st=0:d=0.6,fade=t=out:st={cr_secs - 0.5:.2f}:d=0.5,setpts=PTS-STARTPTS[kv]")
        final += ["[mvt]", "[mat]", "[kv]", "[tail]"]
    else:
        final += ["[mv]", "[ma]"]
    chain.append("".join(final) + f"concat=n={len(final) // 2}:v=1:a=1[v][a]")
    cmd += ["-filter_complex", ";".join(chain), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    print("Wrote %s (%.1f s)" % (out, float(probe("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
