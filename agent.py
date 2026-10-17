"""Deterministic lane-defense optimizer v9 for AutoPilot."""


def _xy(u):
    return round(u["position"]["x"]), round(u["position"]["y"])


def _etype(t):
    t = str(t).lower()
    if "clown" in t:
        return 0
    if "monk" in t:
        return 1
    if "wizard" in t:
        return 2
    if "pirate" in t:
        return 3
    return -1


def _dtype(t):
    t = str(t).lower()
    if "penguin" in t:
        return 0
    if "sol" in t:
        return 1
    if "archer" in t:
        return 2
    if "shield" in t:
        return 3
    return -1


def get_reinforcements(state):
    coins = float(state.get("budget", {}).get("remaining", 0))
    raw_costs = state.get("unitCosts") or {"0": 250, "1": 200, "2": 300, "3": 150}
    costs = {int(k): float(v) for k, v in raw_costs.items()}
    min_cost = min(costs.values())
    if coins < min_cost:
        return []

    defences = [d for d in state.get("defences", []) if d.get("health", 0) > 0]
    enemies = [
        e for e in state.get("enemies", [])
        if not e.get("isDead", False) and e.get("health", 0) > 0
    ]
    taken = {_xy(d) for d in defences}

    row_defs = {r: [] for r in range(6)}
    for d in defences:
        x, y = _xy(d)
        if 0 <= y <= 5:
            row_defs[y].append((x, _dtype(d.get("type", "")), float(d.get("health", 0))))

    row_enems = {r: [] for r in range(6)}
    for e in enemies:
        x, y = _xy(e)
        if 0 <= y <= 5:
            row_enems[y].append((x, _etype(e.get("type", "")), float(e.get("health", 0))))

    cards = []

    def place(kind, x, y):
        nonlocal coins
        c = costs.get(kind, 9999)
        if coins >= c and 0 <= x <= 10 and 0 <= y <= 5 and (x, y) not in taken:
            taken.add((x, y))
            coins -= c
            cards.append({"defenceId": kind, "defenceGridPosition": {"x": x, "y": y}})
            hp = 700.0 if kind == 3 else (200.0 if kind == 0 else (150.0 if kind == 1 else 100.0))
            row_defs[y].append((x, kind, hp))
            return True
        return False

    def has_kind(y, kind, xs=None):
        return any(k == kind and (xs is None or x in xs) for x, k, _ in row_defs[y])

    def count_kind(y, kind, xs=None):
        return sum(1 for x, k, _ in row_defs[y] if k == kind and (xs is None or x in xs))

    def shield_hp(y, xs):
        return sum(hp for x, k, hp in row_defs[y] if k == 3 and x in xs)

    def total_archers():
        return sum(count_kind(r, 2) for r in range(6))

    phase = state.get("phase", "pause")

    if phase == "start":
        upcoming = state.get("upcomingEnemies") or []
        row_threat = {r: {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0} for r in range(6)}
        active_rows = set()
        total_wizards = 0
        total_pirates = 0

        for item in upcoming:
            eid = int(item.get("enemyId", -1))
            cnt = int(item.get("count", 0))
            if cnt <= 0 or eid not in (0, 1, 2, 3):
                continue
            if eid == 2:
                total_wizards += cnt
            elif eid == 3:
                total_pirates += cnt
            allowed = item.get("allowedRows")
            rows = [r for r in (allowed if allowed else range(6)) if 0 <= r <= 5]
            if not rows:
                rows = list(range(6))
            for r in rows:
                active_rows.add(r)
                row_threat[r][eid] += cnt / len(rows)

        for r in range(6):
            if row_enems[r]:
                active_rows.add(r)

        if not active_rows:
            active_rows = set(range(6))

        game_settings = state.get("gameSettings") or {}
        reinf_enabled = game_settings.get("reinforcementsEnabled", True)

        # CASE 1: Pure Clown/Monk swarm with generous budget (e.g., TC01 = 5000 coins, 0 Wizards, 0 Pirates)
        if total_wizards == 0 and total_pirates == 0 and coins >= 3000:
            for r in range(6):
                place(2, 0, r)
            for r in range(6):
                place(1, 1, r)
            return cards

        # CASE 2: Concentrated 1-3 lane siege (e.g., TC11 "dr.doom": 12 Wizards + 6 Clowns in rows [2, 3], budget 1400)
        # Why did Soldiers at x=0/1 fail on TC11?
        # Because when Wizards spawn in BOTH row 2 and row 3, 2 Soldiers per row only deal 80 DPS per row (65 net DPS vs 15/s regen),
        # taking 7.7s to kill ONE Wizard while new Wizards arrive every 2.8s!
        # By placing 4 Archers at x=0 in SAFE quiet rows (e.g., rows 0, 1, 4, 5) + 1 Shield at x=4 in the row with the first enemy:
        # - All 4 Archers focus-fire ONE Wizard at a time (104 DPS -> 89 net DPS), killing it before the next builds up!
        # - Every kill grants +50 coins, and at Pause 2/3 we buy the 5th Archer (130 DPS) and Penguins at x=5 to wipe stacked Wizards!
        if len(active_rows) <= 3 and total_pirates == 0:
            quiet_rows = [r for r in range(6) if r not in active_rows]
            # Place up to 4 Archers in quiet rows first (safe from all enemy beams/throws!)
            for r in (quiet_rows + sorted(active_rows))[:4]:
                if coins >= costs.get(2, 300) + costs.get(3, 150):
                    place(2, 0, r)
                elif coins >= costs.get(2, 300) and len(cards) < 3:
                    place(2, 0, r)
            # Place Shields at x=4 in active rows (starting with the row that already has the first enemy!)
            ordered_active = sorted(
                active_rows,
                key=lambda r: -(100.0 if row_enems[r] else row_threat[r][2] * 3.0 + row_threat[r][0]),
            )
            for r in ordered_active:
                if coins >= costs.get(3, 150):
                    place(3, 4, r)
            return cards

        # CASE 3: Multi-lane mixed waves (TC02, TC05, TC09, etc.):
        must_shield_rows = [
            r for r in active_rows
            if (row_enems[r] and any(e[1] != 0 for e in row_enems[r]))
            or row_threat[r][3] > 0
            or row_threat[r][2] >= 1.0
            or row_threat[r][1] >= 1.0
        ]
        min_shields_needed = min(len(active_rows), max(3, len(must_shield_rows)))
        shield_reserve = min_shields_needed * costs.get(3, 150)

        if coins >= 2700:
            target_archers = 6
        elif coins - shield_reserve >= 1500:
            target_archers = 5
        elif coins - shield_reserve >= 1050:
            target_archers = 4
        else:
            target_archers = max(2, int((coins - shield_reserve) // costs.get(2, 300)))

        # Put Archers in rows with lowest Pirate/Wizard threat first so they sit in the safest lanes
        archer_rows = sorted(
            range(6),
            key=lambda r: (
                row_threat[r][3] * 10.0 + row_threat[r][2] * 8.0 + row_threat[r][1] * 2.0,
                r,
            ),
        )
        for r in archer_rows[:target_archers]:
            place(2, 0, r)

        # Place Shields at x=4 in highest-threat rows:
        shield_candidates = sorted(
            active_rows,
            key=lambda r: -(
                (60.0 if (row_enems[r] and any(e[1] != 0 for e in row_enems[r])) else 0.0)
                + (35.0 if row_threat[r][3] > 0 else 0.0)
                + (15.0 if row_threat[r][1] > 0 else 0.0)
                + (10.0 if row_threat[r][2] > 0 else 0.0)
                + (6.0 if has_kind(r, 2, {0}) else 0.0)
                + row_threat[r][3] * 5.0
                + row_threat[r][1] * 3.0
                + row_threat[r][2] * 2.5
                + row_threat[r][0]
            ),
        )
        for r in shield_candidates:
            if coins >= costs.get(3, 150):
                place(3, 4, r)

        if not reinf_enabled:
            for r in range(6):
                place(2, 0, r)
            for r in shield_candidates:
                place(1, 1, r)
                place(1, 2, r)

        return cards

    # === PAUSE PHASE ===
    queued = int((state.get("counts") or {}).get("enemiesQueued", 0))
    urgent_rows = sorted(
        [r for r in range(6) if row_enems[r]],
        key=lambda r: (min(e[0] for e in row_enems[r]), -sum(e[2] for e in row_enems[r])),
    )

    # 1. Immediate reactive defense in rows with active enemies:
    for r in urgent_rows:
        enems = row_enems[r]
        min_x = min(e[0] for e in enems)
        has_wiz = any(e[1] == 2 for e in enems)
        has_pir = any(e[1] == 3 for e in enems)
        has_monk = any(e[1] == 1 for e in enems)
        wiz_cnt = sum(1 for e in enems if e[1] == 2)
        total_hp = sum(e[2] for e in enems)

        # A. Pirate in row: must have a Shield with >= 210 HP ahead of x=1 (at x=4, 3, or 2)
        if has_pir:
            pir_x = min(e[0] for e in enems if e[1] == 3)
            blocking_hp = sum(hp for x, k, hp in row_defs[r] if k == 3 and 2 <= x <= pir_x)
            if blocking_hp < 210:
                for bx in (4, 3, 2):
                    if bx < pir_x and place(3, bx, r):
                        break

        # B. Wizard in row:
        if has_wiz:
            wiz_x = min(e[0] for e in enems if e[1] == 2)
            # CRITICAL: If 2+ Wizards (or Wizard + enemies >= 650 HP) are stacked in this row,
            # or if a Wizard is in row >= 3 while lower rows also have enemies (distracting our Archers!),
            # a Penguin placed within 5 tiles of the Wizard (e.g., at x = min(5, wiz_x - 1)) gets beamed by the Wizard,
            # triggers immediately, and slides down the row dealing 500 DAMAGE to EVERY enemy in the row!
            lower_rows_busy = any( len(row_enems[lr]) > 0 for lr in range(r) )
            if (wiz_cnt >= 2 or total_hp >= 650 or (r >= 3 and lower_rows_busy and wiz_x <= 9)) and not has_kind(r, 0):
                # Place Penguin IN FRONT OF our existing Shield (or at x=5/4/3) so the Wizard hits the Penguin first!
                max_def_x = max([x for x, _, _ in row_defs[r]] or [0])
                cand_xs = [px for px in (5, 4, 3, 2, 1) if max_def_x < px < wiz_x and wiz_x - px <= 5]
                if not cand_xs:
                    cand_xs = [px for px in (4, 3, 2, 1) if px < wiz_x and wiz_x - px <= 5]
                for px in cand_xs:
                    if place(0, px, r):
                        break

            # Ensure blocking Shield ahead of Wizard if current Shield has < 220 HP (and no Penguin was just placed)
            blocking_hp = sum(hp for x, k, hp in row_defs[r] if k == 3 and 1 <= x <= wiz_x)
            if blocking_hp < 220 and not has_kind(r, 0):
                for sx in (4, 3, 2, 1):
                    if sx < wiz_x and place(3, sx, r):
                        break

            # Also if a Wizard is in row >= 3 and lower rows are busy (orblocking_hp < 350), a Soldier at x=1 provides dedicated lane DPS
            if (r >= 3 and lower_rows_busy) and not has_kind(r, 1, {1, 2}) and not has_kind(r, 0) and wiz_x >= 2:
                if coins >= costs.get(1, 200):
                    place(1, 1, r)

        # C. Monk or Clown in row: ensure blocking Shield if current Shield has < 200 HP
        if has_monk or min_x <= 6:
            blocking_hp = sum(hp for x, k, hp in row_defs[r] if k == 3 and 1 <= x <= min_x)
            if blocking_hp < 200 and (has_monk or not has_kind(r, 1, {1, 2})):
                for sx in (4, 3, 2, 1):
                    if sx < min_x and place(3, sx, r):
                        break

        # D. Emergency breach protection (enemy at x <= 2)
        if min_x <= 2:
            blocking_hp = sum(hp for x, k, hp in row_defs[r] if k == 3 and x <= min_x)
            if blocking_hp == 0 and not has_kind(r, 0):
                if not place(0, max(1, min_x - 1), r):
                    if not place(3, max(0, min_x - 1), r):
                        place(3, min_x, r)

    # 2. Scale global DPS up to 5-6 Archers at x=0 when all threatened rows are protected!
    if queued > 0 and total_archers() < 6:
        safe_archer_rows = sorted(
            [r for r in range(6) if not has_kind(r, 2, {0})],
            key=lambda r: (
                len(row_enems[r]) > 0 and shield_hp(r, {2, 3, 4}) < 250,
                -shield_hp(r, {2, 3, 4}),
                r,
            ),
        )
        for r in safe_archer_rows:
            if total_archers() < 6 and coins >= costs.get(2, 300):
                if shield_hp(r, {2, 3, 4}) >= 250 or not row_enems[r]:
                    place(2, 0, r)

    # 3. If any row has an Archer at x=0 AND active enemies (or enemies queued) but NO Shield at all, shield it at x=4!
    if queued > 0 and total_archers() >= 4:
        for r in range(6):
            if has_kind(r, 2, {0}) and not has_kind(r, 1, {1, 2}) and shield_hp(r, {2, 3, 4}) == 0:
                if coins >= costs.get(3, 150) + 100:
                    place(3, 4, r)

    return cards
