"""
Terminal output renderer for race predictions.
Uses box-drawing characters and probability bars.
"""
import sys
from typing import Dict, List, Any

W = 72  # box width

COMPOUND_LABELS = {"C1": "Hard", "C2": "Hard", "C3": "Medium", "C4": "Medium",
                   "C5": "Soft", "C6": "Soft"}


def _box(title: str) -> str:
    bar = "═" * (W - 2)
    return f"\n╔{bar}╗\n║  {title:<{W-4}}║\n╚{bar}╝"


def _rule(char: str = "─") -> str:
    return char * W


def _bar(prob: float, width: int = 20) -> str:
    filled = int(round(prob * width))
    return "█" * filled + "░" * (width - filled)


def _pct(p: float) -> str:
    return f"{p * 100:5.1f}%"


def show(
    race: Dict,
    track: Dict,
    weather: Dict,
    results: List[Dict],
    strategies: List[Dict],
    n_sims: int = 5000,
    pace_source: str = "championship",
):
    out = []
    out.append(_box(f"RACE PREDICTION: {race.get('raceName', '?').upper()}"))

    # Race info
    out.append(f"  Round {race.get('round','?')}  |  "
               f"{track.get('name','?')}  |  "
               f"{race.get('Circuit', {}).get('Location', {}).get('country','?')}")
    out.append(f"  Date : {race.get('date','?')}  |  "
               f"Laps : {track.get('laps','?')}  |  "
               f"Length : {track.get('length_km','?')} km")
    out.append("")

    # Conditions
    out.append(_box("RACE CONDITIONS"))
    air   = weather.get("air_temp", "?")
    trk   = weather.get("track_temp", "?")
    rain  = weather.get("rain_prob", 0)
    wind  = weather.get("wind_kmh", "?")
    src   = weather.get("source", "")
    out.append(f"  Air temp    : {air}°C   Track temp : ~{trk}°C  ({src})")
    out.append(f"  Rain prob   : {_pct(rain)}   Wind       : {wind} km/h")

    compounds = track.get("compounds", [])
    cstr = "  /  ".join(f"{c} ({COMPOUND_LABELS.get(c,'?')})" for c in compounds)
    out.append(f"  Compounds   : {cstr}")
    _WEAR_LABELS = ["LOW", "LOW", "MED", "HIGH", "EXTREME"]
    wear = track.get("tire_wear", 3)
    out.append(f"  Tire wear   : {'▓' * wear}{'░' * (5 - wear)}  "
               f"{_WEAR_LABELS[min(wear - 1, 4)]}")
    out.append(f"  Overtaking  : {'▓' * track.get('overtaking', 3)}"
               f"{'░' * (5 - track.get('overtaking', 3))}  "
               f"DRS zones: {track.get('drs_zones','?')}")
    out.append(f"  Safety car  : {_pct(track.get('sc_prob', 0.4))} historical probability")
    if track.get("notes"):
        out.append(f"  Note        : {track['notes']}")

    # Predicted finish order
    out.append(_box("PREDICTED FINISH ORDER"))
    data_label = ("qualifying data" if pace_source == "qualifying"
                  else "qualifying form" if pace_source == "quali_form"
                  else "championship standings")
    out.append(f"  Based on: {data_label}  |  Monte Carlo: {n_sims:,} simulations")
    out.append("")

    header = f"  {'Pos':<4} {'Driver':<22} {'Team':<16} {'Win':>6} {'Podium':>8} {'Pts':>6}  Confidence"
    out.append(header)
    out.append("  " + _rule("─")[:-2])

    for i, r in enumerate(results[:20]):
        pos   = f"P{i+1}"
        name  = r["name"][:21]
        team  = _short_team(r["constructor_id"])[:15]
        win   = _pct(r["win_prob"])
        pod   = _pct(r["podium_prob"])
        pts   = _pct(r["points_prob"])
        bar   = _bar(r["win_prob"], 14)
        dnf_s = f"  DNF:{_pct(r['dnf_sim_rate'])}" if r["dnf_sim_rate"] > 0.05 else ""
        line  = f"  {pos:<4} {name:<22} {team:<16} {win} {pod:>8} {pts:>6}  {bar}{dnf_s}"
        out.append(line)

    # Tire strategy
    out.append(_box("OPTIMAL TIRE STRATEGIES"))
    if strategies:
        for i, s in enumerate(strategies[:4]):
            stops  = s["stops"]
            stints = "  ->  ".join(
                f"{st['compound']} ({COMPOUND_LABELS.get(st['compound'],'?')}) {st['laps']}L"
                for st in s["stints"]
            )
            cost   = s["time_cost"]
            tag    = " ◈ OPTIMAL" if i == 0 else ""
            pit_info = ""
            if stops == 1 and "pit_lap" in s:
                pit_info = f"  Pit lap: ~{s['pit_lap']}"
            elif stops == 2 and "pit_laps" in s:
                pit_info = f"  Pit laps: ~{s['pit_laps'][0]}, ~{s['pit_laps'][1]}"
            out.append(f"  {stops}-stop  {stints}{pit_info}  [{cost:+.1f}s base cost]{tag}")
    else:
        out.append("  No strategy data available.")

    # Key factors
    out.append(_box("KEY FACTORS ANALYSIS"))

    # Tire temp analysis
    # Note: tire OPERATING temps (80-130°C) ≠ track surface temp (20-60°C).
    # We estimate operating temp: tire_op ≈ track_temp * 1.8 + 40 (empirical).
    from prediction.tracks import TIRE_COMPOUNDS
    trk_t    = weather.get("track_temp", 40.0)
    air_t    = weather.get("air_temp", 22.0)
    tire_op  = round(trk_t * 1.8 + air_t * 0.4 + 18, 1)  # estimated tire operating temp
    out.append(f"  [Tire Temperature]")
    out.append(f"  Track surface: {trk_t}°C  ->  Est. tire operating temp: ~{tire_op}°C")
    for c in compounds:
        tc    = TIRE_COMPOUNDS.get(c, {})
        t_min = tc.get("optimal_min", 90)
        t_max = tc.get("optimal_max", 110)
        window = f"{t_min}-{t_max}°C"
        if tire_op < t_min:
            delta  = t_min - tire_op
            status = f"COLD RISK (+{delta:.0f}°C to optimum — {tc.get('warmup_laps',3)+1} warm-up laps)"
        elif tire_op > t_max:
            delta  = tire_op - t_max
            status = f"OVERHEATING RISK (+{delta:.0f}°C above optimum — faster degradation)"
        else:
            status = f"OPTIMAL WINDOW (margin: -{tire_op - t_min:.0f}/+{t_max - tire_op:.0f}°C)"
        out.append(f"  ▸  {c} {COMPOUND_LABELS.get(c,'?'):<7}  Window: {window:<14}  [{status}]")
        out.append(f"     Warm-up: {tc.get('warmup_laps',3)} laps  "
                   f"Peak life: ~{tc.get('peak_laps',25)} laps  "
                   f"Lap-time vs C4: {tc.get('gap_vs_c4',0):+.2f}s")

    # Top driver factors
    out.append(f"\n  [Driver Factor Breakdown]")
    out.append(f"  {'Driver':<22} {'Pace src':<14} {'Form':>6} {'Rel':>6} "
               f"{'TireMgt':>8} {'Wet':>5} {'Affinity':>9}")
    out.append("  " + _rule("─")[:-2])
    for r in results[:10]:
        src_s = ("QUALI" if r["pace_source"] == "qualifying"
                  else "Q·FORM" if r["pace_source"] == "quali_form"
                  else "CHAMP")
        out.append(
            f"  {r['name'][:21]:<22} {src_s:<14}"
            f" {_pct(r['form']):>6}"
            f" {_pct(r['reliability']):>6}"
            f" {_pct(r['tire_mgmt']):>8}"
            f" {_pct(r['wet_skill']):>5}"
            f" {_pct(r['track_affinity']):>9}"
        )

    # Scenarios
    out.append(_box("SCENARIO ANALYSIS"))
    top3 = results[:3]

    if weather.get("rain_prob", 0) >= 0.25:
        wet_winners = sorted(results, key=lambda x: -x["wet_skill"])[:3]
        out.append(f"  RAIN SCENARIO ({_pct(weather['rain_prob'])} probability):")
        for r in wet_winners[:3]:
            out.append(f"  ▸  {r['name']} — wet skill {_pct(r['wet_skill'])}  "
                       f"boosted win prob")

    out.append(f"  SAFETY CAR ({_pct(track.get('sc_prob',0.4))}):")
    out.append(f"  ▸  High SC probability bunches field — pit timing becomes critical")
    out.append(f"  ▸  Undercut window opens if SC deployed before lap {int(track.get('laps',60) * 0.4)}")

    # Championship impact
    out.append(f"\n  CHAMPIONSHIP IMPACT (top 5 in standings):")
    top5_standings = sorted(results, key=lambda x: x["championship_pos"])[:5]
    for r in top5_standings:
        pts_gain = "25" if results.index(r) == 0 else "18/15/12/10..."
        out.append(f"  ▸  P{r['championship_pos']} {r['name']:<22} "
                   f"{int(r['championship_pts'])} pts  |  "
                   f"Predicted P{results.index(r)+1} (win prob {_pct(r['win_prob'])})")

    # Dark horse
    dark_horses = [r for r in results[5:] if r["win_prob"] > 0.01]
    if dark_horses:
        out.append(_box("DARK HORSE ALERTS"))
        for r in dark_horses[:3]:
            out.append(f"  ▸  {r['name']} ({_short_team(r['constructor_id'])})  "
                       f"Win: {_pct(r['win_prob'])}  Podium: {_pct(r['podium_prob'])}  "
                       f"— {_dark_horse_reason(r, track)}")

    # Footer
    out.append("")
    out.append("═" * W)
    out.append(f"  Monte Carlo: {n_sims:,} sims  |  Factors: 12 per driver  |  "
               f"APIs: Ergast + OpenF1 + Open-Meteo")
    out.append("═" * W)

    print("\n".join(out))


def _short_team(constructor_id: str) -> str:
    MAP = {
        "red_bull": "Red Bull", "mercedes": "Mercedes", "ferrari": "Ferrari",
        "mclaren": "McLaren", "aston_martin": "Aston Martin", "alpine": "Alpine",
        "williams": "Williams", "rb": "RB", "sauber": "Sauber/Audi", "haas": "Haas",
    }
    return MAP.get(constructor_id, constructor_id.replace("_", " ").title())


def _dark_horse_reason(r: Dict, track: Dict) -> str:
    reasons = []
    if r["track_affinity"] > 0.3:
        reasons.append("strong circuit history")
    if r["wet_skill"] > 0.82 and track.get("sc_prob", 0) > 0.5:
        reasons.append("high SC/rain skill")
    if r["tire_mgmt"] > 0.85:
        reasons.append("elite tire management")
    if r["form"] > 0.75:
        reasons.append("in strong form")
    return ", ".join(reasons) if reasons else "statistical outlier"
