"""
Flask web UI for the F1 Race Predictor.

Routes:
  GET  /                    → SPA shell
  GET  /api/races           → upcoming race list
  POST /api/predict         → run full prediction pipeline
  GET  /api/live/session    → detect active race session
  GET  /api/live/state      → current lap, gaps, stints, SC status
  POST /api/live/predict    → MC from current lap using live gaps
  GET  /api/history         → saved prediction runs (SQLite)
  DELETE /api/history/<id>  → delete a saved run
"""
import re
import os
import sys
import json
import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

# Set NTFY_TOPIC env var to use a private topic; defaults to f1-predictor
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "f1-predictor")

# Input validation — allowlist patterns
_ROUND_RE       = re.compile(r'^(last|\d{1,3})$')
_SESSION_KEY_RE = re.compile(r'^(latest|\d{1,8})$')
_YEAR_RE        = re.compile(r'^(current|\d{4})$')


def _ntfy_push(title: str, body: str, tags: str = "racing,checkered_flag", priority: int = 3) -> bool:
    """Fire-and-forget push to ntfy.sh. Returns True on success."""
    try:
        req = Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode(),
            headers={
                "Title":    title,
                "Tags":     tags,
                "Priority": str(priority),
                "Content-Type": "text/plain",
            },
            method="POST",
        )
        with urlopen(req, timeout=8):
            pass
        return True
    except (URLError, Exception) as e:
        print(f"  [ntfy] push failed: {e}")
        return False

from flask import Flask, render_template, request, jsonify, Response
from prediction import api, factors as fac, simulator
from prediction.tracks import get_track
from prediction import live as live_mod

app = Flask(__name__)


@app.after_request
def _security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net unpkg.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: *; "
        "connect-src 'self' https://ntfy.sh; "
        "frame-src https://www.youtube.com https://player.twitch.tv;"
    )
    return response

# ── SQLite history database ───────────────────────────────────────────────────
DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent / "predictions.db")))

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    NOT NULL,
                race_name   TEXT    NOT NULL,
                race_round  TEXT,
                race_date   TEXT,
                circuit     TEXT,
                country     TEXT,
                n_sims      INTEGER,
                pace_source TEXT,
                top5_json   TEXT,   -- JSON array of top-5 result objects
                payload_json TEXT   -- full response payload (compressed subset)
            )
        """)
        conn.commit()

_init_db()

# ── JSON helper: convert numpy scalars → Python native types ─────────────────
def _to_json(obj):
    if isinstance(obj, dict):
        return {k: _to_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json(v) for v in obj]
    if isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, (int, float)):
        return obj
    # numpy scalar → Python int or float via .item()
    try:
        return obj.item()
    except AttributeError:
        pass
    try:
        return float(obj)
    except (TypeError, ValueError):
        return obj


# ── TikTok caption generator ─────────────────────────────────────────────────

def _tiktok_caption(race: dict, results: list, weather: dict, track: dict) -> str:
    """Generate a punchy TikTok post from prediction data."""
    rnd       = race.get("round", "?")
    race_name = race.get("raceName", "Grand Prix")
    top3      = results[:3]
    p1, p2, p3 = top3[0], top3[1], top3[2]
    rain_pct  = int(weather.get("rain_prob", 0) * 100)
    sc_pct    = int(track.get("sc_prob", 0.4) * 100)
    circuit   = track.get("name", "")
    country   = track.get("country", "")

    # Find surprise: high DNF risk in top 10, rain, SC chaos, or midfield threat
    verstappen = next((r for r in results if "verstappen" in r.get("driver_id","").lower()), None)
    vmax_dnf   = verstappen and verstappen.get("dnf_sim_rate", 0) > 0.2
    rain_race  = rain_pct >= 40
    sc_chaos   = sc_pct >= 60
    midfield   = any(r.get("championship_pos", 99) > 8 and r.get("win_prob", 0) > 0.05
                     for r in results[:5])

    # Build controversy hook (max ~10 words)
    if rain_race:
        hook = f"Rain flips the grid at {country}? AI says... 🌧️"
    elif vmax_dnf:
        hook = f"Verstappen DNF risk at {country}? 👀 The data is ruthless"
    elif midfield:
        hook = f"Midfield shock incoming at R{rnd}? 🤖 AI spotted it"
    elif sc_chaos:
        hook = f"Safety car chaos likely at {circuit[:20]} 🚨 Who benefits?"
    elif p1.get("win_prob", 0) > 0.45:
        p1_last = p1["name"].split()[-1]
        hook = f"Is {p1_last} just unbeatable right now? 📊 AI thinks so"
    else:
        p1_last = p1["name"].split()[-1]
        hook = f"Our AI model called R{rnd} — {p1_last} on top 🏆"

    # Body: top 3 + surprise callout
    p1_name = p1["name"]; p2_name = p2["name"]; p3_name = p3["name"]
    body_lines = [
        f"P1 {p1_name} — {p1['win_prob']*100:.0f}% win prob",
        f"P2 {p2_name} — {p2['win_prob']*100:.0f}%",
        f"P3 {p3_name} — {p3['win_prob']*100:.0f}%",
    ]

    # Surprise callout line
    if rain_race:
        body_lines.append(f"\n{rain_pct}% rain. Wet weather specialists rise. Wet race could shuffle everything.")
    elif vmax_dnf and verstappen:
        vpos = next((i+1 for i, r in enumerate(results) if "verstappen" in r.get("driver_id","").lower()), "?")
        body_lines.append(f"\nVerstappen P{vpos} expected — but {int(verstappen['dnf_sim_rate']*100)}% DNF rate. Data doesn't do loyalty.")
    elif sc_chaos:
        body_lines.append(f"\n{sc_pct}% safety car probability. Strategy calls this one, not pace.")
    elif midfield:
        surprise = next(r for r in results[:5] if r.get("championship_pos", 99) > 8)
        body_lines.append(f"\n{surprise['name'].split()[-1]} in the mix? {surprise['win_prob']*100:.0f}% win prob. AI doesn't follow the narrative.")

    # Race hashtag slug
    gp_tag = "#" + race_name.replace(" ", "").replace("-", "")

    hashtags = f"#F1 #FormulaOne {gp_tag} #MachineLearning #DataScience #F1Predictions #BuildInPublic #AI"

    return f"{hook}\n\n" + "\n".join(body_lines) + f"\n\n{hashtags}"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


def _race_payload(r):
    return {
        "round":      r.get("round", "?"),
        "name":       r.get("raceName", "?"),
        "date":       r.get("date", "?"),
        "time":       r.get("time", "13:00:00Z"),
        "circuit":    r.get("Circuit", {}).get("circuitName", "?"),
        "circuitId":  r.get("Circuit", {}).get("circuitId", ""),
        "country":    r.get("Circuit", {}).get("Location", {}).get("country", "?"),
        "lat":        r.get("Circuit", {}).get("Location", {}).get("lat", ""),
        "lon":        r.get("Circuit", {}).get("Location", {}).get("long", ""),
    }

@app.route("/api/races")
def get_races():
    races = api.get_upcoming_races()
    if not races:
        today = datetime.today().date().isoformat()
        races = [r for r in api.get_schedule() if r.get("date", "") >= today]
    return jsonify([_race_payload(r) for r in races])


@app.route("/api/season")
def get_season():
    """Return the full season schedule (all rounds, past and future)."""
    races = api.get_schedule()
    return jsonify([_race_payload(r) for r in races])


@app.route("/api/drivers/stats")
def driver_stats():
    """
    Aggregated season stats per driver:
      championship position, points, wins, podiums, top5, top10,
      DNFs, fastest laps, recent form (last 6 race positions),
      average qualifying gap to pole, teammate head-to-head.
    """
    standings      = api.get_driver_standings()
    season_results = api.get_season_results()
    season_qual    = api.get_season_qualifying()  # newest-first

    # ── Pre-index: race results by driver ─────────────────────────────────────
    # Each entry: {"pos": int, "status": str, "round": str, "raceName": str, "fl_rank": str}
    driver_races: dict = {}
    for race in season_results:
        rnd  = race.get("round", "?")
        name = race.get("raceName", "?")
        for r in race.get("Results", []):
            did = r.get("Driver", {}).get("driverId", "")
            if not did:
                continue
            status = r.get("status", "")
            try:
                pos = int(r.get("position", 20))
            except ValueError:
                pos = 20
            is_dnf = any(x in status for x in
                         ("DNF", "Retired", "Accident", "Engine",
                          "Gearbox", "Hydraulics", "Electrical", "Collision"))
            fl_rank = r.get("FastestLap", {}).get("rank", "")
            driver_races.setdefault(did, []).append({
                "round":    rnd,
                "raceName": name,
                "pos":      pos,
                "status":   status,
                "is_dnf":   is_dnf,
                "fl_rank":  fl_rank,
            })

    # Sort each driver's races by round ascending (oldest first)
    for did in driver_races:
        driver_races[did].sort(key=lambda x: int(x["round"]) if x["round"].isdigit() else 0)

    # ── Pre-index: qualifying data by driver ──────────────────────────────────
    # Compute avg gap-to-pole across all qualifying sessions
    driver_quali_gaps: dict = {}  # did → [gap_s, ...]
    for race in season_qual:  # newest-first
        qr = race.get("QualifyingResults", [])
        if not qr:
            continue
        pole_t = None
        for q in qr:
            t = q.get("Q3") or q.get("Q2") or q.get("Q1", "")
            s = api.parse_q_time(t)
            if s is not None and (pole_t is None or s < pole_t):
                pole_t = s
        if pole_t is None:
            continue
        for q in qr:
            did = q.get("Driver", {}).get("driverId", "")
            t   = q.get("Q3") or q.get("Q2") or q.get("Q1", "")
            s   = api.parse_q_time(t)
            if did and s is not None:
                driver_quali_gaps.setdefault(did, []).append(round(s - pole_t, 3))

    # ── Teammate head-to-head quali: count sessions each beat the other ───────
    # Build constructor → [driver_ids] map from standings
    con_drivers: dict = {}
    for s in standings:
        con = s.get("Constructors", [{}])[0].get("constructorId", "unknown")
        did = s.get("Driver", {}).get("driverId", "")
        con_drivers.setdefault(con, []).append(did)

    # For each qualifying session, compare teammates
    teammate_wins: dict = {}  # did → int (sessions beating teammate)
    teammate_total: dict = {}
    for race in season_qual:
        qr = race.get("QualifyingResults", [])
        # Build: did → best time in seconds
        session_times: dict = {}
        for q in qr:
            did = q.get("Driver", {}).get("driverId", "")
            t   = q.get("Q3") or q.get("Q2") or q.get("Q1", "")
            s   = api.parse_q_time(t)
            if did and s is not None:
                session_times[did] = s
        # Compare within each constructor
        for con, dids in con_drivers.items():
            if len(dids) < 2:
                continue
            d1, d2 = dids[0], dids[1]
            t1, t2 = session_times.get(d1), session_times.get(d2)
            if t1 is not None and t2 is not None:
                teammate_total[d1] = teammate_total.get(d1, 0) + 1
                teammate_total[d2] = teammate_total.get(d2, 0) + 1
                if t1 < t2:
                    teammate_wins[d1] = teammate_wins.get(d1, 0) + 1
                else:
                    teammate_wins[d2] = teammate_wins.get(d2, 0) + 1

    # ── Assemble result per driver ─────────────────────────────────────────────
    result = []
    for s in standings:
        d   = s.get("Driver", {})
        did = d.get("driverId", "")
        con = s.get("Constructors", [{}])[0].get("constructorId", "unknown")

        races = driver_races.get(did, [])
        wins     = int(s.get("wins", 0))
        podiums  = sum(1 for r in races if not r["is_dnf"] and r["pos"] <= 3)
        top5     = sum(1 for r in races if not r["is_dnf"] and r["pos"] <= 5)
        top10    = sum(1 for r in races if not r["is_dnf"] and r["pos"] <= 10)
        dnfs     = sum(1 for r in races if r["is_dnf"])
        fl_count = sum(1 for r in races if str(r.get("fl_rank")) == "1")
        races_started = len(races)

        # Recent form: last 6 race positions
        recent = [{"pos": r["pos"], "is_dnf": r["is_dnf"],
                   "round": r["round"], "raceName": r["raceName"]}
                  for r in races[-6:]]

        # Avg qualifying gap to pole
        gaps = driver_quali_gaps.get(did, [])
        avg_gap = round(sum(gaps) / len(gaps), 3) if gaps else None

        # Teammate H2H
        tm_wins  = teammate_wins.get(did, 0)
        tm_total = teammate_total.get(did, 0)

        result.append({
            "driver_id":       did,
            "name":            f"{d.get('givenName','')} {d.get('familyName','')}".strip(),
            "code":            d.get("code", did[:3].upper()),
            "number":          d.get("permanentNumber", ""),
            "nationality":     d.get("nationality", ""),
            "constructor_id":  con,
            "championship_pos": int(s.get("position", 99)),
            "championship_pts": float(s.get("points", 0)),
            "wins":            wins,
            "podiums":         podiums,
            "top5":            top5,
            "top10":           top10,
            "dnfs":            dnfs,
            "fastest_laps":    fl_count,
            "races_started":   races_started,
            "avg_quali_gap":   avg_gap,
            "recent_form":     recent,
            "teammate_h2h":    {"wins": tm_wins, "total": tm_total},
            "race_history":    races,  # full list for expanded view
        })

    result.sort(key=lambda x: x["championship_pos"])
    return jsonify(result)


@app.route("/api/predict", methods=["POST"])
def predict():
    data = request.get_json(force=True, silent=True) or {}
    round_num = str(data.get("round", "last"))
    if not _ROUND_RE.match(round_num):
        return jsonify({"error": "Invalid round parameter"}), 400

    # Locate race object
    upcoming = api.get_upcoming_races() or api.get_schedule()
    race = next((r for r in upcoming if str(r.get("round")) == round_num), None)
    if race is None:
        full = api.get_schedule()
        race = next((r for r in full if str(r.get("round")) == round_num), full[0] if full else {})

    circuit_id = race.get("Circuit", {}).get("circuitId", "")
    race_date  = race.get("date", "")

    # Fetch
    driver_standings      = api.get_driver_standings()
    constructor_standings = api.get_constructor_standings()
    season_results        = api.get_season_results()
    season_qualifying     = api.get_season_qualifying()

    qualifying = api.get_qualifying(rnd=round_num)
    if not qualifying:
        prev = str(max(1, int(round_num) - 1)) if round_num.isdigit() else "last"
        qualifying = api.get_qualifying(rnd=prev)

    circuit_history = api.get_circuit_history(circuit_id, seasons=5)
    track   = get_track(circuit_id)
    weather = api.get_weather_forecast(track["lat"], track["lon"], race_date)

    if not driver_standings:
        return jsonify({"error": "Could not fetch driver standings"}), 503

    driver_factors = fac.build_factors(
        driver_standings=driver_standings,
        constructor_standings=constructor_standings,
        season_results=season_results,
        qualifying_results=qualifying,
        circuit_history=circuit_history,
        circuit_id=circuit_id,
        weather=weather,
        track=track,
        season_qualifying=season_qualifying,
    )

    strategies = fac.compute_optimal_strategy(track, weather)
    results    = simulator.simulate(driver_factors, track, weather)

    pace_source = results[0]["pace_source"] if results else "championship"

    # Tire temperature analysis (mirrors display.py logic)
    from prediction.tracks import TIRE_COMPOUNDS, COMPOUND_LABELS
    trk_t   = weather.get("track_temp", 40.0)
    air_t   = weather.get("air_temp", 22.0)
    tire_op = round(trk_t * 1.8 + air_t * 0.4 + 18, 1)
    compounds = track.get("compounds", [])

    tire_analysis = []
    for c in compounds:
        tc    = TIRE_COMPOUNDS.get(c, {})
        t_min = tc.get("optimal_min", 90)
        t_max = tc.get("optimal_max", 110)
        if tire_op < t_min:
            status = "COLD"
            margin = t_min - tire_op
        elif tire_op > t_max:
            status = "HOT"
            margin = tire_op - t_max
        else:
            status = "OPTIMAL"
            margin = min(tire_op - t_min, t_max - tire_op)
        tire_analysis.append({
            "compound":     c,
            "label":        COMPOUND_LABELS.get(c, "?"),
            "window":       f"{t_min}–{t_max}°C",
            "status":       status,
            "margin":       round(float(margin), 1),
            "warmup_laps":  tc.get("warmup_laps", 3),
            "peak_laps":    tc.get("peak_laps", 25),
            "gap_vs_c4":    tc.get("gap_vs_c4", 0.0),
        })

    payload = {
        "race":         {"name": race.get("raceName", "?"), "round": race.get("round", "?"), "date": race_date},
        "track":        _to_json(track),
        "weather":      _to_json(weather),
        "tire_op_temp": tire_op,
        "tire_analysis": tire_analysis,
        "results":      _to_json(results[:20]),
        "strategies":   _to_json(strategies),
        "n_sims":       simulator.N_SIMS,
        "pace_source":  pace_source,
    }

    # ── Persist to history DB ─────────────────────────────────────────────────
    try:
        top5 = _to_json(results[:5])
        with _db() as conn:
            conn.execute("""
                INSERT INTO predictions
                    (created_at, race_name, race_round, race_date, circuit, country,
                     n_sims, pace_source, top5_json, payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                datetime.utcnow().isoformat(timespec="seconds"),
                race.get("raceName", "?"),
                str(race.get("round", "?")),
                race_date,
                track.get("name", "?"),
                track.get("country", "?"),
                simulator.N_SIMS,
                pace_source,
                json.dumps(top5),
                json.dumps({
                    "track":        _to_json(track),
                    "weather":      _to_json(weather),
                    "tire_op_temp": tire_op,
                    "tire_analysis": tire_analysis,
                    "strategies":   _to_json(strategies),
                    "results":      _to_json(results[:20]),
                }),
            ))
            conn.commit()
    except Exception:
        pass  # never block the response for a logging failure

    # ── ntfy push (background, never blocks response) ────────────────────────
    def _push():
        top3 = results[:3]
        lines = [f"P{i+1} {r['name']} ({r['constructor_id']}) {r['win_prob']*100:.0f}%"
                 for i, r in enumerate(top3)]
        w = weather
        body = "\n".join(lines) + (
            f"\n\n🌡 {w.get('air_temp')}°C  "
            f"🌧 {int(w.get('rain_prob', 0)*100)}% rain  "
            f"💨 {w.get('wind_kmh')} km/h"
        )
        title = f"R{race.get('round')} {race.get('raceName','?')} · Prediction"
        _ntfy_push(title, body)
        # Second push — TikTok caption ready to copy
        caption = _tiktok_caption(race, results, weather, track)
        _ntfy_push(
            f"R{race.get('round')} TikTok Caption 📱",
            caption,
            tags="pencil,checkered_flag",
        )
    threading.Thread(target=_push, daemon=True).start()

    return jsonify(payload)


# ── ntfy standalone endpoint ──────────────────────────────────────────────────

@app.route("/api/notify", methods=["POST"])
def notify():
    """Push a pre-computed prediction summary to ntfy. Body: {"round": "6"}"""
    data = request.get_json(force=True, silent=True) or {}
    try:
        run_id = int(data.get("run_id", 0)) or None
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid run_id"}), 400
    if run_id:
        # Push from saved history
        with _db() as conn:
            row = conn.execute("SELECT * FROM predictions WHERE id=?", (run_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "run not found"}), 404
        top5 = json.loads(row["top5_json"] or "[]")
        lines = [f"P{i+1} {r['name']} ({r['constructor_id']}) {r['win_prob']*100:.0f}%"
                 for i, r in enumerate(top5[:3])]
        title = f"R{row['race_round']} {row['race_name']} · Saved Prediction"
        body  = "\n".join(lines)
    else:
        return jsonify({"ok": False, "error": "provide run_id"}), 400

    ok = _ntfy_push(title, body)
    return jsonify({"ok": ok})


# ── Live race endpoints ───────────────────────────────────────────────────────

@app.route("/api/live/session")
def live_session():
    """Detect if a race session is currently active via OpenF1."""
    session = live_mod.get_active_session()
    if not session:
        return jsonify({"active": False, "session": None})
    is_live = live_mod.is_session_live(session)
    return jsonify({
        "active":       is_live,
        "session_key":  session.get("session_key"),
        "session_name": session.get("session_name"),
        "circuit":      session.get("circuit_short_name"),
        "country":      session.get("country_name"),
        "date_start":   session.get("date_start"),
    })


@app.route("/api/live/state")
def live_state():
    """Return current race state: positions, gaps, tire stints, SC, weather."""
    session_key = request.args.get("session_key", "latest")
    if not _SESSION_KEY_RE.match(session_key):
        return jsonify({"error": "Invalid session_key"}), 400
    state = live_mod.get_live_state(session_key)
    # Serialise sets to lists for JSON
    state["dnf_numbers"] = list(state.get("dnf_numbers", []))
    return jsonify(_to_json(state))


@app.route("/api/live/predict", methods=["POST"])
def live_predict():
    """
    Re-run Monte Carlo from the current lap using live gaps as base_pace.
    Body: {"round": "8", "session_key": "9158"}
    """
    data        = request.get_json(force=True, silent=True) or {}
    round_num   = str(data.get("round", "last"))
    session_key = str(data.get("session_key", "latest"))
    if not _ROUND_RE.match(round_num):
        return jsonify({"error": "Invalid round parameter"}), 400
    if not _SESSION_KEY_RE.match(session_key):
        return jsonify({"error": "Invalid session_key"}), 400

    # Load base prediction factors (same as /api/predict)
    upcoming = api.get_upcoming_races() or api.get_schedule()
    race = next((r for r in upcoming if str(r.get("round")) == round_num), None)
    if race is None:
        full = api.get_schedule()
        race = next((r for r in full if str(r.get("round")) == round_num), full[0] if full else {})

    circuit_id = race.get("Circuit", {}).get("circuitId", "")
    race_date  = race.get("date", "")

    driver_standings      = api.get_driver_standings()
    constructor_standings = api.get_constructor_standings()
    season_results        = api.get_season_results()
    season_qualifying     = api.get_season_qualifying()
    qualifying            = api.get_qualifying(rnd=round_num)
    circuit_history       = api.get_circuit_history(circuit_id, seasons=5)
    track                 = get_track(circuit_id)
    weather               = api.get_weather_forecast(track["lat"], track["lon"], race_date)

    if not driver_standings:
        return jsonify({"error": "Could not fetch driver standings"}), 503

    driver_factors = fac.build_factors(
        driver_standings=driver_standings,
        constructor_standings=constructor_standings,
        season_results=season_results,
        qualifying_results=qualifying,
        circuit_history=circuit_history,
        circuit_id=circuit_id,
        weather=weather,
        track=track,
        season_qualifying=season_qualifying,
    )

    # ── Apply live overrides ──────────────────────────────────────────────────
    live_state_data = live_mod.get_live_state(session_key)

    # Use live weather if available
    if live_state_data.get("weather"):
        weather = {**weather, **live_state_data["weather"]}

    live_factors, remaining_laps = live_mod.apply_live_overrides(
        driver_factors, live_state_data, total_laps=track.get("laps", 60)
    )

    # Simulate over remaining laps only
    live_track = {**track, "laps": remaining_laps}
    results    = simulator.simulate(live_factors, live_track, weather)

    # Build annotated driver rows with live position/gap/tire
    live_positions = live_state_data.get("positions", {})
    live_gaps      = live_state_data.get("gaps", {})
    live_stints    = live_state_data.get("stints", {})
    driver_map     = live_state_data.get("driver_map", {})

    # Annotate each result with live data (matched by name)
    acronym_to_dn = {v["acronym"].upper(): k for k, v in driver_map.items()}
    for r in results:
        surname = r["name"].split()[-1].upper()[:3]
        dn = None
        for acr, num in acronym_to_dn.items():
            if acr[:3] == surname[:3]:
                dn = num
                break
        if dn:
            r["live_pos"]   = live_positions.get(dn)
            r["live_gap"]   = live_gaps.get(dn)
            r["live_tire"]  = live_stints.get(dn, {}).get("compound", "?")
            r["live_tire_age"] = live_state_data["current_lap"] - live_stints.get(dn, {}).get("lap_start", live_state_data["current_lap"])

    from prediction.tracks import TIRE_COMPOUNDS, COMPOUND_LABELS
    trk_t   = weather.get("track_temp", 40.0)
    air_t   = weather.get("air_temp", 22.0)
    tire_op = round(trk_t * 1.8 + air_t * 0.4 + 18, 1)
    compounds = track.get("compounds", [])
    tire_analysis = []
    for c in compounds:
        tc    = TIRE_COMPOUNDS.get(c, {})
        t_min = tc.get("optimal_min", 90)
        t_max = tc.get("optimal_max", 110)
        status = "OPTIMAL" if t_min <= tire_op <= t_max else ("COLD" if tire_op < t_min else "HOT")
        margin = round(float(min(abs(tire_op - t_min), abs(tire_op - t_max))), 1)
        tire_analysis.append({"compound": c, "label": COMPOUND_LABELS.get(c,"?"),
                               "window": f"{t_min}-{t_max}°C", "status": status, "margin": margin,
                               "warmup_laps": tc.get("warmup_laps",3),
                               "peak_laps": tc.get("peak_laps",25),
                               "gap_vs_c4": tc.get("gap_vs_c4",0.0)})

    payload = {
        "race":           {"name": race.get("raceName","?"), "round": race.get("round","?"), "date": race_date},
        "track":          _to_json(track),
        "weather":        _to_json(weather),
        "tire_op_temp":   tire_op,
        "tire_analysis":  tire_analysis,
        "results":        _to_json(results[:20]),
        "strategies":     _to_json(fac.compute_optimal_strategy(live_track, weather)),
        "n_sims":         simulator.N_SIMS,
        "pace_source":    "live",
        "current_lap":    live_state_data["current_lap"],
        "remaining_laps": remaining_laps,
        "sc_active":      live_state_data["sc_active"],
        "vsc_active":     live_state_data["vsc_active"],
        "red_flag":       live_state_data["red_flag"],
    }
    return jsonify(payload)


@app.route("/api/live/feed")
def live_feed():
    """Return chronological race event feed from OpenF1 race_control + pit + position."""
    session_key = request.args.get("session_key", "latest")
    if not _SESSION_KEY_RE.match(session_key):
        return jsonify({"error": "Invalid session_key"}), 400
    events = live_mod.get_race_feed(session_key)
    return jsonify(events)


# ── History endpoints ─────────────────────────────────────────────────────────

@app.route("/api/history")
def get_history():
    """Return all saved prediction runs, newest first."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT id, created_at, race_name, race_round, race_date,
                   circuit, country, n_sims, pace_source, top5_json
            FROM predictions
            ORDER BY id DESC
            LIMIT 100
        """).fetchall()
    result = []
    for r in rows:
        top5 = json.loads(r["top5_json"]) if r["top5_json"] else []
        result.append({
            "id":          r["id"],
            "created_at":  r["created_at"],
            "race_name":   r["race_name"],
            "race_round":  r["race_round"],
            "race_date":   r["race_date"],
            "circuit":     r["circuit"],
            "country":     r["country"],
            "n_sims":      r["n_sims"],
            "pace_source": r["pace_source"],
            "top5":        top5,
        })
    return jsonify(result)


@app.route("/api/history/<int:run_id>")
def get_history_run(run_id):
    """Return full payload for a single saved run (for replay)."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM predictions WHERE id=?", (run_id,)
        ).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
    payload["race"] = {
        "name":  row["race_name"],
        "round": row["race_round"],
        "date":  row["race_date"],
    }
    payload["n_sims"]      = row["n_sims"]
    payload["pace_source"] = row["pace_source"]
    return jsonify(payload)


@app.route("/api/history/<int:run_id>", methods=["DELETE"])
def delete_history_run(run_id):
    """Delete a saved prediction run."""
    with _db() as conn:
        cur = conn.execute("DELETE FROM predictions WHERE id=?", (run_id,))
        conn.commit()
    if cur.rowcount == 0:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/laptimes")
def lap_times():
    """Qualifying + fastest lap data for a given round, plus season poles."""
    round_num = str(request.args.get("round", "last"))
    year      = str(request.args.get("year",  "current"))
    if not _ROUND_RE.match(round_num):
        return jsonify({"error": "Invalid round parameter"}), 400
    if not _YEAR_RE.match(year):
        return jsonify({"error": "Invalid year parameter"}), 400

    JOLP = api.JOLPICA

    # Qualifying results for this round
    d_qual  = api._get(f"{JOLP}/{year}/{round_num}/qualifying.json")
    races_q = (d_qual or {}).get("MRData", {}).get("RaceTable", {}).get("Races", [])
    qual_r  = races_q[0].get("QualifyingResults", []) if races_q else []
    race_info = {}
    if races_q:
        r0 = races_q[0]
        race_info = {
            "raceName":  r0.get("raceName"),
            "round":     r0.get("round"),
            "date":      r0.get("date"),
            "circuitId": r0.get("Circuit", {}).get("circuitId"),
            "circuit":   r0.get("Circuit", {}).get("circuitName"),
            "country":   r0.get("Circuit", {}).get("Location", {}).get("country"),
        }

    # Race results for fastest laps
    d_race  = api._get(f"{JOLP}/{year}/{round_num}/results.json")
    races_r = (d_race or {}).get("MRData", {}).get("RaceTable", {}).get("Races", [])
    race_r  = races_r[0].get("Results", []) if races_r else []

    # All qualifying results for season poles timeline
    d_sq   = api._get(f"{JOLP}/{year}/qualifying.json?limit=500")
    all_q  = (d_sq or {}).get("MRData", {}).get("RaceTable", {}).get("Races", [])

    def _fmt_qual(row):
        q1 = row.get("Q1", "")
        q2 = row.get("Q2", "")
        q3 = row.get("Q3", "")
        best = q3 or q2 or q1
        return {
            "position":  row.get("position"),
            "driver":    row.get("Driver", {}).get("code", ""),
            "driver_id": row.get("Driver", {}).get("driverId", ""),
            "name":      (row.get("Driver", {}).get("givenName", "") + " " +
                          row.get("Driver", {}).get("familyName", "")).strip(),
            "team":      row.get("Constructor", {}).get("constructorId", ""),
            "team_name": row.get("Constructor", {}).get("name", ""),
            "Q1": q1, "Q2": q2, "Q3": q3,
            "best": best,
            "best_s": api.parse_q_time(best),
            "Q1_s":   api.parse_q_time(q1),
            "Q2_s":   api.parse_q_time(q2),
            "Q3_s":   api.parse_q_time(q3),
        }

    qualifying = [_fmt_qual(r) for r in qual_r]

    fastest_laps = []
    for r in race_r:
        fl = r.get("FastestLap", {})
        t  = fl.get("Time", {}).get("time", "")
        fastest_laps.append({
            "race_pos":  r.get("position"),
            "driver":    r.get("Driver", {}).get("code", ""),
            "driver_id": r.get("Driver", {}).get("driverId", ""),
            "name":      (r.get("Driver", {}).get("givenName", "") + " " +
                          r.get("Driver", {}).get("familyName", "")).strip(),
            "team":      r.get("Constructor", {}).get("constructorId", ""),
            "fl_rank":   fl.get("rank", ""),
            "fl_lap":    fl.get("lap", ""),
            "fl_time":   t,
            "fl_time_s": api.parse_q_time(t),
            "fl_speed":  fl.get("AverageSpeed", {}).get("speed", ""),
        })
    fastest_laps.sort(key=lambda x: x["fl_time_s"] or 999)

    season_poles = []
    for r in all_q:
        qr = r.get("QualifyingResults", [])
        if not qr:
            continue
        pole = qr[0]
        q3   = pole.get("Q3") or pole.get("Q2") or pole.get("Q1", "")
        season_poles.append({
            "round":     r.get("round"),
            "raceName":  r.get("raceName"),
            "date":      r.get("date"),
            "circuitId": r.get("Circuit", {}).get("circuitId"),
            "driver":    pole.get("Driver", {}).get("code", ""),
            "driver_id": pole.get("Driver", {}).get("driverId", ""),
            "name":      (pole.get("Driver", {}).get("givenName", "") + " " +
                          pole.get("Driver", {}).get("familyName", "")).strip(),
            "team":      pole.get("Constructor", {}).get("constructorId", ""),
            "time":      q3,
            "time_s":    api.parse_q_time(q3),
        })
    season_poles.sort(key=lambda x: int(x["round"] or 999))

    return jsonify({
        "race":         race_info,
        "qualifying":   qualifying,
        "fastest_laps": fastest_laps,
        "season_poles": season_poles,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    host = "0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1"
    print(f"  F1 Predictor UI → http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
