#if TRAILER
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;
using Unity.FPS.Game;

namespace Unity.FPS.Gameplay
{
    // Dev-only hero autopilot: invincible, walks the NavMesh to the nearest enemy, aims with smoothed yaw and pitch,
    // checks line of sight, fires in pulses, rescues itself when stuck.
    public class TrailerPilot : MonoBehaviour
    {
        PlayerCharacterController m_Player;
        Health m_Health;
        CharacterController m_Controller;
        Transform m_Cam;
        Actor m_Self;
        float m_Rot;

        Actor m_Target;
        readonly Dictionary<Actor, float> m_Ignore = new Dictionary<Actor, float>();
        float m_TargetSince, m_LastSeen;
        NavMeshPath m_Path = new NavMeshPath();
        float m_NextPath;
        int m_Corner;

        Vector3 m_StuckPos; float m_StuckTime;
        float m_StrafeDir = 1f, m_NextStrafe;
        float m_FireCycle;
        float m_CueNextLog;

        // cover beat: step out, take the turret's attention, duck behind cover, step out again
        public static float BeatStartAfter = 20f;     // seconds after gameplay-start before the beat may begin
        public static float BeatForceAfter = 32f;     // give up looking for a good spot and cue anyway
        enum Beat { Wait, ToCover, Hidden1, Out1, Peek, Duck, Hidden2, Out2, Done }
        Beat m_Beat = Beat.Wait;
        float m_BeatT, m_Born;
        Actor m_Turret;
        Vector3 m_Exposed, m_Hidden;
        Vector3 m_LastGood; bool m_HaveGood;
        float m_FloorMin = -1000f;
        int m_NavVerts;
        bool m_Switched, m_BeatDoneSeen;

        void Start()
        {
            m_Player = GetComponent<PlayerCharacterController>();
            m_Health = GetComponent<Health>();
            m_Controller = GetComponent<CharacterController>();
            m_Self = GetComponent<Actor>();
            m_Cam = m_Player.PlayerCamera.transform;
            m_Rot = m_Player.RotationSpeed;
            m_StuckPos = transform.position;
            m_Born = Time.time;
            var tri = NavMesh.CalculateTriangulation();
            m_NavVerts = tri.vertices.Length;
            if (m_NavVerts > 0)
            {
                float mn = float.MaxValue;
                foreach (var v in tri.vertices) mn = Mathf.Min(mn, v.y);
                m_FloorMin = mn - 2.5f;       // anything lower than the lowest walkable floor is the void
            }
            m_LastGood = transform.position; m_HaveGood = true;
        }

        void Warp(Vector3 p)
        {
            m_Controller.enabled = false;
            transform.position = p + Vector3.up * 0.1f;
            m_Controller.enabled = true;
            m_Player.CharacterVelocity = Vector3.zero;
            m_StuckPos = transform.position; m_StuckTime = 0; m_NextPath = 0;
        }

        // keeps the hero from ever leaving the walkable floor: remember the last good spot, go back to it when below the floor
        void KeepOnFloor()
        {
            Vector3 pos = transform.position;
            if (m_Player.IsGrounded && NavMesh.SamplePosition(pos, out var nh, 1.2f, NavMesh.AllAreas) && Mathf.Abs(nh.position.y - pos.y) < 1.5f)
            {
                m_LastGood = nh.position; m_HaveGood = true;
            }
            else if (m_HaveGood && pos.y < m_FloorMin)
            {
                Debug.Log("[trailer] fell to y " + pos.y + ", back to " + m_LastGood);
                Warp(m_LastGood);
                TrailerHarness.Cue("fall-recovered");
            }
        }

        // do not step off the navmesh edge (a drop or the void): if the straight step is blocked, follow the path corner instead
        Vector3 GuardMove(Vector3 move)
        {
            if (move.sqrMagnitude < 1e-4f) return move;
            if (!NavMesh.SamplePosition(transform.position, out var s0, 1.2f, NavMesh.AllAreas)) return move;
            Vector3 ahead = s0.position + move.normalized * 2.0f;
            if (!NavMesh.Raycast(s0.position, ahead, out _, NavMesh.AllAreas)) return move;
            if (m_Path != null && m_Path.corners.Length > 1)
            {
                Vector3 d = m_Path.corners[Mathf.Clamp(m_Corner, 1, m_Path.corners.Length - 1)] - transform.position; d.y = 0;
                if (d.magnitude > 0.3f && !NavMesh.Raycast(s0.position, s0.position + d.normalized * 2.0f, out _, NavMesh.AllAreas)) return d.normalized;
            }
            return Vector3.zero;
        }

        void OnDestroy() { TrailerInput.Move = Vector2.zero; TrailerInput.Fire = false; TrailerInput.LookX = TrailerInput.LookY = 0; }

        Vector3 AimPoint(Actor a) => a.AimPoint != null ? a.AimPoint.position : a.transform.position + Vector3.up * 1.0f;

        bool HasLos(Actor a)
        {
            Vector3 from = m_Cam.position, to = AimPoint(a);
            Vector3 d = to - from;
            var hits = Physics.RaycastAll(from, d.normalized, d.magnitude + 0.5f, ~0, QueryTriggerInteraction.Ignore);
            float best = float.MaxValue; Collider bestC = null;
            foreach (var h in hits)
            {
                if (h.collider.transform.IsChildOf(transform)) continue;
                if (h.distance < best) { best = h.distance; bestC = h.collider; }
            }
            return bestC != null && bestC.GetComponentInParent<Actor>() == a;
        }

        void PickTarget()
        {
            var mgr = FindAnyObjectByType<ActorsManager>();
            if (mgr == null) return;
            Actor best = null; float bestScore = float.MaxValue;
            foreach (var a in mgr.Actors)
            {
                if (a == null || a == m_Self || a.Affiliation == m_Self.Affiliation) continue;
                if (m_Ignore.TryGetValue(a, out float until) && Time.time < until) continue;
                float score = PathLength(a.transform.position);
                // until the cover beat is done: first the mobile enemy (the kill), from 16 s on the turret (the beat)
                bool turret = a.name.Contains("Turret");
                if (m_Beat != Beat.Done && turret == (Time.time - m_Born < 16f)) score += 1000f;
                if (score < bestScore) { bestScore = score; best = a; }
            }
            if (best == null && m_Ignore.Count > 0)
            {
                m_Ignore.Clear();   // everything was given up on: try again, nearest first
                foreach (var a in mgr.Actors)
                {
                    if (a == null || a == m_Self || a.Affiliation == m_Self.Affiliation) continue;
                    float score = PathLength(a.transform.position);
                    if (score < bestScore) { bestScore = score; best = a; }
                }
            }
            if (best != m_Target) { m_Target = best; m_TargetSince = Time.time; m_LastSeen = Time.time; m_NextPath = 0; }
        }

        // walking distance over the navmesh (straight distance plus a penalty when there is no path)
        float PathLength(Vector3 to)
        {
            Vector3 from = NavMesh.SamplePosition(transform.position, out var a, 3f, NavMesh.AllAreas) ? a.position : transform.position;
            Vector3 dest = NavMesh.SamplePosition(to, out var b, 6f, NavMesh.AllAreas) ? b.position : to;
            var p = new NavMeshPath();
            if (!NavMesh.CalculatePath(from, dest, NavMesh.AllAreas, p) || p.status == NavMeshPathStatus.PathInvalid || p.corners.Length < 2)
                return Vector3.Distance(transform.position, to) + 500f;
            float len = 0f;
            for (int i = 1; i < p.corners.Length; i++) len += Vector3.Distance(p.corners[i - 1], p.corners[i]);
            return p.status == NavMeshPathStatus.PathPartial ? len + 250f : len;
        }

        int EnemiesLeft()
        {
            var mgr = FindAnyObjectByType<ActorsManager>();
            int n = 0;
            if (mgr != null) foreach (var a in mgr.Actors) if (a != null && a != m_Self && a.Affiliation != m_Self.Affiliation && a.GetComponent<Health>() != null) n++;
            return n;
        }

        static float Wrap(float a) { while (a > 180f) a -= 360f; while (a < -180f) a += 360f; return a; }

        void Update()
        {
            float dt = Mathf.Max(Time.deltaTime, 0.001f);
            m_Health.Invincible = true;
            if (Time.time > m_CueNextLog) { m_CueNextLog = Time.time + 3f; Debug.Log("[trailer] pos " + transform.position + " navmesh " + m_NavVerts + " target " + (m_Target ? m_Target.name : "none")); }
            KeepOnFloor();
            m_Health.CurrentHealth = m_Health.MaxHealth;

            if (!m_Switched && Time.time - m_Born >= 16f) { m_Switched = true; m_Target = null; }
            if (!m_BeatDoneSeen && m_Beat == Beat.Done) { m_BeatDoneSeen = true; m_Target = null; }
            if (m_Target == null || m_Target.gameObject == null || !m_Target.isActiveAndEnabled
                || (Time.time - m_LastSeen > 14f && Time.time - m_TargetSince > 14f))
            {
                if (m_Target != null && Time.time - m_LastSeen > 14f) m_Ignore[m_Target] = Time.time + 20f;
                PickTarget();
            }

            Vector3 move = Vector3.zero; // world space
            Vector3 lookAt = transform.position + transform.forward * 5f;
            bool fireOk = false;

            if (m_Beat != Beat.Done && UpdateBeat(dt, ref move, ref lookAt, ref fireOk))
            {
                // the beat drives this frame
            }
            else if (m_Target != null)
            {
                Vector3 aim = AimPoint(m_Target);
                Vector3 toT = aim - m_Cam.position;
                float flat = new Vector3(toT.x, 0, toT.z).magnitude;
                bool los = HasLos(m_Target);
                if (los) m_LastSeen = Time.time;

                if (Time.time >= m_NextPath)
                {
                    m_NextPath = Time.time + 0.6f;
                    NavMeshHit nh;
                    Vector3 dest = NavMesh.SamplePosition(m_Target.transform.position, out nh, 6f, NavMesh.AllAreas) ? nh.position : m_Target.transform.position;
                    NavMeshHit sh;
                    Vector3 src = NavMesh.SamplePosition(transform.position, out sh, 3f, NavMesh.AllAreas) ? sh.position : transform.position;
                    NavMesh.CalculatePath(src, dest, NavMesh.AllAreas, m_Path);
                    m_Corner = 1;
                }

                Vector3 waypoint = m_Target.transform.position;
                if (m_Path != null && m_Path.corners.Length > 1)
                {
                    m_Corner = Mathf.Clamp(m_Corner, 1, m_Path.corners.Length - 1);
                    while (m_Corner < m_Path.corners.Length - 1 &&
                           new Vector2(m_Path.corners[m_Corner].x - transform.position.x, m_Path.corners[m_Corner].z - transform.position.z).magnitude < 1.2f) m_Corner++;
                    waypoint = m_Path.corners[m_Corner];
                }

                if (los && flat < 28f)
                {
                    // fight: face the target, close in to about 11 m, strafe
                    lookAt = aim;
                    if (Time.time > m_NextStrafe) { m_StrafeDir = Random.value < 0.5f ? -1f : 1f; m_NextStrafe = Time.time + Random.Range(1.2f, 2.5f); }
                    Vector3 fwd = new Vector3(toT.x, 0, toT.z).normalized;
                    Vector3 right = Vector3.Cross(Vector3.up, fwd);
                    float adv = flat > 12f ? 1f : (flat < 8f ? -0.6f : 0f);
                    move = fwd * adv + right * m_StrafeDir * 0.6f;
                    float yawErr = Mathf.Abs(Wrap(Quaternion.LookRotation(new Vector3(toT.x, 0, toT.z)).eulerAngles.y - transform.eulerAngles.y));
                    fireOk = yawErr < 7f;
                }
                else
                {
                    // travel: follow the path, look where we are going
                    Vector3 d = waypoint - transform.position;
                    d.y = 0;
                    if (d.magnitude > 0.2f) move = d.normalized;
                    lookAt = transform.position + (d.sqrMagnitude > 0.01f ? d.normalized : transform.forward) * 5f + Vector3.up * 1.5f;
                }
            }

            // look: smoothed yaw and pitch
            Vector3 dir = lookAt - m_Cam.position;
            float wantYaw = Quaternion.LookRotation(new Vector3(dir.x, 0, dir.z).sqrMagnitude > 1e-4f ? new Vector3(dir.x, 0, dir.z) : transform.forward).eulerAngles.y;
            float dyaw = Wrap(wantYaw - transform.eulerAngles.y);
            float horiz = new Vector3(dir.x, 0, dir.z).magnitude;
            float wantPitch = Mathf.Clamp(-Mathf.Atan2(dir.y, Mathf.Max(horiz, 0.1f)) * Mathf.Rad2Deg, -60f, 60f);
            float curPitch = Wrap(m_Cam.localEulerAngles.x);
            float dpitch = wantPitch - curPitch;
            float k = Mathf.Min(1f, 9f * dt);
            float yawStep = Mathf.Clamp(dyaw * k, -9f, 9f);
            float pitchStep = Mathf.Clamp(dpitch * k, -6f, 6f);
            TrailerInput.LookX = yawStep / m_Rot;
            TrailerInput.LookY = pitchStep / m_Rot;

            // move: world to local input; slow down while turning hard
            move = GuardMove(move);
            Vector3 local = transform.InverseTransformDirection(move);
            float turnFactor = Mathf.Clamp01(1.2f - Mathf.Abs(dyaw) / 90f);
            TrailerInput.Move = new Vector2(local.x, local.z) * turnFactor;

            // fire in pulses, only with a clear view and a good aim
            m_FireCycle += dt;
            bool pulse = (m_FireCycle % 0.55f) < 0.28f;
            // never kill the last enemy: its death would end the level (win scene) in the middle of the show
            if (m_Target != null && m_Beat != Beat.Done && m_Target.name.Contains("Turret"))
            {
                var th = m_Target.GetComponent<Health>();
                if (th != null && th.GetRatio() < 0.35f) fireOk = false;   // keep the turret alive until the cover beat is done
            }
            TrailerInput.Fire = fireOk && pulse;

            // stuck rescue
            m_StuckTime += dt;
            if (m_StuckTime > 3.5f)
            {
                float moved = (transform.position - m_StuckPos).magnitude;
                m_StuckPos = transform.position; m_StuckTime = 0;
                if (moved < 1.2f && m_Target != null) Rescue();
            }
            TrailerInput.Jump = false;
        }

        // returns true while the beat drives the hero. Time-based: starts BeatStartAfter s after gameplay-start whatever happens.
        bool UpdateBeat(float dt, ref Vector3 move, ref Vector3 lookAt, ref bool fireOk)
        {
            float since = Time.time - m_Born;
            if (m_Beat == Beat.Wait)
            {
                if (since < BeatStartAfter) return false;
                m_Turret = FindTurret();
                if (m_Turret == null) { TrailerHarness.Cue("cover-skipped"); m_Beat = Beat.Done; return false; }
                if (FindHiddenFrom(transform.position, m_Turret, out m_Hidden, true))
                {
                    m_Exposed = transform.position; Next(Beat.ToCover);
                }
                else if (FindBeatSpot(m_Turret, out m_Exposed, out m_Hidden))
                {
                    Debug.Log("[trailer] beat spot by warp: hidden " + m_Hidden + " exposed " + m_Exposed);
                    Warp(m_Hidden); Next(Beat.Hidden1);
                }
                else { TrailerHarness.Cue("cover-skipped"); m_Beat = Beat.Done; return false; }
            }
            m_BeatT += dt;

            lookAt = AimPoint(m_Turret);
            Vector3 goal = transform.position; float tol = 0.4f; bool expose = false;
            switch (m_Beat)
            {
                case Beat.ToCover: goal = m_Hidden; if (Arrived(goal, tol) || m_BeatT > 3f) Next(Beat.Hidden1); break;
                case Beat.Hidden1: goal = m_Hidden; if (m_BeatT > 1.4f) Next(Beat.Out1); break;
                case Beat.Out1: goal = m_Exposed; expose = true; if (Arrived(goal, tol) || m_BeatT > 1.2f) { Next(Beat.Peek); TrailerHarness.Cue("cover-peek"); } break;
                case Beat.Peek: goal = m_Exposed; expose = true; if (m_BeatT > 0.6f) Next(Beat.Duck); break;
                case Beat.Duck: goal = m_Hidden; if (Arrived(goal, tol) || m_BeatT > 1.2f) Next(Beat.Hidden2); break;
                case Beat.Hidden2: goal = m_Hidden; if (m_BeatT > 0.35f) Next(Beat.Out2); break;
                case Beat.Out2: goal = m_Exposed; expose = true; if (Arrived(goal, tol) || m_BeatT > 1.2f) { Next(Beat.Done); TrailerHarness.Cue("cover-end"); m_NextPath = 0; } break;
            }
            Vector3 d = goal - transform.position; d.y = 0;
            if (d.magnitude > tol) move = d.normalized;
            fireOk = expose;
            return m_Beat != Beat.Done;
        }

        bool Arrived(Vector3 g, float tol) { var d = g - transform.position; d.y = 0; return d.magnitude < tol; }
        void Next(Beat b) { m_Beat = b; m_BeatT = 0; }

        Actor FindTurret()
        {
            var mgr = FindAnyObjectByType<ActorsManager>();
            if (mgr == null) return null;
            foreach (var a in mgr.Actors)
                if (a != null && a.Affiliation != m_Self.Affiliation && a.name.Contains("Turret")) return a;
            return null;
        }

        bool TurretSees(Actor t, Vector3 eyePoint)
        {
            Vector3 from = AimPoint(t), d = eyePoint - from;
            var hits = Physics.RaycastAll(from, d.normalized, d.magnitude, ~0, QueryTriggerInteraction.Ignore);
            foreach (var h in hits)
            {
                if (h.collider.transform.IsChildOf(transform) || h.collider.transform.IsChildOf(t.transform)) continue;
                return false;   // something solid in between
            }
            return true;
        }

        // from an exposed point (the turret sees it): a spot 2 to 4 m away, reachable in a straight line over the navmesh, that the turret cannot see
        bool FindHiddenFrom(Vector3 origin, Actor t, out Vector3 hidden, bool needExposed)
        {
            hidden = origin;
            float dist = Vector3.Distance(t.transform.position, origin);
            if (dist > 32f || dist < 5f) return false;
            if (needExposed && !TurretSees(t, origin + Vector3.up * 1.6f)) return false;
            if (!NavMesh.SamplePosition(origin, out var s0, 1.5f, NavMesh.AllAreas)) return false;
            for (int i = 0; i < 16; i++)
            {
                float ang = i * 22.5f * Mathf.Deg2Rad;
                for (float r = 2f; r <= 4f; r += 1f)
                {
                    Vector3 cand = s0.position + new Vector3(Mathf.Cos(ang), 0, Mathf.Sin(ang)) * r;
                    if (!NavMesh.SamplePosition(cand, out var nh, 1.0f, NavMesh.AllAreas)) continue;
                    if (Mathf.Abs(nh.position.y - s0.position.y) > 0.6f) continue;
                    if (NavMesh.Raycast(s0.position, nh.position, out _, NavMesh.AllAreas)) continue;
                    if (TurretSees(t, nh.position + Vector3.up * 1.6f) || TurretSees(t, nh.position + Vector3.up * 0.8f)) continue;
                    hidden = nh.position;
                    Debug.Log("[trailer] cover found at " + hidden + " from " + origin + " turret " + t.name);
                    return true;
                }
            }
            return false;
        }

        // a fixed, seeded search over the navmesh around the turret for an exposed spot with cover next to it
        bool FindBeatSpot(Actor t, out Vector3 exposed, out Vector3 hidden)
        {
            var rng = new System.Random(5);
            exposed = hidden = transform.position;
            for (int i = 0; i < 400; i++)
            {
                float ang = (float)(rng.NextDouble() * Mathf.PI * 2f), r = 9f + (float)rng.NextDouble() * 12f;
                Vector3 cand = t.transform.position + new Vector3(Mathf.Cos(ang), 0, Mathf.Sin(ang)) * r;
                if (!NavMesh.SamplePosition(cand, out var nh, 3f, NavMesh.AllAreas)) continue;
                if (Mathf.Abs(nh.position.y - t.transform.position.y) > 3f) continue;
                if (FindHiddenFrom(nh.position, t, out hidden, true)) { exposed = nh.position; return true; }
            }
            return false;
        }

        void Rescue()
        {
            Vector3 center = m_Target.transform.position + Random.insideUnitSphere * 7f;
            if (NavMesh.SamplePosition(center, out var hit, 6f, NavMesh.AllAreas))
            {
                m_Controller.enabled = false;
                transform.position = hit.position + Vector3.up * 0.2f;
                m_Controller.enabled = true;
                m_NextPath = 0;
                TrailerHarness.Cue("rescue");
            }
            else m_Ignore[m_Target] = Time.time + 20f;
        }
    }
}
#endif
