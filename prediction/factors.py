"""
Build per-driver factor vectors from API data.

Every variable that feeds the simulator is computed here:
  base_pace      - qualifying gap to pole (or championship-position proxy)
  form           - weighted recent-race performance  [0=terrible, 1=perfect]
  reliability    - 1 - DNF_rate this season
  tire_mgmt      - tire management rating  [0-1]
  wet_skill      - wet weather skill  [0-1]
  track_affinity - historical podium rate at this circuit  [0-1]
  pit_speed      - constructor pit stop delta (s, negative = faster)
  altitude_adapt - altitude/heat sensitivity modifier
"""
import math
from typing import Dict, List, Optional
from prediction.tracks import TRACKS, PIT_SPEED, TIRE_COMPOUNDS

# ── Static driver ratings (0-10) based on known performance profile ────────
# Updated for 2024/2025 season. Keys match Ergast driverId.
DRIVER_RATINGS: Dict[str, Dict] = {
    "max_verstappen":     {"tire": 9.2, "wet": 9.5, "overtaking": 9.5, "consistency": 9.3},
    "leclerc":            {"tire": 7.5, "wet": 8.5, "overtaking": 8.5, "consistency": 7.8},
    "norris":             {"tire": 8.5, "wet": 8.5, "overtaking": 8.5, "consistency": 8.5},
    "piastri":            {"tire": 8.0, "wet": 8.0, "overtaking": 8.0, "consistency": 8.2},
    "hamilton":           {"tire": 9.0, "wet": 9.5, "overtaking": 9.0, "consistency": 8.5},
    "russell":            {"tire": 7.8, "wet": 8.0, "overtaking": 7.5, "consistency": 8.0},
    "sainz":              {"tire": 8.5, "wet": 8.0, "overtaking": 7.8, "consistency": 8.3},
    "alonso":             {"tire": 9.0, "wet": 9.0, "overtaking": 8.5, "consistency": 8.5},
    "stroll":             {"tire": 6.5, "wet": 7.5, "overtaking": 6.0, "consistency": 6.5},
    "ocon":               {"tire": 7.0, "wet": 7.0, "overtaking": 6.5, "consistency": 7.0},
    "gasly":              {"tire": 7.0, "wet": 7.0, "overtaking": 7.0, "consistency": 7.0},
    "albon":              {"tire": 7.2, "wet": 7.2, "overtaking": 7.0, "consistency": 7.2},
    "bottas":             {"tire": 7.5, "wet": 7.5, "overtaking": 7.0, "consistency": 7.5},
    "zhou":               {"tire": 6.5, "wet": 6.5, "overtaking": 6.0, "consistency": 6.5},
    "tsunoda":            {"tire": 6.8, "wet": 7.0, "overtaking": 7.5, "consistency": 6.5},
    "ricciardo":          {"tire": 7.5, "wet": 7.5, "overtaking": 8.0, "consistency": 7.0},
    "lawson":             {"tire": 7.0, "wet": 7.0, "overtaking": 7.5, "consistency": 7.2},
    "hulkenberg":         {"tire": 7.2, "wet": 7.5, "overtaking": 7.0, "consistency": 7.5},
    "magnussen":          {"tire": 6.5, "wet": 7.0, "overtaking": 6.8, "consistency": 6.5},
    "bearman":            {"tire": 7.0, "wet": 7.0, "overtaking": 7.0, "consistency": 7.0},
    "colapinto":          {"tire": 7.0, "wet": 7.0, "overtaking": 7.0, "consistency": 7.0},
    "hadjar":             {"tire": 7.0, "wet": 7.0, "overtaking": 7.0, "consistency": 7.0},
    "antonelli":          {"tire": 7.5, "wet": 7.5, "overtaking": 7.5, "consistency": 7.5},
    "doohan":             {"tire": 6.8, "wet": 6.8, "overtaking": 6.8, "consistency": 6.8},
    "bortoleto":          {"tire": 7.0, "wet": 7.0, "overtaking": 7.2, "consistency": 7.0},
    "default":            {"tire": 7.0, "wet": 7.0, "overtaking": 7.0, "consistency": 7.0},
}


def get_driver_rating(driver_id: str) -> Dict:
    return DRIVER_RATINGS.get(driver_id, DRIVER_RATINGS["default"])


# ── Form computation ───────────────────────────────────────────────────────

def compute_form(driver_id: str, season_results: List[Dict], n: int = 6) -> float:
    """
    Weighted recent-race score. Last race counts 2x, 2nd-last 1.5x, etc.
    Returns 0 (terrible) to 1 (dominant).
    """
    finishes = []
    for race in reversed(season_results):
        for result in race.get("Results", []):
            if result.get("Driver", {}).get("driverId") == driver_id:
                pos = result.get("position", "20")
                status = result.get("status", "")
                if any(x in status for x in ("DNF", "Retired", "Accident", "Engine",
                                        "Gearbox", "Hydraulics", "Electrical", "Collision")):
                    finishes.append(20)
                else:
                    try:
                        finishes.append(int(pos))
                    except ValueError:
                        finishes.append(20)
                break
        if len(finishes) >= n:
            break

    if not finishes:
        return 0.5

    weights = [2.0, 1.5, 1.2, 1.0, 0.9, 0.8][:len(finishes)]
    weighted_pos = sum(p * w for p, w in zip(finishes, weights)) / sum(weights)
    # P1 = 1.0, P10 = 0.5, P20 = 0.0
    return max(0.0, min(1.0, 1.0 - (weighted_pos - 1) / 19))


def compute_reliability(driver_id: str, season_results: List[Dict]) -> float:
    """1.0 = no DNFs this season. Decays per DNF."""
    total, dnfs = 0, 0
    for race in season_results:
        for result in race.get("Results", []):
            if result.get("Driver", {}).get("driverId") == driver_id:
                total += 1
                s = result.get("status", "")
                if any(x in s for x in ("DNF", "Retired", "Accident", "Engine",
                                        "Gearbox", "Hydraulics", "Electrical")):
                    dnfs += 1
    if total == 0:
        return 0.92  # unknown = slight uncertainty
    return max(0.6, 1.0 - (dnfs / total) * 1.2)


def compute_track_affinity(driver_id: str, circuit_id: str,
                            circuit_history: List[Dict]) -> float:
    """Fraction of top-3 finishes at this circuit over last 5 years. 0–1."""
    top3, total = 0, 0
    for race in circuit_history:
        for result in race.get("Results", []):
            if result.get("Driver", {}).get("driverId") == driver_id:
                total += 1
                try:
                    if int(result.get("position", 99)) <= 3:
                        top3 += 1
                except ValueError:
                    pass
    return (top3 / total) if total > 0 else 0.0


# ── Season qualifying form ────────────────────────────────────────────────

def compute_quali_form(driver_id: str, season_qualifying: List[Dict], n: int = 5) -> Optional[float]:
    """
    Weighted average gap-to-pole across the driver's last N qualifying sessions.
    Returns seconds (0.0 = pole pace), or None if no data available.
    Recency-weighted: most recent session counts 2x.
    """
    gaps: List[float] = []
    for race in season_qualifying:          # already sorted newest-first
        results = race.get("QualifyingResults", [])
        if not results:
            continue
        pole_time: Optional[float] = None
        for q in results:
            t = q.get("Q3") or q.get("Q2") or q.get("Q1", "")
            sec = _parse_time(t)
            if sec is not None and (pole_time is None or sec < pole_time):
                pole_time = sec
        if pole_time is None:
            continue
        for q in results:
            if q.get("Driver", {}).get("driverId") == driver_id:
                t = q.get("Q3") or q.get("Q2") or q.get("Q1", "")
                sec = _parse_time(t)
                if sec is not None:
                    gaps.append(sec - pole_time)
                break
        if len(gaps) >= n:
            break

    if not gaps:
        return None

    weights = [2.0, 1.5, 1.2, 1.0, 0.9][: len(gaps)]
    return sum(g * w for g, w in zip(gaps, weights)) / sum(weights)


# ── Qualifying pace proxy when quali data isn't available ─────────────────

def position_to_pace_gap(championship_position: int, total_drivers: int = 20) -> float:
    """
    Approximate qualifying gap (seconds to pole) from championship position.
    Uses log curve: P1=0s, P5~0.3s, P10~0.5s, P20~0.8s.
    """
    if championship_position <= 1:
        return 0.0
    return 0.22 * math.log(championship_position)


# ── Main builder ──────────────────────────────────────────────────────────

def build_factors(
    driver_standings: List[Dict],
    constructor_standings: List[Dict],
    season_results: List[Dict],
    qualifying_results: List[Dict],
    circuit_history: List[Dict],
    circuit_id: str,
    weather: Dict,
    track: Dict,
    season_qualifying: Optional[List[Dict]] = None,
) -> List[Dict]:
    """
    Return a list of factor dicts, one per driver in the standings.
    """
    # Build constructor reliability + standings map
    con_map = {
        s["Constructor"]["constructorId"]: {
            "position": int(s["position"]),
            "points":   float(s["points"]),
        }
        for s in constructor_standings
    }

    # Qualifying times: driver_id → seconds gap to pole
    quali_map: Dict[str, float] = {}
    if qualifying_results:
        pole_time: Optional[float] = None
        for q in qualifying_results:
            t = (q.get("Q3") or q.get("Q2") or q.get("Q1") or "")
            sec = _parse_time(t)
            if sec is not None and (pole_time is None or sec < pole_time):
                pole_time = sec
        if pole_time is not None:
            for q in qualifying_results:
                did = q["Driver"]["driverId"]
                t = (q.get("Q3") or q.get("Q2") or q.get("Q1") or "")
                sec = _parse_time(t)
                if sec is not None:
                    quali_map[did] = sec - pole_time

    # Tire temperature modifier: how far track temp is from each compound's optimum.
    # IMPORTANT: compound windows are tire OPERATING temps (~70-135°C), not surface temps.
    # Estimate operating temp: tire_op ≈ track_temp * 1.8 + air_temp * 0.4 + 18 (empirical)
    track_temp    = weather.get("track_temp", 40.0)
    air_temp      = weather.get("air_temp", 22.0)
    tire_op_temp  = round(track_temp * 1.8 + air_temp * 0.4 + 18, 1)
    compounds    = track.get("compounds", ["C2", "C3", "C4"])
    best_compound = _best_compound(compounds, tire_op_temp)

    factors = []
    for s in driver_standings:
        d      = s["Driver"]
        did    = d["driverId"]
        dname  = f"{d['givenName']} {d['familyName']}"
        con_id = s["Constructors"][0]["constructorId"] if s.get("Constructors") else "unknown"

        champ_pos  = int(s["position"])
        champ_pts  = float(s["points"])
        wins       = int(s.get("wins", 0))

        ratings    = get_driver_rating(did)
        form       = compute_form(did, season_results)
        reliability= compute_reliability(did, season_results)
        affinity   = compute_track_affinity(did, circuit_id, circuit_history)

        # Base pace priority: round quali > season quali form > championship proxy
        if did in quali_map:
            base_pace   = quali_map[did]
            pace_source = "qualifying"
        elif season_qualifying:
            qf = compute_quali_form(did, season_qualifying)
            if qf is not None:
                base_pace   = qf
                pace_source = "quali_form"
            else:
                base_pace   = position_to_pace_gap(champ_pos)
                pace_source = "championship"
        else:
            base_pace   = position_to_pace_gap(champ_pos)
            pace_source = "championship"

        # Tire management modifier on base pace
        tire_skill = ratings["tire"] / 10.0  # 0-1
        # Temp penalty: tire outside optimal window costs lap time
        temp_penalty = _tire_temp_penalty(best_compound, tire_op_temp, track.get("tire_wear", 3))

        # Altitude modifier (Mexico, etc.)
        altitude_factor = _altitude_factor(track.get("lat", 0), track.get("lon", 0))

        factors.append({
            "driver_id":        did,
            "name":             dname,
            "constructor_id":   con_id,
            "championship_pos": champ_pos,
            "championship_pts": champ_pts,
            "wins":             wins,
            "base_pace":        base_pace,
            "form":             form,
            "reliability":      reliability,
            "tire_mgmt":        tire_skill,
            "wet_skill":        ratings["wet"] / 10.0,
            "overtaking_skill": ratings["overtaking"] / 10.0,
            "consistency":      ratings["consistency"] / 10.0,
            "track_affinity":   affinity,
            "pit_speed":        PIT_SPEED.get(con_id, 0.0),
            "temp_penalty":     temp_penalty,
            "altitude_factor":  altitude_factor,
            "pace_source":      pace_source,
        })

    return sorted(factors, key=lambda x: x["base_pace"])


# ── Tire temperature model ────────────────────────────────────────────────

def _best_compound(compounds: List[str], track_temp: float) -> str:
    """Return compound whose optimal window best matches track temperature."""
    from prediction.tracks import TIRE_COMPOUNDS
    best, best_dist = compounds[0], float("inf")
    for c in compounds:
        tc = TIRE_COMPOUNDS.get(c, {})
        mid = (tc.get("optimal_min", 95) + tc.get("optimal_max", 115)) / 2
        if abs(mid - track_temp) < best_dist:
            best, best_dist = c, abs(mid - track_temp)
    return best


def _tire_temp_penalty(compound: str, track_temp: float, wear_rate: int) -> float:
    """
    Extra lap time (s) due to tire operating outside optimal temperature window.
    Cold = understeer/snap oversteer, Hot = rapid degradation.
    """
    from prediction.tracks import TIRE_COMPOUNDS
    tc     = TIRE_COMPOUNDS.get(compound, {})
    t_min  = tc.get("optimal_min", 85)
    t_max  = tc.get("optimal_max", 110)

    if track_temp < t_min:
        cold_delta = (t_min - track_temp) * 0.025
        return min(cold_delta, 0.8)  # cap at 0.8s
    elif track_temp > t_max:
        hot_delta = (track_temp - t_max) * 0.02 * (wear_rate / 3)
        return min(hot_delta, 1.2)
    return 0.0


def compute_optimal_strategy(track: Dict, weather: Dict) -> List[Dict]:
    """
    Return ranked list of 1-stop and 2-stop strategies with estimated total time.
    """
    from prediction.tracks import TIRE_COMPOUNDS
    compounds  = track.get("compounds", ["C2", "C3", "C4"])
    n_laps     = track.get("laps", 60)
    wear_rate  = track.get("tire_wear", 3)
    track_temp = weather.get("track_temp", 40.0)
    temp_factor= 1 + (track_temp - 30) * 0.015  # hot = faster degradation

    strategies = []

    def stint_life(c: str) -> float:
        tc = TIRE_COMPOUNDS.get(c, {})
        return tc.get("peak_laps", 25) / wear_rate / temp_factor

    # 1-stop options
    for c1 in compounds:
        for c2 in compounds:
            if c1 != c2:
                c1_life = stint_life(c1)
                if c1_life >= n_laps * 0.30:
                    split = int(min(c1_life * 0.88, n_laps * 0.55))
                    time_est = _strategy_cost([(c1, split), (c2, n_laps - split)], n_laps)
                    strategies.append({
                        "stops": 1,
                        "stints": [{"compound": c1, "laps": split},
                                    {"compound": c2, "laps": n_laps - split}],
                        "pit_lap": split,
                        "time_cost": time_est,
                    })

    # 2-stop options
    for c1 in compounds:
        for c2 in compounds:
            for c3 in compounds:
                c1_life = stint_life(c1)
                c2_life = stint_life(c2)
                p1 = int(c1_life * 0.85)
                p2 = int(p1 + c2_life * 0.80)
                if p2 < n_laps and p1 >= 8 and (p2 - p1) >= 8:
                    time_est = _strategy_cost(
                        [(c1, p1), (c2, p2 - p1), (c3, n_laps - p2)], n_laps)
                    strategies.append({
                        "stops": 2,
                        "stints": [
                            {"compound": c1, "laps": p1},
                            {"compound": c2, "laps": p2 - p1},
                            {"compound": c3, "laps": n_laps - p2},
                        ],
                        "pit_laps": [p1, p2],
                        "time_cost": time_est,
                    })

    strategies.sort(key=lambda s: s["time_cost"])
    return strategies[:5]  # top 5


def _strategy_cost(stints: List, n_laps: int) -> float:
    """Rough total race time cost (seconds) for a strategy."""
    from prediction.tracks import TIRE_COMPOUNDS
    PIT_LOSS = 22.0  # typical pit stop time loss
    total = (len(stints) - 1) * PIT_LOSS
    for compound, laps in stints:
        tc = TIRE_COMPOUNDS.get(compound, {})
        base_gap = tc.get("gap_vs_c4", 0.0)
        total += laps * base_gap  # faster compound = negative, saves time
    return total


def _altitude_factor(lat: float, lon: float) -> float:
    """Return pace modifier for high-altitude circuits (Mexico = +2% drag reduction)."""
    # Mexico City
    if 19.0 <= lat <= 20.0 and -100 <= lon <= -98:
        return 1.015  # thin air helps power-heavy cars
    return 1.0


def _parse_time(t: str) -> Optional[float]:
    if not t:
        return None
    try:
        parts = t.split(":")
        return int(parts[0]) * 60 + float(parts[1]) if len(parts) == 2 else float(t)
    except (ValueError, IndexError):
        return None
