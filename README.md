# F1 Race Predictor — 2026

A local Monte Carlo race simulation engine for the 2026 Formula 1 season. Runs a Flask web app with four interactive tabs: race predictions, prediction history, circuit explorer, and win-probability breakdown.

No API keys required. All data sources are free and open.

---

## Features

| Tab | What it does |
|-----|-------------|
| **PREDICTOR** | Run a 5,000-iteration Monte Carlo simulation for any 2026 race. Shows predicted finish order, win/podium probabilities, optimal tire strategies, and scenario analysis. |
| **DATABASE** | Full prediction history stored in SQLite. Sortable, searchable, with per-run replay. |
| **TRACKS** | Interactive Leaflet world map + cards for all 22 circuits. Tire wear, overtaking rating, SC probability, DRS zones, compound allocation. |
| **CHANCE** | Visual win-probability dashboard — conic-gradient donut rings for the top 3, animated bar chart for all 20 drivers, team-coloured. |

**Additional:**
- Live session detection via OpenF1 — upgrades predictions with real gap data mid-race
- Phone push notifications via [ntfy.sh](https://ntfy.sh) (free, no account needed) — fires automatically on every prediction
- TikTok caption auto-generation from prediction data, pushed alongside results
- Weather forecast from Open-Meteo (no API key, 16-day forecast)
- Tire temperature window analysis per compound
- Export prediction as PNG

---

## Data Sources

| Source | Used for | API key? |
|--------|----------|----------|
| [Jolpica / Ergast](https://jolpi.ca) | Driver standings, constructor standings, season results, qualifying, circuit history | No |
| [OpenF1](https://openf1.org) | Live session detection, tire stints, real-time gaps | No |
| [Open-Meteo](https://open-meteo.com) | Race weekend weather forecast | No |

All responses cached in-memory for 5 minutes (thread-safe).

---

## Installation

**Python 3.10+** required.

```bash
git clone https://github.com/CCguvycu/motorsport-telemetry.git
cd motorsport-telemetry
pip install flask numpy matplotlib scipy
```

---

## Running

```bash
python ui.py
```

Opens on `http://127.0.0.1:5050`

---

## Phone Alerts (ntfy)

1. Download the ntfy app — [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) · [iPhone](https://apps.apple.com/app/ntfy/id1625396347)
2. In the app tap **+** and subscribe to a topic name (e.g. `f1-alerts-cameron`)
3. Set the same topic in the PHONE ALERTS panel inside the app, or via environment variable:

```bash
NTFY_TOPIC=f1-alerts-cameron python ui.py
```

Every prediction fires two notifications automatically: a results summary and a TikTok-ready caption.

---

## How the Simulation Works

Each prediction pulls live season data and builds a factor vector per driver:

```
factor = form × wet_skill × tire_mgmt × reliability × drs_efficiency × defense
```

Factors are weighted against qualifying pace (when available), championship pace, or live gap data. The Monte Carlo loop runs 5,000 race simulations, sampling random events — safety cars, DNFs, weather shifts — to produce finish-position distributions.

**Track data** covers all 22 circuits with:
- Tire wear rating (1–5), overtaking difficulty (1–5)
- Historical safety car probability
- Pirelli compound allocation (C1–C6)
- Pit stop performance delta per team
- GPS coordinates for weather fetch

---

## Project Structure

```
motorsport-telemetry/
├── ui.py                   # Flask app — all routes, ntfy, SQLite history
├── prediction/
│   ├── api.py              # Data fetchers (Jolpica, OpenF1, Open-Meteo)
│   ├── factors.py          # Driver factor builder + strategy engine
│   ├── simulator.py        # Monte Carlo simulation core
│   ├── tracks.py           # Circuit database (22 tracks, tire compounds)
│   └── live.py             # Live session detection + gap ingestion
├── templates/
│   └── index.html          # Single-page app (~3,700 lines)
├── tests/                  # pytest suite
└── data/sample/            # Sample telemetry CSV for local testing
```

---

## Security

- Bound to `127.0.0.1` only — not exposed to the network
- CSP, X-Frame-Options, X-Content-Type-Options headers on every response
- Input validation on all API parameters (allowlist regex)
- XSS-safe HTML rendering via `textContent` / `createElement` throughout
- `predictions.db` excluded from version control

---

## 2026 Calendar

| Rd | Race | Circuit |
|----|------|---------|
| 1 | Australia | Albert Park |
| 2 | China | Shanghai |
| 3 | Japan | Suzuka |
| 4 | Miami | Miami International Autodrome |
| 5 | Canada | Circuit Gilles Villeneuve |
| 6 | Monaco | Circuit de Monaco |
| 7 | Spain | Circuit de Barcelona-Catalunya |
| 8 | Austria | Red Bull Ring |
| 9 | Great Britain | Silverstone |
| 10 | Belgium | Spa-Francorchamps |
| 11 | Hungary | Hungaroring |
| 12 | Netherlands | Zandvoort |
| 13 | Italy | Monza |
| 14 | Spain (Madrid) | TBC |
| 15 | Azerbaijan | Baku City Circuit |
| 16 | Singapore | Marina Bay |
| 17 | USA | Circuit of the Americas |
| 18 | Mexico | Hermanos Rodríguez |
| 19 | Brazil | Interlagos |
| 20 | Las Vegas | Las Vegas Strip Circuit |
| 21 | Qatar | Lusail |
| 22 | Abu Dhabi | Yas Marina |
