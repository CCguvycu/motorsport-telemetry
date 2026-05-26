"""
F1 Race Predictor — interactive CLI.

Usage:
    python predict.py          # pick from upcoming races
    python predict.py --race 8 # predict round 8 directly
    python predict.py --list   # list upcoming races only
"""
import sys
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

from prediction import api, factors as fac, simulator, display
from prediction.tracks import get_track


def pick_race(upcoming: list) -> dict:
    """Interactive race picker."""
    print("\n╔══ UPCOMING RACES ══╗")
    for i, r in enumerate(upcoming):
        name    = r.get("raceName", "?")
        circuit = r.get("Circuit", {}).get("circuitName", "?")
        country = r.get("Circuit", {}).get("Location", {}).get("country", "?")
        date    = r.get("date", "?")
        print(f"  [{i+1:2d}]  Round {r.get('round','?'):<3}  {date}  "
              f"{name:<35}  {country}")
    print()

    while True:
        try:
            choice = input("  Pick a race [1-{}]: ".format(len(upcoming))).strip()
            idx = int(choice) - 1
            if 0 <= idx < len(upcoming):
                return upcoming[idx]
        except (ValueError, EOFError):
            pass
        print(f"  Enter a number between 1 and {len(upcoming)}.")


def _circuit_id(race: dict) -> str:
    return race.get("Circuit", {}).get("circuitId", "")


def run_prediction(race: dict):
    circuit_id = _circuit_id(race)
    round_num  = race.get("round", "last")
    race_date  = race.get("date", "")

    print(f"\n  Fetching data for {race.get('raceName','?')}...")

    # ── Fetch all data ────────────────────────────────────────────────────
    print("  [1/6] Driver standings...")
    driver_standings = api.get_driver_standings()

    print("  [2/6] Constructor standings...")
    constructor_standings = api.get_constructor_standings()

    print("  [3/6] Season results (form + reliability)...")
    season_results = api.get_season_results()

    print("  [4/6] Qualifying results...")
    qualifying = api.get_qualifying(rnd=round_num)
    if not qualifying:
        # Try previous round as proxy
        prev = str(max(1, int(round_num) - 1)) if round_num.isdigit() else "last"
        qualifying = api.get_qualifying(rnd=prev)
        if qualifying:
            print(f"         (using round {prev} qualifying as pace reference)")

    print("  [5/6] Circuit history (last 5 years)...")
    circuit_history = api.get_circuit_history(circuit_id, seasons=5)

    print("  [6/6] Weather forecast...")
    track = get_track(circuit_id)
    weather = api.get_weather_forecast(track["lat"], track["lon"], race_date)

    print(f"         Air {weather['air_temp']}°C  |  "
          f"Track ~{weather['track_temp']}°C  |  "
          f"Rain {weather['rain_prob']*100:.0f}%  |  "
          f"Wind {weather['wind_kmh']} km/h")

    # ── Bail out if no standings data ─────────────────────────────────────
    if not driver_standings:
        print("\n  [!] Could not fetch driver standings. Check network / API status.")
        return

    # ── Build factor vectors ───────────────────────────────────────────────
    print("\n  Computing factor vectors...")
    driver_factors = fac.build_factors(
        driver_standings=driver_standings,
        constructor_standings=constructor_standings,
        season_results=season_results,
        qualifying_results=qualifying,
        circuit_history=circuit_history,
        circuit_id=circuit_id,
        weather=weather,
        track=track,
    )

    n_factors = len(driver_factors[0]) - 2 if driver_factors else 0
    print(f"  {len(driver_factors)} drivers  |  ~12 factors each")

    # ── Optimal tire strategies ────────────────────────────────────────────
    strategies = fac.compute_optimal_strategy(track, weather)

    # ── Monte Carlo simulation ─────────────────────────────────────────────
    print(f"  Running Monte Carlo ({simulator.N_SIMS:,} simulations)...")
    results = simulator.simulate(driver_factors, track, weather)

    pace_source = results[0]["pace_source"] if results else "championship"

    # ── Display ───────────────────────────────────────────────────────────
    display.show(
        race=race,
        track=track,
        weather=weather,
        results=results,
        strategies=strategies,
        n_sims=simulator.N_SIMS,
        pace_source=pace_source,
    )


def main():
    parser = argparse.ArgumentParser(description="F1 Race Predictor")
    parser.add_argument("--race",  type=str, default=None, help="Round number to predict")
    parser.add_argument("--list",  action="store_true",    help="List upcoming races only")
    args = parser.parse_args()

    print("  Fetching F1 calendar...")
    upcoming = api.get_upcoming_races()

    if not upcoming:
        # Fall back to full schedule if nothing found as "upcoming"
        print("  No upcoming races found — showing full 2025 calendar.")
        upcoming = api.get_schedule()

    if args.list or not upcoming:
        for r in upcoming:
            print(f"  Round {r.get('round','?'):<3}  {r.get('date','?')}  "
                  f"{r.get('raceName','?')}")
        return

    if args.race:
        matches = [r for r in upcoming if str(r.get("round")) == args.race]
        if not matches:
            # try full schedule
            matches = [r for r in api.get_schedule() if str(r.get("round")) == args.race]
        race = matches[0] if matches else upcoming[0]
    else:
        race = pick_race(upcoming)

    run_prediction(race)


if __name__ == "__main__":
    main()
