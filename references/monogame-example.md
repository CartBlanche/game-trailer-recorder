# The contract in a MonoGame game (from Vector Rumble)

Vector Rumble's harness is one file, `Core/DevShots.cs`, compiled in only with `dotnet build -c Release -p:DevShots=true` (the project defines a `DEVSHOT` symbol when that property is set; the whole file sits inside `#if DEVSHOT`). Hooks into the game are a few `#if DEVSHOT` lines. The same pattern works in any C# game; other engines need their own version of it.

## Compile switch (csproj)

Put the define in the project that holds the game class. A game split into a Core library and a Desktop app needs it in the Core project; building the Desktop project with `-p:DevShots=true` passes the property down to it.

```xml
<PropertyGroup Condition="'$(DevShots)' == 'true'">
  <DefineConstants>$(DefineConstants);DEVSHOT</DefineConstants>
</PropertyGroup>
```

## Sketch

```csharp
#if DEVSHOT
static class DevShots
{
    // 1. environment in
    static string Env(string name) => Environment.GetEnvironmentVariable(name);

    // 2. cue lines out: one per story beat, wall-clock milliseconds, flushed
    public static void Cue(string name)
    {
        long ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        Console.WriteLine($"[DEVSHOT] cue {name} unix-ms {ms}");
        Console.Out.Flush();
    }

    // 3. window from "x,y,w,h": set before the first frame
    public static void ApplyWindow(Game game, GraphicsDeviceManager graphics)
    {
        var parts = (Env("VR_WIN") ?? "").Split(',');
        if (parts.Length != 4) return;
        graphics.PreferredBackBufferWidth = int.Parse(parts[2]);
        graphics.PreferredBackBufferHeight = int.Parse(parts[3]);
        graphics.ApplyChanges();
        game.Window.Position = new Point(int.Parse(parts[0]), int.Parse(parts[1]));
        Console.WriteLine($"[DEVSHOT] back buffer {graphics.PreferredBackBufferWidth}x{graphics.PreferredBackBufferHeight}");
    }

    // 4. signal files: poll once per frame in Update; act when one appears
    public static bool Signalled(string envName) { var p = Env(envName); return p != null && File.Exists(p); }
}
#endif
```

## The autopilot as a script (from a second game, a two-player LAN artillery game)

The part that takes the time is the scripted walk. A neat shape in C# is a script of "waits" run by a game component: each `yield return` is a condition that must become true before the script goes on, so the whole walk reads top to bottom. Menu items are chosen by setting the screen's selected index (so the highlight shows), waiting, then calling the screen's own select method (so the game's own sound and logic run). The menu classes' members are often private: reach them by reflection, behind the dev switch.

```csharp
class Director : GameComponent   // added with Components.Add in the dev hook; UpdateOrder high so it runs last
{
    IEnumerator<Func<bool>> script;   // = HostScript() or JoinScript()
    Func<bool> waiting; float clock;

    public override void Update(GameTime t)
    {
        clock += (float)t.ElapsedGameTime.TotalSeconds;
        if (waiting == null || waiting())            // the current wait is over: run to the next one
            { if (!script.MoveNext()) { Game.Exit(); return; } waiting = script.Current; }
    }
    Func<bool> Wait(float s) { float end = clock + s; return () => clock >= end; }
    Func<bool> Until(Func<bool> c, float timeout) { float end = clock + timeout; return () => c() || clock >= end; }

    // highlight an entry, hold so the viewer sees it, press it, pause
    IEnumerable<Func<bool>> Choose(string text, float highlight, float after)
    {
        yield return Until(() => MenuReady(text), 30f);          // the top screen is an active menu with that entry
        var menu = Top() as MenuScreen; int i = IndexOf(menu, text);
        Highlight(menu, i);                                       // reflection: set the selected index
        yield return Wait(highlight);
        Press(menu, i);                                           // reflection: call the select method
        yield return Wait(after);
    }

    IEnumerator<Func<bool>> HostScript()
    {
        Cue("parked");
        yield return () => File.Exists(Env("GAME_RELEASE"));      // the release gate
        foreach (var s in Choose("Play", 0.7f, 0.8f)) yield return s;
        foreach (var s in Choose("Multiplayer", 0.7f, 0.8f)) yield return s;
        Cue("host-lobby");
        yield return () => File.Exists(Env("GAME_START"));        // the director's "start" signal
        /* ... play the match with scripted or AI input, Cue("match-start"), Cue("game-over"), wait, then it ends and Game.Exit() runs */
    }
}
```

Also in the dev build: force the game to act as focused and set `InactiveSleepTime` to zero (see `pitfalls.md`).

## What Vector Rumble's harness does, for reference

- Opens on a chosen screen (`VR_OPEN`: main menu or the Multiplayer browser) and walks a list of menu items (`VR_TOUR="Play,Multiplayer,Host a game"`) by calling the menu screen's own select methods through reflection, highlight first and press after, with the menu's own sound cue played for each step (otherwise the scripted walk is silent).
- Waits for `VR_TOURFILE` before starting the walk (the release file), `VR_GOFILE` before a joiner presses Join, `VR_STARTFILE` before the host presses Start.
- AI flies every ship (`VR_ALLAI`), seed and level fixed (`VR_SEED`, `VR_PICK`), ends the match at `VR_SCORELIMIT` kills, quits `VR_QUITAFTEROVER` seconds after game over and at `VR_ENDAFTER` seconds regardless.
- `VR_CLEANSETTINGS` ignores the saved settings file and turns the idle pause off.
- Dev-only polish: a bigger, coloured player name in the heading, brighter background labels (`VR_SKYNAMES`), and AI pilots hopping just before a shot arrives (`VR_DEMOHOP`) to show the hop move.

Pitfalls that hit this harness: stereo menu sounds not playing for scripted presses, an idle "Paused" screen, window size smaller than the video, and a non-host copy's setting not reaching the match (the host's arena choice had to be copied into the lobby rules).
