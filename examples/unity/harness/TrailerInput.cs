#if TRAILER
using UnityEngine;

namespace Unity.FPS.Gameplay
{
    // Dev-only input override for the trailer autopilot. PlayerInputHandler reads it when Active.
    // Lives inside the fps.Gameplay assembly so the game's own input class can see it.
    public static class TrailerInput
    {
        public static bool Active;
        public static Vector2 Move;      // x = strafe, y = forward, local to the hero
        public static float LookX;       // multiplied by RotationSpeed by the player controller (degrees per frame / 200)
        public static float LookY;       // positive looks down
        public static bool Fire;
        public static bool Jump;         // held
    }
}
#endif
