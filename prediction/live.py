"""
Live race feed integration via OpenF1 API.

Converts real-time race state into factor overrides for the Monte Carlo simulator:
  - Current time gaps replace qualifying-derived base_pace
  - Tire compound + age from stints endpoint drives degradation cost
  - Safety car status compresses the field immediately
  - DNF detection removes retired drivers from the simulation
  - Live weather overrides forecast data
"""
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from prediction.api import _get, _cache

OPENF1 = "https://api.openf1.org/v1"

# ── Session detection ─────────────────────────────────────────────────────────

def get_active_session() -> Optional[Dict]:
    """
    Return the most recent Race session object, or None if nothing active.
    OpenF1 'session_key=latest' always returns the most recent session.
    """
    data = _get(f"{OPENF1}/sessions?session_type=Race&year={datetime.now().year}")
    if not data:
        return None
    # Sort by date_end descending; pick the most recent
    sessions = sorted(data, key=lambda s: s.get("date_end", ""), reverse=True)
    return sessions[0] if sessions else None


def is_session_live(session: Dict) -> bool:
    """Session is live if date_end is None (ongoing) or still in the future."""
    date_end = session.get("date_end")
    if date_end is None:
        return True
    try:
        end_dt = datetime.fromisoformat(date_end.replace("Z", "+00:00"))
        return end_dt > datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False


# ── Live state fetch ──────────────────────────────────────────────────────────

def get_live_state(session_key: str) -> Dict:
    """
    Fetch all live data for a session and merge into a single state dict.

    Returns:
        {
          "session_key":   str,
          "current_lap":   int,
          "total_laps":    int,
          "sc_active":     bool,
          "vsc_active":    bool,
          "red_flag":      bool,
          "weather":       dict,
          "drivers":       {driver_number: {...}},
          "positions":     {driver_number: int},
          "gaps":          {driver_number: float},   # seconds to leader
          "stints":        {driver_number: {...}},   # current stint info
          "dnf_numbers":   set,
        }
    """
    sk = f"session_key={session_key}"

    # Parallel fetch (serial with caching — all cached 5 min by api._cache)
    positions_raw = _get(f"{OPENF1}/position?{sk}") or []
    intervals_raw = _get(f"{OPENF1}/intervals?{sk}") or []
    stints_raw    = _get(f"{OPENF1}/stints?{sk}") or []
    laps_raw      = _get(f"{OPENF1}/laps?{sk}") or []
    rc_raw        = _get(f"{OPENF1}/race_control?{sk}") or []
    weather_raw   = _get(f"{OPENF1}/weather?{sk}") or []
    drivers_raw   = _get(f"{OPENF1}/drivers?{sk}") or []

    # ── Current positions (most recent entry per driver) ──────────────────────
    pos_latest: Dict[int, Dict] = {}
    for p in positions_raw:
        dn = p.get("driver_number")
        if dn and (dn not in pos_latest or p.get("date","") > pos_latest[dn].get("date","")):
            pos_latest[dn] = p

    positions = {dn: p.get("position", 99) for dn, p in pos_latest.items()}

    # ── Time gaps (most recent interval per driver) ───────────────────────────
    int_latest: Dict[int, Dict] = {}
    for iv in intervals_raw:
        dn = iv.get("driver_number")
        if dn and (dn not in int_latest or iv.get("date","") > int_latest[dn].get("date","")):
            int_latest[dn] = iv

    gaps: Dict[int, float] = {}
    for dn, iv in int_latest.items():
        raw_gap = iv.get("gap_to_leader")
        if raw_gap is None:
            gaps[dn] = 0.0          # leader
        elif isinstance(raw_gap, (int, float)):
            gaps[dn] = float(raw_gap)
        else:
            try:
                gaps[dn] = float(str(raw_gap).replace("+", "").replace("LAP", "").strip()) * (
                    90.0 if "LAP" in str(raw_gap) else 1.0
                )
            except (ValueError, TypeError):
                gaps[dn] = 999.0    # lapped / unknown

    # ── Current lap ──────────────────────────────────────────────────────────
    current_lap = 1
    if laps_raw:
        current_lap = max(l.get("lap_number", 1) for l in laps_raw if l.get("lap_number"))

    # ── Active stints (last entry per driver) ─────────────────────────────────
    stint_latest: Dict[int, Dict] = {}
    for st in stints_raw:
        dn = st.get("driver_number")
        if dn and (dn not in stint_latest or
                   st.get("stint_number", 0) > stint_latest[dn].get("stint_number", 0)):
            stint_latest[dn] = st

    # ── Race control: SC / VSC / red flag ─────────────────────────────────────
    sc_active  = False
    vsc_active = False
    red_flag   = False
    if rc_raw:
        recent_rc = sorted(rc_raw, key=lambda r: r.get("date", ""), reverse=True)
        for msg in recent_rc[:10]:
            cat = str(msg.get("category", "")).upper()
            flg = str(msg.get("flag", "")).upper()
            note = str(msg.get("message", "")).upper()
            if "SAFETY CAR" in note and "DEPLOYED" in note:
                sc_active = True; break
            if "VIRTUAL" in note and "DEPLOYED" in note:
                vsc_active = True; break
            if "RED FLAG" in flg or "RED FLAG" in note:
                red_flag = True; break
            if any(x in note for x in ("CLEAR", "WITHDRAWN", "RESUME")):
                sc_active = False; vsc_active = False; break

    # ── Live weather (most recent sample) ────────────────────────────────────
    weather_out = {}
    if weather_raw:
        w = sorted(weather_raw, key=lambda x: x.get("date", ""), reverse=True)[0]
        rain_pct = w.get("rainfall", 0)
        weather_out = {
            "air_temp":   w.get("air_temperature", 22.0),
            "track_temp": w.get("track_temperature", 38.0),
            "rain_prob":  1.0 if rain_pct and float(rain_pct) > 0 else 0.05,
            "wind_kmh":   round(float(w.get("wind_speed", 10)) * 3.6, 1),
            "source":     "OpenF1 Live",
        }

    # ── DNF detection: present in session but not seen in last 3 laps ────────
    active_laps = set()
    if laps_raw:
        cutoff = max(1, current_lap - 3)
        active_laps = {l.get("driver_number") for l in laps_raw
                       if l.get("lap_number", 0) >= cutoff and l.get("driver_number")}
    all_drivers = {p.get("driver_number") for p in positions_raw if p.get("driver_number")}
    dnf_numbers = all_drivers - active_laps if len(active_laps) > 0 else set()

    # ── Driver map: number → name_acronym / driver_id ─────────────────────────
    driver_map: Dict[int, Dict] = {}
    for d in drivers_raw:
        dn = d.get("driver_number")
        if dn:
            driver_map[dn] = {
                "acronym":    d.get("name_acronym", "???"),
                "full_name":  d.get("full_name", "Unknown"),
                "team_color": d.get("team_colour", "888888"),
                "team_name":  d.get("team_name", "?"),
            }

    return {
        "session_key":  session_key,
        "current_lap":  current_lap,
        "sc_active":    sc_active,
        "vsc_active":   vsc_active,
        "red_flag":     red_flag,
        "weather":      weather_out,
        "driver_map":   driver_map,
        "positions":    positions,
        "gaps":         gaps,
        "stints":       stint_latest,
        "dnf_numbers":  dnf_numbers,
    }


# ── Race event feed ───────────────────────────────────────────────────────────

def get_race_feed(session_key: str) -> List[Dict]:
    """
    Build a chronological event feed from OpenF1 data for a session.

    Combines:
      - race_control  → SC/VSC/red flag, fastest lap, DRS, penalties
      - pit           → pit stop entries with stationary time
      - position      → detected overtakes (position changes between samples)

    Returns list of event dicts sorted newest-first:
      {type, lap, driver, detail, timestamp, color}
    """
    sk = f"session_key={session_key}"
    rc_raw      = _get(f"{OPENF1}/race_control?{sk}") or []
    pit_raw     = _get(f"{OPENF1}/pit?{sk}") or []
    pos_raw     = _get(f"{OPENF1}/position?{sk}") or []
    drivers_raw = _get(f"{OPENF1}/drivers?{sk}") or []

    # Build driver number → acronym map
    dn_to_acr: Dict[int, str] = {}
    for d in drivers_raw:
        dn = d.get("driver_number")
        if dn:
            dn_to_acr[dn] = d.get("name_acronym", f"#{dn}")

    events: List[Dict] = []

    # ── Race control messages ─────────────────────────────────────────────────
    RC_COLOR = {
        "SC":        "#f5c518",   # yellow
        "VSC":       "#ffd700",
        "RED":       "#e10600",
        "CLEAR":     "#00c851",
        "FASTEST":   "#9b59b6",
        "DRS":       "#17a2b8",
        "PENALTY":   "#fd7e14",
        "OTHER":     "#6c757d",
    }

    for msg in rc_raw:
        note    = str(msg.get("message", ""))
        cat     = str(msg.get("category", "")).upper()
        flag    = str(msg.get("flag", "")).upper()
        lap     = msg.get("lap_number", "?")
        ts      = msg.get("date", "")
        note_up = note.upper()

        if "SAFETY CAR" in note_up and "DEPLOYED" in note_up:
            kind   = "SC"; color = RC_COLOR["SC"]
            detail = "Safety Car deployed"
        elif "VIRTUAL" in note_up and "DEPLOYED" in note_up:
            kind   = "VSC"; color = RC_COLOR["VSC"]
            detail = "Virtual Safety Car deployed"
        elif "RED FLAG" in flag or "RED FLAG" in note_up:
            kind   = "RED FLAG"; color = RC_COLOR["RED"]
            detail = "Red Flag — session stopped"
        elif any(x in note_up for x in ("CLEAR", "WITHDRAWN", "RESUME")):
            kind   = "CLEAR"; color = RC_COLOR["CLEAR"]
            detail = note if note else "Safety car withdrawn"
        elif "FASTEST LAP" in note_up:
            kind   = "FASTEST LAP"; color = RC_COLOR["FASTEST"]
            detail = note
        elif "DRS" in note_up:
            kind   = "DRS"; color = RC_COLOR["DRS"]
            detail = note
        elif "PENALTY" in note_up or "INVESTIGATE" in note_up or "BLACK" in flag:
            kind   = "PENALTY"; color = RC_COLOR["PENALTY"]
            detail = note
        else:
            if not note.strip():
                continue
            kind   = "INFO"; color = RC_COLOR["OTHER"]
            detail = note

        events.append({
            "type":      kind,
            "lap":       lap,
            "driver":    None,
            "detail":    detail,
            "timestamp": ts,
            "color":     color,
        })

    # ── Pit stops ─────────────────────────────────────────────────────────────
    for pit in pit_raw:
        dn    = pit.get("driver_number")
        lap   = pit.get("lap_number", "?")
        dur   = pit.get("pit_duration")
        ts    = pit.get("date", "")
        acr   = dn_to_acr.get(dn, f"#{dn}" if dn else "?")
        dur_s = f"{dur:.1f}s" if isinstance(dur, (int, float)) else "?"
        events.append({
            "type":      "PIT",
            "lap":       lap,
            "driver":    acr,
            "detail":    f"{acr} pits — {dur_s} stationary",
            "timestamp": ts,
            "color":     "#4fc3f7",
        })

    # ── Detected overtakes (position improvements ≥ 1 between consecutive samples) ─
    # Group position samples per driver, sort by date, find changes
    pos_by_driver: Dict[int, List[Dict]] = {}
    for p in pos_raw:
        dn = p.get("driver_number")
        if dn:
            pos_by_driver.setdefault(dn, []).append(p)

    for dn, samples in pos_by_driver.items():
        samples.sort(key=lambda x: x.get("date", ""))
        for i in range(1, len(samples)):
            prev_pos = samples[i-1].get("position", 99)
            curr_pos = samples[i].get("position", 99)
            if isinstance(prev_pos, int) and isinstance(curr_pos, int) and curr_pos < prev_pos:
                gained = prev_pos - curr_pos
                if gained >= 1:
                    acr = dn_to_acr.get(dn, f"#{dn}")
                    lap = samples[i].get("lap_number", "?")
                    ts  = samples[i].get("date", "")
                    events.append({
                        "type":      "OVERTAKE",
                        "lap":       lap,
                        "driver":    acr,
                        "detail":    f"{acr} gains P{gained} — now P{curr_pos}",
                        "timestamp": ts,
                        "color":     "#00e676",
                    })

    # Sort newest first
    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return events[:200]   # cap at 200 events


# ── Factor override ────────────────────────────────────────────────────────────

def apply_live_overrides(
    factors: List[Dict],
    live: Dict,
    total_laps: int,
) -> Tuple[List[Dict], int]:
    """
    Merge live race state into factor dicts for a mid-race MC simulation.

    Returns:
        (updated_factors, remaining_laps)
    """
    current_lap    = live["current_lap"]
    remaining_laps = max(1, total_laps - current_lap)
    gaps           = live["gaps"]
    positions      = live["positions"]
    stints         = live["stints"]
    dnf_numbers    = live["dnf_numbers"]
    sc_active      = live["sc_active"]
    vsc_active     = live["vsc_active"]

    # Build driver_number → factor index map via name matching (best effort)
    # OpenF1 uses driver_number; our factors use driver_id + name
    acronym_map: Dict[str, int] = {}
    for dn, dm in live["driver_map"].items():
        acronym_map[dm["acronym"].upper()] = dn

    updated = []
    for f in factors:
        f2 = dict(f)
        name_parts = f["name"].split()
        surname    = name_parts[-1].upper()[:3]
        # Try to match by acronym or surname prefix
        dn = None
        for acr, num in acronym_map.items():
            if acr == surname or acr[:3] == surname[:3]:
                dn = num
                break

        if dn is not None:
            # ── Replace base_pace with actual race gap ────────────────────────
            gap_s = gaps.get(dn, None)
            if gap_s is not None and gap_s < 500 and current_lap > 2:
                # Convert cumulative gap to per-lap equivalent
                pace_per_lap = gap_s / current_lap
                f2["base_pace"]   = pace_per_lap
                f2["pace_source"] = "live"

            # ── Current position → track affinity proxy ───────────────────────
            cur_pos = positions.get(dn)
            if cur_pos:
                f2["current_position"] = cur_pos

            # ── Tire state ────────────────────────────────────────────────────
            stint = stints.get(dn)
            if stint:
                compound  = stint.get("compound", "MEDIUM").upper()
                lap_start = stint.get("lap_start", current_lap)
                tire_age  = current_lap - lap_start
                f2["tire_age"]           = tire_age
                f2["current_compound"]   = compound
                # Adjust degradation: older tires cost more
                age_penalty = min(tire_age * 0.008, 0.4)   # up to 0.4s/lap extra deg
                f2["temp_penalty"] = f2.get("temp_penalty", 0.0) + age_penalty

            # ── DNF: flag as retired ──────────────────────────────────────────
            if dn in dnf_numbers:
                f2["already_dnf"] = True
                f2["base_pace"]   = 999.0   # will be sorted to last

        # ── Safety car: compress all gaps ─────────────────────────────────────
        if sc_active or vsc_active:
            bp = f2.get("base_pace", 0.0)
            if bp < 900.0:  # don't compress DNF sentinel (999)
                f2["base_pace"] = bp * 0.4  # SC neutralises 60% of gap

        updated.append(f2)

    return updated, remaining_laps
