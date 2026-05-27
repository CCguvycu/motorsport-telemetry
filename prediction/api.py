"""
F1 data fetcher.
  - Jolpica/Ergast  → schedule, standings, results, qualifying
  - OpenF1          → tire stints, real-time weather (recent sessions)
  - Open-Meteo      → race weekend weather forecast (no API key)
"""
import json
import time
import threading
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

JOLPICA    = "https://api.jolpi.ca/ergast/f1"
OPENF1     = "https://api.openf1.org/v1"
OPEN_METEO = "https://api.open-meteo.com/v1"

_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()
CACHE_TTL = 300  # seconds


def _get(url: str, timeout: int = 12) -> Optional[Any]:
    with _cache_lock:
        if url in _cache:
            data, ts = _cache[url]
            if time.time() - ts < CACHE_TTL:
                return data
    try:
        req = Request(url, headers={"User-Agent": "motorsport-telemetry/1.0"})
        with urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        with _cache_lock:
            _cache[url] = (data, time.time())
        return data
    except Exception as e:
        print(f"  [api] {url[:60]}...  -> {e}")
        return None


# ── Ergast / Jolpica ──────────────────────────────────────────────────────

def get_schedule(year: str = "current") -> List[Dict]:
    d = _get(f"{JOLPICA}/{year}.json")
    return (d or {}).get("MRData", {}).get("RaceTable", {}).get("Races", [])


def get_upcoming_races() -> List[Dict]:
    today = date.today()
    out = []
    for r in get_schedule():
        try:
            if datetime.strptime(r["date"], "%Y-%m-%d").date() >= today:
                out.append(r)
        except (KeyError, ValueError):
            pass
    return out


def get_driver_standings(year: str = "current") -> List[Dict]:
    d = _get(f"{JOLPICA}/{year}/driverStandings.json")
    lists = (d or {}).get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
    return lists[0].get("DriverStandings", []) if lists else []


def get_constructor_standings(year: str = "current") -> List[Dict]:
    d = _get(f"{JOLPICA}/{year}/constructorStandings.json")
    lists = (d or {}).get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
    return lists[0].get("ConstructorStandings", []) if lists else []


def get_season_results(year: str = "current") -> List[Dict]:
    d = _get(f"{JOLPICA}/{year}/results.json?limit=500")
    return (d or {}).get("MRData", {}).get("RaceTable", {}).get("Races", [])


def get_qualifying(year: str = "current", rnd: str = "last") -> List[Dict]:
    d = _get(f"{JOLPICA}/{year}/{rnd}/qualifying.json")
    races = (d or {}).get("MRData", {}).get("RaceTable", {}).get("Races", [])
    return races[0].get("QualifyingResults", []) if races else []


def get_season_qualifying(year: str = "current") -> List[Dict]:
    """All qualifying sessions for the season, newest first (all drivers, all rounds)."""
    d = _get(f"{JOLPICA}/{year}/qualifying.json?limit=500")
    races = (d or {}).get("MRData", {}).get("RaceTable", {}).get("Races", [])
    return list(reversed(races))  # most recent first for weighted lookups


def get_circuit_history(circuit_id: str, seasons: int = 5) -> List[Dict]:
    """Last N years of results at this circuit."""
    current_year = date.today().year
    all_results = []
    for y in range(current_year - seasons, current_year):
        d = _get(f"{JOLPICA}/{y}/circuits/{circuit_id}/results.json")
        races = (d or {}).get("MRData", {}).get("RaceTable", {}).get("Races", [])
        all_results.extend(races)
    return all_results


# ── Open-Meteo weather forecast ───────────────────────────────────────────

def get_weather_forecast(lat: float, lon: float, race_date: str) -> Dict:
    url = (
        f"{OPEN_METEO}/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,"
        f"precipitation_probability_max,windspeed_10m_max,weathercode"
        f"&timezone=auto&forecast_days=16"
    )
    d = _get(url)
    if not d:
        return _fallback_weather()

    daily = d.get("daily", {})
    dates = daily.get("time", [])
    try:
        idx = dates.index(race_date)
        t_max  = daily["temperature_2m_max"][idx]
        t_min  = daily["temperature_2m_min"][idx]
        rain   = daily["precipitation_probability_max"][idx] / 100.0
        wind   = daily["windspeed_10m_max"][idx]
        air_t  = (t_max + t_min) / 2
        return {
            "air_temp":     round(air_t, 1),
            "track_temp":   round(air_t * 1.4 + 8, 1),  # empirical: track ~ 1.4×air + 8
            "t_max":        t_max,
            "t_min":        t_min,
            "rain_prob":    round(rain, 2),
            "wind_kmh":     round(wind, 1),
            "source":       "Open-Meteo forecast",
        }
    except (ValueError, KeyError, IndexError):
        return _fallback_weather()


def _fallback_weather() -> Dict:
    return {"air_temp": 22.0, "track_temp": 38.0, "rain_prob": 0.1,
            "wind_kmh": 12.0, "source": "historical average"}


# ── OpenF1 – tire stints from last session at this circuit ───────────────

def get_stint_data(circuit_short: str) -> List[Dict]:
    """Fetch latest available stint data for circuit from OpenF1."""
    # Find last session at this circuit
    sessions = _get(f"{OPENF1}/sessions?circuit_short_name={circuit_short}&session_type=Race")
    if not sessions or not isinstance(sessions, list):
        return []
    sessions.sort(key=lambda s: s.get("date_start", ""), reverse=True)
    if not sessions:
        return []
    sk = sessions[0].get("session_key")
    stints = _get(f"{OPENF1}/stints?session_key={sk}")
    return stints if isinstance(stints, list) else []


def parse_q_time(t: str) -> Optional[float]:
    """'1:23.456' → 83.456 seconds.  Returns None if blank."""
    if not t:
        return None
    try:
        parts = t.split(":")
        return int(parts[0]) * 60 + float(parts[1]) if len(parts) == 2 else float(t)
    except (ValueError, IndexError):
        return None
