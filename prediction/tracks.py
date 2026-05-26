"""
Static track database: circuit characteristics, tire compound allocations,
GPS coordinates for weather fetch, and historical safety car rates.

tire_wear    : 1–5 (1=minimal, 5=extreme)
overtaking   : 1–5 (1=nearly impossible, 5=easy)
sc_prob      : historical safety car probability per race
drs_zones    : number of DRS activation zones
compounds    : Pirelli allocation for this race (C1–C5)
lat/lon      : circuit centroid for weather API
"""
from typing import Dict, Any

TRACKS: Dict[str, Dict[str, Any]] = {
    "albert_park": {
        "name": "Albert Park Circuit", "country": "Australia",
        "lat": -37.849, "lon": 144.968,
        "laps": 58, "length_km": 5.278,
        "tire_wear": 3, "overtaking": 3, "sc_prob": 0.45, "drs_zones": 4,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Smooth surface, medium deg. Safety car common lap 1.",
    },
    "bahrain": {
        "name": "Bahrain International Circuit", "country": "Bahrain",
        "lat": 26.032, "lon": 50.511,
        "laps": 57, "length_km": 5.412,
        "tire_wear": 4, "overtaking": 4, "sc_prob": 0.30, "drs_zones": 3,
        "compounds": ["C1", "C2", "C3"],
        "notes": "High abrasion. 3 DRS zones. Good overtaking.",
    },
    "jeddah": {
        "name": "Jeddah Corniche Circuit", "country": "Saudi Arabia",
        "lat": 21.631, "lon": 39.104,
        "laps": 50, "length_km": 6.174,
        "tire_wear": 2, "overtaking": 3, "sc_prob": 0.65, "drs_zones": 3,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Very high SC probability. Low tire wear. Fast circuit.",
    },
    "suzuka": {
        "name": "Suzuka International Racing Course", "country": "Japan",
        "lat": 34.844, "lon": 136.541,
        "laps": 53, "length_km": 5.807,
        "tire_wear": 4, "overtaking": 2, "sc_prob": 0.35, "drs_zones": 2,
        "compounds": ["C1", "C2", "C3"],
        "notes": "Technical layout. Hard to overtake. High-speed corners punish errors.",
    },
    "shanghai": {
        "name": "Shanghai International Circuit", "country": "China",
        "lat": 31.340, "lon": 121.220,
        "laps": 56, "length_km": 5.451,
        "tire_wear": 3, "overtaking": 3, "sc_prob": 0.35, "drs_zones": 2,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Long back straight. Rubber build-up aids late-race overtaking.",
    },
    "miami": {
        "name": "Miami International Autodrome", "country": "USA",
        "lat": 25.958, "lon": -80.239,
        "laps": 57, "length_km": 5.412,
        "tire_wear": 3, "overtaking": 3, "sc_prob": 0.55, "drs_zones": 3,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Street-ish circuit. Heat/humidity elevates tire temps significantly.",
    },
    "imola": {
        "name": "Autodromo Enzo e Dino Ferrari", "country": "Italy",
        "lat": 44.344, "lon": 11.713,
        "laps": 63, "length_km": 4.909,
        "tire_wear": 3, "overtaking": 1, "sc_prob": 0.45, "drs_zones": 1,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Virtually no overtaking. Q position crucial. Track position everything.",
    },
    "monaco": {
        "name": "Circuit de Monaco", "country": "Monaco",
        "lat": 43.737, "lon": 7.427,
        "laps": 78, "length_km": 3.337,
        "tire_wear": 1, "overtaking": 1, "sc_prob": 0.70, "drs_zones": 1,
        "compounds": ["C3", "C4", "C5"],
        "notes": "Pole critical. VSC/SC almost guaranteed. Undercut only viable strategy.",
    },
    "barcelona": {
        "name": "Circuit de Barcelona-Catalunya", "country": "Spain",
        "lat": 41.570, "lon": 2.261,
        "laps": 66, "length_km": 4.657,
        "tire_wear": 4, "overtaking": 2, "sc_prob": 0.30, "drs_zones": 2,
        "compounds": ["C1", "C2", "C3"],
        "notes": "Tire management critical. Overcut viable. Hard to overtake on track.",
    },
    "villeneuve": {
        "name": "Circuit Gilles Villeneuve", "country": "Canada",
        "lat": 45.505, "lon": -73.526,
        "laps": 70, "length_km": 4.361,
        "tire_wear": 2, "overtaking": 4, "sc_prob": 0.55, "drs_zones": 3,
        "compounds": ["C3", "C4", "C5"],
        "notes": "Wall of Champions. SC common. Stop-start layout wears brakes > tires.",
    },
    "red_bull_ring": {
        "name": "Red Bull Ring", "country": "Austria",
        "lat": 47.220, "lon": 14.764,
        "laps": 71, "length_km": 4.318,
        "tire_wear": 3, "overtaking": 4, "sc_prob": 0.40, "drs_zones": 3,
        "compounds": ["C3", "C4", "C5"],
        "notes": "Short lap. Aggressive DRS. Best cars qualify well but passes happen.",
    },
    "silverstone": {
        "name": "Silverstone Circuit", "country": "Great Britain",
        "lat": 52.072, "lon": -1.017,
        "laps": 52, "length_km": 5.891,
        "tire_wear": 5, "overtaking": 3, "sc_prob": 0.35, "drs_zones": 2,
        "compounds": ["C1", "C2", "C3"],
        "notes": "Highest tire wear on calendar. 2-stop strongly preferred — aggressive deg makes a 1-stop very difficult to execute.",
    },
    "hungaroring": {
        "name": "Hungaroring", "country": "Hungary",
        "lat": 47.582, "lon": 19.251,
        "laps": 70, "length_km": 4.381,
        "tire_wear": 3, "overtaking": 1, "sc_prob": 0.35, "drs_zones": 2,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Monaco without the walls. Track position critical. 1-stop typical.",
    },
    "spa": {
        "name": "Circuit de Spa-Francorchamps", "country": "Belgium",
        "lat": 50.437, "lon": 5.971,
        "laps": 44, "length_km": 7.004,
        "tire_wear": 3, "overtaking": 4, "sc_prob": 0.55, "drs_zones": 2,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Weather highly variable. Eau Rouge risk. Long lap = fewer stops.",
    },
    "zandvoort": {
        "name": "Circuit Zandvoort", "country": "Netherlands",
        "lat": 52.388, "lon": 4.541,
        "laps": 72, "length_km": 4.259,
        "tire_wear": 4, "overtaking": 1, "sc_prob": 0.35, "drs_zones": 1,
        "compounds": ["C1", "C2", "C3"],
        "notes": "Banked corners reduce overtaking. Heavy tire deg. 2-stop typical.",
    },
    "monza": {
        "name": "Autodromo Nazionale Monza", "country": "Italy",
        "lat": 45.620, "lon": 9.289,
        "laps": 53, "length_km": 5.793,
        "tire_wear": 2, "overtaking": 4, "sc_prob": 0.45, "drs_zones": 2,
        "compounds": ["C4", "C5", "C6"] if False else ["C3", "C4", "C5"],
        "notes": "Slipstream temple. Low downforce = power units matter most.",
    },
    "baku": {
        "name": "Baku City Circuit", "country": "Azerbaijan",
        "lat": 40.372, "lon": 49.853,
        "laps": 51, "length_km": 6.003,
        "tire_wear": 2, "overtaking": 4, "sc_prob": 0.65, "drs_zones": 2,
        "compounds": ["C3", "C4", "C5"],
        "notes": "SC probability highest outside Monaco. Long straight punishes slow exits.",
    },
    "marina_bay": {
        "name": "Marina Bay Street Circuit", "country": "Singapore",
        "lat": 1.291, "lon": 103.864,
        "laps": 62, "length_km": 4.940,
        "tire_wear": 3, "overtaking": 1, "sc_prob": 0.65, "drs_zones": 3,
        "compounds": ["C3", "C4", "C5"],
        "notes": "Night race, 35°C+ air, 60°C+ track. Highest heat stress on tires.",
    },
    "americas": {
        "name": "Circuit of the Americas", "country": "USA",
        "lat": 30.133, "lon": -97.641,
        "laps": 56, "length_km": 5.513,
        "tire_wear": 4, "overtaking": 3, "sc_prob": 0.40, "drs_zones": 2,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Heavy braking zones. Bumpy surface adds thermal stress.",
    },
    "rodriguez": {
        "name": "Autodromo Hermanos Rodriguez", "country": "Mexico",
        "lat": 19.404, "lon": -99.091,
        "laps": 71, "length_km": 4.304,
        "tire_wear": 3, "overtaking": 3, "sc_prob": 0.30, "drs_zones": 3,
        "compounds": ["C2", "C3", "C4"],
        "notes": "2,285m altitude. Thinner air reduces cooling, elevates tire temps.",
    },
    "interlagos": {
        "name": "Autodromo Jose Carlos Pace", "country": "Brazil",
        "lat": -23.702, "lon": -46.698,
        "laps": 71, "length_km": 4.309,
        "tire_wear": 3, "overtaking": 4, "sc_prob": 0.50, "drs_zones": 2,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Unpredictable weather. SC common. Late-race rain changes everything.",
    },
    "vegas": {
        "name": "Las Vegas Strip Circuit", "country": "USA",
        "lat": 36.112, "lon": -115.174,
        "laps": 50, "length_km": 6.201,
        "tire_wear": 3, "overtaking": 4, "sc_prob": 0.50, "drs_zones": 3,
        "compounds": ["C3", "C4", "C5"],
        "notes": "Cold desert night race. Tire warm-up critical. Long straight lap.",
    },
    "losail": {
        "name": "Lusail International Circuit", "country": "Qatar",
        "lat": 25.490, "lon": 51.454,
        "laps": 57, "length_km": 5.419,
        "tire_wear": 5, "overtaking": 3, "sc_prob": 0.35, "drs_zones": 2,
        "compounds": ["C1", "C2", "C3"],
        "notes": "Highest tire deg on calendar after Silverstone. 2-stop strongly preferred.",
    },
    "yas_marina": {
        "name": "Yas Marina Circuit", "country": "UAE",
        "lat": 24.467, "lon": 54.603,
        "laps": 58, "length_km": 5.281,
        "tire_wear": 3, "overtaking": 3, "sc_prob": 0.30, "drs_zones": 3,
        "compounds": ["C2", "C3", "C4"],
        "notes": "Season finale. Cool evening temps aid tire life. Low SC rate.",
    },
}

# Human-readable compound labels (used by display.py and ui.py)
COMPOUND_LABELS: Dict[str, str] = {
    "C1": "Hard", "C2": "Hard", "C3": "Medium",
    "C4": "Medium", "C5": "Soft", "C6": "Soft",
}

# Pirelli compound performance and thermal characteristics
TIRE_COMPOUNDS = {
    "C1": {"label": "Hard",   "colour": "white",  "optimal_min": 105, "optimal_max": 135,
           "warmup_laps": 5, "peak_laps": 60, "gap_vs_c4": +0.8},
    "C2": {"label": "Hard",   "colour": "white",  "optimal_min": 100, "optimal_max": 125,
           "warmup_laps": 4, "peak_laps": 50, "gap_vs_c4": +0.5},
    "C3": {"label": "Medium", "colour": "yellow", "optimal_min":  90, "optimal_max": 115,
           "warmup_laps": 3, "peak_laps": 35, "gap_vs_c4": +0.2},
    "C4": {"label": "Medium", "colour": "yellow", "optimal_min":  85, "optimal_max": 105,
           "warmup_laps": 2, "peak_laps": 25, "gap_vs_c4":  0.0},
    "C5": {"label": "Soft",   "colour": "red",    "optimal_min":  75, "optimal_max":  98,
           "warmup_laps": 1, "peak_laps": 15, "gap_vs_c4": -0.35},
    "C6": {"label": "Soft",   "colour": "red",    "optimal_min":  70, "optimal_max":  92,
           "warmup_laps": 1, "peak_laps": 10, "gap_vs_c4": -0.5},
}

# Pit stop performance (seconds above/below average 2.5s stop)
PIT_SPEED: Dict[str, float] = {
    "red_bull":    -0.18,
    "mercedes":    -0.08,
    "ferrari":     +0.05,
    "mclaren":     -0.12,
    "aston_martin":+0.15,
    "alpine":      +0.22,
    "williams":    +0.18,
    "rb":          +0.10,
    "sauber":      +0.25,
    "haas":        +0.12,
}


def get_track(circuit_id: str) -> Dict:
    """Fuzzy match a circuit_id to track data."""
    if circuit_id in TRACKS:
        return TRACKS[circuit_id]
    # partial match
    for key, t in TRACKS.items():
        if key in circuit_id or circuit_id in key:
            return t
    # fallback: generic mid-range track
    return {
        "name": circuit_id, "country": "?",
        "lat": 0.0, "lon": 0.0,
        "laps": 60, "length_km": 5.0,
        "tire_wear": 3, "overtaking": 2, "sc_prob": 0.40, "drs_zones": 2,
        "compounds": ["C2", "C3", "C4"],
        "notes": "No specific data. Using defaults.",
    }
