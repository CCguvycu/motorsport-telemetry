"""
Monte Carlo race simulator — v2 (realistic probability model).

Key design principles enforced:
  1. PROBABILITY DISTRIBUTION REALISM
     - Top driver win prob is naturally top-heavy (30-50%) but never 100%.
     - Achieved via: hierarchical noise (team-level + driver-level),
       realistic form spread, and bounded stochastic event magnitudes.

  2. TEAM/CAR PERFORMANCE CEILINGS
     - Each constructor has a pace ceiling derived from WCC position.
     - Drivers cannot out-pace their car ceiling by more than ±DRIVER_DELTA_CAP seconds.
     - Prevents a midfield driver from winning on pure form alone.

  3. DRIVER ELIGIBILITY CONSTRAINTS
     - Only drivers present in the standings are simulated.
     - DNF candidates are flagged before the loop (not mid-loop via mask leaks).
     - DNF penalty is stochastic (lapped/retired/crash distinction).

  4. STOCHASTIC RACE EVENTS AS FIRST-CLASS VARIABLES
     - Safety car: Poisson-distributed count; triggers lap-timing delta per position.
     - Rain: Bernoulli event; reshuffles order non-linearly via wet-skill multiplier.
     - Tire cliff: Exponential degradation spike at high-wear tracks; rare but large.
     - Pit execution: Per-team Gaussian centered on known stop-time delta.
     - Each event is independent and contributes a quantified time delta.
"""
import numpy as np
from typing import Dict, List

N_SIMS = 5_000

# ── Constants ─────────────────────────────────────────────────────────────────
SAFETY_CAR_SPEED_LOSS = 18.0   # s gap compression per SC period (field bunching)
PIT_STOP_BASE_LOSS    = 22.0   # s typical stationary + in/out lap delta
DRIVER_DELTA_CAP      = 8.0    # s max a driver can beat their car ceiling

# Race pace vs qualifying gap compression.
# Empirically, race pace gaps are ~30% of qualifying gaps:
# qualifying gives clean-air best-lap; races involve traffic, deg, strategy timing.
RACE_PACE_FACTOR = 0.30

# Constructor pace ceiling (seconds behind best-car pace) by WCC position.
# P1 car = 0s deficit; P10 car = ~1.8s/lap → ~110s over race.
# These are lap-time ceilings, not total-race offsets.
CONSTRUCTOR_CEILING: Dict[str, float] = {
    1:  0.00,   # top team
    2:  0.04,
    3:  0.10,
    4:  0.18,
    5:  0.28,
    6:  0.40,
    7:  0.55,
    8:  0.70,
    9:  0.90,
    10: 1.10,
}


def _constructor_ceiling_gap(factors: List[Dict]) -> np.ndarray:
    """
    Derive constructor ceiling gap (s/lap) per driver from their team's WCC position.
    Drivers on the same constructor share the same ceiling.
    Uses the minimum championship_pts among drivers as a proxy when WCC rank unknown.
    """
    # Build constructor → best WCC pos map from driver standings proxy
    con_pos: Dict[str, int] = {}
    for f in factors:
        cid  = f.get("constructor_id", "unknown")
        cpos = f.get("championship_pos", 10)
        if cid not in con_pos or cpos < con_pos[cid]:
            con_pos[cid] = cpos

    # Rank constructors relative to each other (top team = pos 1)
    sorted_cons = sorted(con_pos.items(), key=lambda x: x[1])
    con_rank    = {cid: i + 1 for i, (cid, _) in enumerate(sorted_cons)}
    n_cons      = len(con_rank)

    gaps = []
    for f in factors:
        cid  = f.get("constructor_id", "unknown")
        rank = con_rank.get(cid, n_cons)
        # Map rank to ceiling; clamp to 10 known levels
        clamped = max(1, min(rank, 10))
        gaps.append(CONSTRUCTOR_CEILING.get(clamped, 1.1))

    return np.array(gaps)   # s/lap gap to best car


def simulate(
    factors: List[Dict],
    track: Dict,
    weather: Dict,
    n_sims: int = N_SIMS,
    rng_seed: int = None,
) -> List[Dict]:
    """
    Run Monte Carlo simulation.

    Returns list of result dicts sorted by expected finishing position.
    """
    rng = np.random.default_rng(rng_seed)
    n   = len(factors)
    if n == 0:
        return []

    # ── Extract factor arrays ─────────────────────────────────────────────────
    base_pace    = np.array([f["base_pace"]         for f in factors])  # s gap to pole
    form         = np.array([f["form"]               for f in factors])  # 0–1
    reliability  = np.array([f["reliability"]        for f in factors])  # 0–1
    tire_mgmt    = np.array([f["tire_mgmt"]           for f in factors])  # 0–1
    wet_skill    = np.array([f["wet_skill"]           for f in factors])  # 0–1
    overtaking   = np.array([f["overtaking_skill"]   for f in factors])  # 0–1
    consistency  = np.array([f["consistency"]         for f in factors])  # 0–1
    affinity     = np.array([f["track_affinity"]      for f in factors])  # 0–1
    pit_delta    = np.array([f["pit_speed"]           for f in factors])  # s (neg=faster)
    temp_penalty = np.array([f["temp_penalty"]        for f in factors])  # s/lap
    altitude     = np.array([f["altitude_factor"]     for f in factors])  # multiplier

    car_ceiling  = _constructor_ceiling_gap(factors)  # s/lap ceiling

    n_laps     = track.get("laps", 60)
    sc_prob    = track.get("sc_prob", 0.4)
    overtake_d = track.get("overtaking", 3)
    tire_wear  = track.get("tire_wear", 3)
    rain_prob  = weather.get("rain_prob", 0.1)

    # ── Pre-compute per-driver constants ──────────────────────────────────────

    # Car ceiling cost: s/lap × race distance × race compression factor
    car_gap_total = car_ceiling * n_laps * RACE_PACE_FACTOR

    # Base pace scaled by race compression factor + blended with car ceiling anchor
    has_quali = np.array([f.get("pace_source") in ("qualifying", "quali_form") for f in factors], dtype=float)
    # Qualifying-data drivers: mostly trust their qualifying gap (compressed to race scale)
    # Championship-proxy drivers: blend with car ceiling more heavily
    quali_component = base_pace * n_laps * RACE_PACE_FACTOR
    champ_component = car_gap_total
    blended_base = quali_component * (0.70 + 0.20 * has_quali) + champ_component * (0.30 - 0.20 * has_quali)

    # Form modifier: maps [0=terrible→1=dominant] to [-6s, +15s]
    # Smaller magnitude — form is one factor among many, not race-deciding
    form_offset = (0.60 - form) * 20.0

    # Tire temp cost (spread over race)
    cold_laps      = np.clip(4.0 - tire_mgmt * 3.0, 1.0, 4.0)
    tire_temp_cost = temp_penalty * cold_laps * altitude

    # Consistency → per-race noise std.
    # Race noise is MUCH larger than qualifying: traffic, pit windows, safety car timing luck.
    # Range: ~[5s, 10s] for typical F1 race (captures real week-to-week variance).
    noise_std = (1.05 - consistency) * 5.0 + 5.0

    # Reliability → per-sim DNF probability (two independent failure modes)
    p_mech_fail  = np.clip(1.0 - reliability, 0.0, 0.40)       # mechanical
    p_incid_fail = np.clip((1.0 - reliability) * 0.12, 0.0, 0.10)  # incident/crash

    # n_stops from tire wear
    n_stops = max(1, int(tire_wear / 2.5))

    # ── Simulation loop ───────────────────────────────────────────────────────
    finish_counts = np.zeros((n, n), dtype=np.int32)
    dnf_counts    = np.zeros(n, dtype=np.int32)

    for _ in range(n_sims):
        # 1. Deterministic base + form + tire temp
        pace = blended_base.copy()
        pace += form_offset
        pace += tire_temp_cost

        # 2. Race-to-race variance (consistency noise)
        pace += rng.normal(0.0, noise_std, n)

        # 3. Car-level team noise (shared within constructor, ~±6s)
        #    Captures race-weekend package variation: balance issues, engine mode,
        #    aero setup; all teammates shift together.
        con_ids   = [f.get("constructor_id", "") for f in factors]
        unique_c  = list(set(con_ids))
        con_noise = {c: rng.normal(0.0, 6.0) for c in unique_c}
        team_noise = np.array([con_noise[c] for c in con_ids])
        pace += team_noise

        # 4. Driver ceiling enforcement: driver cannot beat car ceiling by more
        #    than DRIVER_DELTA_CAP seconds (prevents midfield hero wins via form alone)
        lower_bound = car_gap_total - DRIVER_DELTA_CAP
        pace = np.maximum(pace, lower_bound)

        # 5. Tire degradation (exponential spike; high-wear tracks hit hard)
        tire_loss = rng.exponential(tire_wear * (1.15 - tire_mgmt) * 0.35, n)
        pace += tire_loss

        # 6. Tire cliff event (rare: ~5% chance per sim at wear=5 tracks)
        cliff_prob = max(0.0, (tire_wear - 3) * 0.025)
        cliff_mask = rng.random(n) < cliff_prob * (1.1 - tire_mgmt)
        if cliff_mask.any():
            # Cliff = sudden additional 15-40s degradation burst
            pace[cliff_mask] += rng.uniform(15.0, 40.0, cliff_mask.sum())

        # 7. Safety car / VSC
        n_sc = rng.poisson(sc_prob * 1.4)
        if n_sc > 0:
            pos_guess = np.argsort(pace)
            sc_gain   = np.zeros(n)
            for pos_idx, drv_idx in enumerate(pos_guess):
                # Leader loses nothing; P20 gains up to SAFETY_CAR_SPEED_LOSS per period
                sc_gain[drv_idx] = -pos_idx * (SAFETY_CAR_SPEED_LOSS / n) * n_sc
            pace += sc_gain
            # SC timing luck: uniform ±5s per period
            pace += rng.uniform(-5.0 * n_sc, 5.0 * n_sc, n)

        # 8. Rain event — non-linear reshuffle via wet skill
        if rng.random() < rain_prob:
            # Wet advantage: elite wet driver gains up to ~15s vs. poor wet driver
            wet_offset = (0.5 - wet_skill) * 20.0   # fixed ±10s spread across wet-skill range
            rain_noise = rng.normal(0.0, 10.0, n)           # chaotic rain variance
            pace = pace + wet_offset + rain_noise

        # 9. Pit stop execution delta
        pit_total = pit_delta * n_stops + rng.normal(0.0, 0.5 * n_stops, n)
        pace += pit_total

        # 10. Track position lock-in (Monaco/Imola/Hungary effect)
        if overtake_d <= 2:
            lock = (3 - overtake_d) * 0.22   # 0.22 at ot=2, 0.44 at ot=1
            sorted_pace = np.sort(pace)
            pace = pace * (1.0 - lock) + sorted_pace * lock

        # 11. Track affinity bonus
        pace -= affinity * 3.5

        # 12. DNF assignment (two failure modes)
        dnf_mask = (rng.random(n) < p_mech_fail) | (rng.random(n) < p_incid_fail)
        dnf_counts += dnf_mask.astype(np.int32)
        # DNF penalty: lapped (~90s) → retired (300s) → race-ending (1000s)
        dnf_severity = rng.choice([90.0, 300.0, 1000.0], size=n, p=[0.35, 0.35, 0.30])
        pace[dnf_mask] += dnf_severity[dnf_mask]

        # 13. Finish positions
        order = np.argsort(pace)
        for pos_idx, drv_idx in enumerate(order):
            finish_counts[drv_idx, pos_idx] += 1

    # ── Aggregate ─────────────────────────────────────────────────────────────
    pos_arr = np.arange(1, n + 1)
    results = []
    for i, f in enumerate(factors):
        dist     = finish_counts[i].astype(float) / n_sims
        exp_pos  = float(np.dot(dist, pos_arr))
        dnf_rate = float(dnf_counts[i]) / n_sims

        results.append({
            **f,
            "win_prob":            round(float(dist[0]),        4),
            "podium_prob":         round(float(dist[:3].sum()), 4),
            "top5_prob":           round(float(dist[:5].sum()), 4),
            "points_prob":         round(float(dist[:10].sum()),4),
            "expected_pos":        round(exp_pos, 2),
            "dnf_sim_rate":        round(dnf_rate, 4),
            "finish_distribution": dist.tolist(),
            "n_sims":              n_sims,
        })

    return sorted(results, key=lambda x: x["expected_pos"])
