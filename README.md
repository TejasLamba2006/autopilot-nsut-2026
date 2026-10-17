# AutoPilot — Shunya 2026 (GDG NSUT)

Deterministic lane-defense optimizer (`agent.py`) and browser automation findings for **Team `0060` (`Chatgpteam`)**.

## Key Findings & Architecture

1. **Zero-Latency Deterministic Engine (`agent.py`):**
   - Bypasses the 60 RPM LLM gateway rate limit and 1–3s LLM latency, responding in `< 5ms` per pause (`0.3s` total subprocess roundtrip).
   - Pure Python standard library, passing `autopilot verify` static & runtime sandbox checks.

2. **Scoring Formula (Reverse-Engineered from Backend `evaluator_output`):**
   - **Win:** `25.0` (if lost, only `kill_score` counts, max `25.0`)
   - **Kills:** `25.0 * (enemies_killed / total_enemies)`
   - **Survival:** `25.0 * (defences_survived / defences_placed)` — every destroyed Shield or Penguin reduces this ratio.
   - **Speed:** `max(0, 10.0 * (1 - duration_seconds / 240.0))`
   - **Economy:** `10.0 + 5.0 * ((test_case_budget - total_defence_cost) / test_case_budget)`

3. **Unit & Enemy Mechanics (Extracted from Unity `data.unity3d` & `global-metadata.dat`):**
   - **Grid:** 11 columns (`x = 0..10`), 6 rows (`y = 0..5`), `1.5` world units per tile.
   - **Archers (`defenceId: 2`, 300 coins, 100 HP, ~26 DPS):** Global range across all rows; all Archers focus-fire the lowest row (`y = 0 -> 5`) first, then the enemy closest to `x = 0`.
   - **Soldiers (`defenceId: 1`, 200 coins, 150 HP, ~40 DPS):** Highest DPS-per-coin (`0.20 DPS/coin`), fires along its own row.
   - **Shields (`defenceId: 3`, 150 coins, 700 HP):** Stops enemies and absorbs ranged/beam attacks. Placed at `x = 4` so Pirates (`EnemyPirate`, 2.0-unit / 1.33-tile blast radius) detonate safely away from `x = 0..2`.
   - **Penguins (`defenceId: 0`, 250 coins, 200 HP, 500 burst damage):** Triggers on first damage (`OnPoked`) and slides down its row at `6.7 tiles/s`, dealing `500` damage to every enemy in the lane.
   - **Wizards (`EnemyWizard`, 500 HP, +15/s regen, 8-unit / 5.33-tile range, 50 DPS continuous beam):** Requires concentrated multi-unit focus fire or Penguin burst to overcome regeneration.

4. **Unity WebGL Automation Hook:**
   - The Unity WebGL canvas (`build12`) exposes its internal `Module` via the `#unity-fullscreen-button` closure, allowing headless test-case triggering via:
     ```js
     unityModule.SendMessage("Controller", "ChangeTeamId", "0060");
     unityModule.SendMessage("NetworkManager", "SubmitTeamID", "0060");
     ```
