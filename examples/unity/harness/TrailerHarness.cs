#if TRAILER
using System;
using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using Unity.FPS.Game;

namespace Unity.FPS.Gameplay
{
    // Dev-only trailer harness (compiled only with the TRAILER define, see Editor/TrailerBuild.cs).
    // Driven by environment variables:
    //   TRAILER_RELEASE    path of the release file; the harness only exists when this is set (release gate, part 1)
    //   TRAILER_WIN        "x,y,w,h" window position and size
    //   TRAILER_SCALE      pixels per point (2 on a Retina screen with macRetinaSupport)
    //   TRAILER_SEED       random seed
    //   TRAILER_SHOWSECONDS length of the show from the first gameplay frame
    //   TRAILER_QUITAFTER  seconds the game keeps running after the show ends (for the credits card)
    //   TRAILER_MUTE       "1" mutes all audio (dry runs)
    //   TRAILER_SHOTDIR    folder for self-made screenshots (frames can be checked without OBS)
    public class TrailerHarness : MonoBehaviour
    {
        static string Env(string n, string d = "") { var v = Environment.GetEnvironmentVariable(n); return string.IsNullOrEmpty(v) ? d : v; }

        public static void Cue(string name)
        {
            long ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            Console.Out.WriteLine("[trailer] cue " + name + " unix-ms " + ms);
            Console.Out.Flush();
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        static void Boot()
        {
            if (string.IsNullOrEmpty(Env("TRAILER_RELEASE"))) return;   // a double-clicked dev build plays normally
            var go = new GameObject("TrailerHarness");
            DontDestroyOnLoad(go);
            go.AddComponent<TrailerHarness>();
        }

        void Start()
        {
            Application.runInBackground = true;
            QualitySettings.vSyncCount = 0;
            Application.targetFrameRate = 60;
            UnityEngine.Random.InitState(int.Parse(Env("TRAILER_SEED", "1")));
            StartCoroutine(Story());
        }

        void Update()
        {
            if (Env("TRAILER_MUTE") == "1") AudioListener.volume = 0f;
        }

        IEnumerator Story()
        {
            // window (needs a frame or two after start)
            yield return null; yield return null;
            var parts = Env("TRAILER_WIN", "0,30,1280,720").Split(',');
            int x = int.Parse(parts[0]), y = int.Parse(parts[1]), w = int.Parse(parts[2]), h = int.Parse(parts[3]);
            // with Mac Retina support the resolution is in PIXELS: a 1280x720 point window needs 2560x1440
            int sc = int.Parse(Env("TRAILER_SCALE", "1"));
            Screen.SetResolution(w * sc, h * sc, FullScreenMode.Windowed);
            yield return null; yield return null;
            yield return Screen.MoveMainWindowTo(Screen.mainWindowDisplayInfo, new Vector2Int(x, y));
            yield return null; yield return null;
            Console.Out.WriteLine("[trailer] back buffer " + Screen.width + "x" + Screen.height + " window requested " + w + "x" + h + " dpi " + Screen.dpi);
            Console.Out.Flush();

            // hold on the first screen until the release file appears (release gate, part 2)
            string release = Env("TRAILER_RELEASE");
            Cue("ready");
            while (!File.Exists(release)) yield return null;
            Cue("released");

            // menu: the Play button is selected; show it for a moment, then press
            yield return new WaitForSeconds(0.8f);
            var sel = EventSystem.current != null ? EventSystem.current.currentSelectedGameObject : null;
            Console.Out.WriteLine("[trailer] menu selection: " + (sel ? sel.name : "none"));
            yield return new WaitForSeconds(0.9f);
            Cue("play-pressed");
            SceneManager.LoadScene("MainScene");

            // wait for the player in the level
            PlayerCharacterController player = null;
            while (player == null) { yield return null; player = FindAnyObjectByType<PlayerCharacterController>(); }
            yield return new WaitForSeconds(1.0f);

            TrailerInput.Active = true;
            var pilot = player.gameObject.AddComponent<TrailerPilot>();
            EventManager.AddListener<EnemyKillEvent>(OnKill);
            Cue("gameplay-start");
            float show = float.Parse(Env("TRAILER_SHOWSECONDS", "40"), System.Globalization.CultureInfo.InvariantCulture);
            float quitAfter = float.Parse(Env("TRAILER_QUITAFTER", "12"), System.Globalization.CultureInfo.InvariantCulture);
            string shots = Env("TRAILER_SHOTDIR");
            float t0 = Time.realtimeSinceStartup, nextShot = 2f;

            // unconditional time cap; a win or lose scene also ends the show
            while (Time.realtimeSinceStartup - t0 < show && SceneManager.GetActiveScene().name == "MainScene")
            {
                if (!string.IsNullOrEmpty(shots) && Time.realtimeSinceStartup - t0 > nextShot)
                {
                    Directory.CreateDirectory(shots);
                    ScreenCapture.CaptureScreenshot(Path.Combine(shots, "shot-" + Mathf.RoundToInt(nextShot).ToString("D3") + ".png"));
                    nextShot += 4f;
                }
                yield return null;
            }
            string endScene = SceneManager.GetActiveScene().name;
            Console.Out.WriteLine("[trailer] show ends in scene " + endScene + " after " + (Time.realtimeSinceStartup - t0) + " s");
            if (endScene != "MainScene")
            {
                // a lose or win scene before the cap: a failed take. No show-end cue, so it is plain to see.
                Cue("failed");
                yield return new WaitForSeconds(3f);
                Application.Quit();
                yield break;
            }
            Cue("show-end");
            if (!string.IsNullOrEmpty(shots)) ScreenCapture.CaptureScreenshot(Path.Combine(shots, "shot-end.png"));
            // keep playing so the sound can fade under the credits card, then quit by ourselves
            yield return new WaitForSeconds(quitAfter);
            Cue("quit");
            Application.Quit();
        }

        int m_Kills;
        void OnKill(EnemyKillEvent e) { m_Kills++; Cue("kill"); }
    }
}
#endif
