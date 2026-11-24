#!/usr/bin/env python3
"""Tiny OBS remote control (obs-websocket v5), standard library only. Generic: it knows nothing about any one game.

  OBS_PASSWORD=... obs.py [--host H] [--port P] <command> [args]

  version            OBS and websocket versions
  status             is it recording, and for how long
  scenes             list scenes (current one marked)
  scene <name>       switch to a scene (made if missing)
  start              start recording
  stop               stop recording, prints the file it wrote
  folder [path]      show or set the recording folder
  windows            list the windows OBS can capture (to check the name your game's window has)
  transitions        list OBS's scene transitions (record.py sets one with the config "transition")
  bind-all <names>   one scene per name, each showing one game window, filling the canvas. Name them in the order the games were
                     STARTED: the windows are matched by window id, and the first game started has the lowest id.
  cut <name>         switch to that name's scene
  clean              remove every scene and source this tool made (names starting with OBS_SCENE_PREFIX), when you are done
  call <type> [json] any raw request, for everything else

Settings (environment variables):
  OBS_PASSWORD       the OBS WebSocket password (OBS > Tools > WebSocket Server Settings). Only ever read from here, never stored.
  OBS_HOST / OBS_PORT  default localhost:4455
  OBS_WINDOW_MATCH   text that the window's "[process] title" must contain (required by windows/bind-all), for example the game's name
  OBS_SCENE_PREFIX   scenes are "<prefix> - <name>"; sources are "<prefix> window - <name> <run>" (default "Trailer").
                     OBS source names are global to the whole OBS: pick a prefix that is yours, only sources and scenes starting
                     with it are ever made, changed or removed.
  OBS_TITLE_BAR      capture pixels of window title bar to crop off the top (default 56: a 28 point title bar on a 2x Retina screen)

Sound: a window capture carries the game's own sound. Keep the mic (Mic/Aux) muted.
Never ask OBS for the property list of an audio-capture input (sck_audio_capture): that crashed OBS once. Only the window-list
helper source made here is ever asked.
"""
import base64, hashlib, json, os, socket, struct, sys, time, uuid


class Obs:
    def __init__(self, host, port, password, timeout=10):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self._handshake(host, port)
        hello = self._recv_json()
        if hello.get("op") != 0:
            raise RuntimeError("unexpected greeting: %r" % hello)
        ident = {"rpcVersion": 1, "eventSubscriptions": 0}
        auth = hello["d"].get("authentication")
        if auth:
            if not password:
                raise RuntimeError("OBS wants a password: set OBS_PASSWORD")
            secret = base64.b64encode(hashlib.sha256((password + auth["salt"]).encode()).digest()).decode()
            ident["authentication"] = base64.b64encode(
                hashlib.sha256((secret + auth["challenge"]).encode()).digest()).decode()
        self._send_json({"op": 1, "d": ident})
        reply = self._recv_json()
        if reply.get("op") != 2:
            raise RuntimeError("login refused: %r" % reply)

    def request(self, kind, data=None):
        rid = uuid.uuid4().hex
        msg = {"requestType": kind, "requestId": rid}
        if data:
            msg["requestData"] = data
        self._send_json({"op": 6, "d": msg})
        while True:
            reply = self._recv_json()
            if reply.get("op") == 7 and reply["d"].get("requestId") == rid:
                d = reply["d"]
                if not d["requestStatus"]["result"]:
                    raise RuntimeError("%s failed: %s" % (kind, d["requestStatus"].get("comment", d["requestStatus"])))
                return d.get("responseData") or {}

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    # -- minimal websocket framing (client side, text frames) --
    def _handshake(self, host, port):
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET / HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n"
                           "Sec-WebSocket-Protocol: obswebsocket.json\r\n\r\n" % (host, port, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise RuntimeError("connection closed during handshake")
            buf += chunk
        if b" 101 " not in buf.split(b"\r\n")[0]:
            raise RuntimeError("websocket upgrade refused: " + buf.split(b"\r\n")[0].decode())
        self._pending = buf.split(b"\r\n\r\n", 1)[1]

    def _read(self, n):
        while len(self._pending) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("connection closed")
            self._pending += chunk
        out, self._pending = self._pending[:n], self._pending[n:]
        return out

    def _send_json(self, obj):
        payload = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(payload)
        head = b"\x81" + (bytes([0x80 | n]) if n < 126 else b"\xfe" + struct.pack(">H", n) if n < 65536
                          else b"\xff" + struct.pack(">Q", n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _recv_json(self):
        message = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            data = self._read(n)
            opcode = b1 & 0x0F
            if opcode == 8:
                raise RuntimeError("OBS closed the connection: %r" % data[2:])
            if opcode in (9, 10):
                continue
            message += data
            if b1 & 0x80:
                return json.loads(message.decode())



PREFIX = os.environ.get("OBS_SCENE_PREFIX", "Trailer")
WINDOW_MATCH = os.environ.get("OBS_WINDOW_MATCH", "")
TITLE_BAR = int(os.environ.get("OBS_TITLE_BAR", "56"))


def scene_of(name):
    return "%s - %s" % (PREFIX, name)


def list_windows(obs):
    """[(id, "[process] title")] of the windows OBS can capture. A dedicated, disabled window-capture source lists them;
    its settings are forced to window mode each time, because a source left in another mode has no "window" property."""
    lister = PREFIX + " window-list"
    existing = {i["inputName"] for i in obs.request("GetInputList")["inputs"]}
    if PREFIX not in {s["sceneName"] for s in obs.request("GetSceneList")["scenes"]}:
        obs.request("CreateScene", {"sceneName": PREFIX})
    if lister not in existing:
        obs.request("CreateInput", {"sceneName": PREFIX, "inputName": lister, "inputKind": "screen_capture",
                                    "inputSettings": {"type": 1}, "sceneItemEnabled": False})
    obs.request("SetInputSettings", {"inputName": lister, "inputSettings": {"type": 1}})
    for _ in range(10):
        try:
            items = obs.request("GetInputPropertiesListPropertyItems",
                                {"inputName": lister, "propertyName": "window"})["propertyItems"]
            return [(int(i["itemValue"]), i["itemName"]) for i in items]
        except RuntimeError:
            time.sleep(0.5)
    raise RuntimeError("could not list the windows")


def bind_all(obs, names):
    """One scene per name, each showing that game's window, filling the canvas (title bar cropped)."""
    if not WINDOW_MATCH:
        raise RuntimeError("set OBS_WINDOW_MATCH to text in the game window's title (see the 'windows' command)")
    windows = sorted(w for w in list_windows(obs) if WINDOW_MATCH.lower() in w[1].lower())
    if len(windows) < len(names):
        raise RuntimeError("expected %d game windows matching %r, found %d: start the games first" % (len(names), WINDOW_MATCH, len(windows)))
    if len(windows) > len(names):
        print("note: %d windows match %r, using the %d with the lowest ids" % (len(windows), WINDOW_MATCH, len(names)), file=sys.stderr)
    video = obs.request("GetVideoSettings")
    width, height = video["baseWidth"], video["baseHeight"]
    scenes = {s["sceneName"] for s in obs.request("GetSceneList")["scenes"]}
    # the sources of earlier runs go (only ours: they start with this prefix); a name that was just removed stays busy for a
    # while, so each run's sources get a name of their own
    for i in obs.request("GetInputList")["inputs"]:
        if i["inputName"].startswith(PREFIX + " window - "):
            try:
                obs.request("RemoveInput", {"inputName": i["inputName"]})
            except RuntimeError:
                pass
    run = str(int(time.time()))
    # the windows are in the order the games were started, and the names are given in that order
    for (window, _), name in zip(windows, names):
        scene = scene_of(name)
        source = "%s window - %s %s" % (PREFIX, name, run)
        if scene not in scenes:
            obs.request("CreateScene", {"sceneName": scene})
        # a fresh source every run: an existing one pointed at a new window can sit at 0x0 and never deliver frames
        item = obs.request("CreateInput", {"sceneName": scene, "inputName": source, "inputKind": "screen_capture",
            "inputSettings": {"type": 1, "window": window, "show_cursor": False}, "sceneItemEnabled": True})["sceneItemId"]
        for _ in range(20):
            time.sleep(0.5)
            got = obs.request("GetSceneItemTransform", {"sceneName": scene, "sceneItemId": item})["sceneItemTransform"]
            if got["sourceWidth"] > 0:
                break
        else:
            raise RuntimeError("%s never started delivering frames (window %d): is it visible?" % (source, window))
        src_w, src_h = got["sourceWidth"], got["sourceHeight"] - TITLE_BAR
        scale = min(width / src_w, height / src_h)
        obs.request("SetSceneItemTransform", {"sceneName": scene, "sceneItemId": item, "sceneItemTransform": {
            "positionX": (width - src_w * scale) / 2, "positionY": (height - src_h * scale) / 2,
            "scaleX": scale, "scaleY": scale, "cropTop": TITLE_BAR, "cropLeft": 0, "cropRight": 0, "cropBottom": 0,
            "alignment": 5, "boundsType": "OBS_BOUNDS_NONE"}})
        print("%s: window %d, %dx%d at %.2fx" % (name, window, src_w, src_h, scale))


def clean(obs):
    """Remove the scenes and sources made under PREFIX (and nothing else), so the user's OBS is left as it was."""
    for i in obs.request("GetInputList")["inputs"]:
        if i["inputName"].startswith(PREFIX + " window"):
            try:
                obs.request("RemoveInput", {"inputName": i["inputName"]})
                print("removed source", i["inputName"])
            except RuntimeError as e:
                print("could not remove %s: %s" % (i["inputName"], e), file=sys.stderr)
    for sc in obs.request("GetSceneList")["scenes"]:
        n = sc["sceneName"]
        if n == PREFIX or n.startswith(PREFIX + " - "):
            try:
                obs.request("RemoveScene", {"sceneName": n})
                print("removed scene", n)
            except RuntimeError as e:
                print("could not remove %s: %s (switch OBS to another scene first)" % (n, e), file=sys.stderr)


def main(argv):
    host = os.environ.get("OBS_HOST", "localhost")
    port = int(os.environ.get("OBS_PORT", "4455"))
    args = []
    it = iter(argv)
    for a in it:
        if a == "--host":
            host = next(it)
        elif a == "--port":
            port = int(next(it))
        else:
            args.append(a)
    if not args:
        print(__doc__)
        return 1

    obs = Obs(host, port, os.environ.get("OBS_PASSWORD", ""))
    try:
        cmd, rest = args[0], args[1:]
        if cmd == "version":
            v = obs.request("GetVersion")
            print("OBS %s, obs-websocket %s, %s" % (v["obsVersion"], v["obsWebSocketVersion"], v["platform"]))
        elif cmd == "status":
            s = obs.request("GetRecordStatus")
            print("recording" if s["outputActive"] else "not recording", s.get("outputTimecode", ""))
        elif cmd == "scenes":
            s = obs.request("GetSceneList")
            for sc in reversed(s["scenes"]):
                print(("* " if sc["sceneName"] == s["currentProgramSceneName"] else "  ") + sc["sceneName"])
        elif cmd == "scene":
            names = {s["sceneName"] for s in obs.request("GetSceneList")["scenes"]}
            if rest[0] not in names:
                obs.request("CreateScene", {"sceneName": rest[0]})
            obs.request("SetCurrentProgramScene", {"sceneName": rest[0]})
        elif cmd == "start":
            obs.request("StartRecord")
        elif cmd == "stop":
            print(obs.request("StopRecord").get("outputPath", ""))
        elif cmd == "folder":
            if rest:
                obs.request("SetRecordDirectory", {"recordDirectory": rest[0]})
            print(obs.request("GetRecordDirectory")["recordDirectory"])
        elif cmd == "windows":
            for wid, name in sorted(list_windows(obs)):
                print("%d  %s" % (wid, name))
        elif cmd == "bind-all":
            if not rest:
                raise RuntimeError("bind-all needs the names, in the order the games were started")
            bind_all(obs, rest)
        elif cmd == "transitions":
            lst = obs.request("GetSceneTransitionList")
            for t in lst["transitions"]:
                print("%s%s" % (t["transitionName"], "   (current)" if t["transitionName"] == lst["currentSceneTransitionName"] else ""))
        elif cmd == "cut":
            obs.request("SetCurrentProgramScene", {"sceneName": scene_of(rest[0])})
        elif cmd == "clean":
            clean(obs)
        elif cmd == "call":
            print(json.dumps(obs.request(rest[0], json.loads(rest[1]) if len(rest) > 1 else None), indent=2))
        else:
            print(__doc__)
            return 1
    finally:
        obs.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (RuntimeError, OSError) as e:
        print("obs.py: %s" % e, file=sys.stderr)
        sys.exit(2)
