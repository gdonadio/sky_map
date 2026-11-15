"""Sky map for the Inkplate 10: the sky at sunrise or sunset, sun/moon times, and the forecast.

Before noon (local) it draws today's sunrise; from noon on, today's sunset.
Set SKY_MAP_MODE=sunrise or SKY_MAP_MODE=sunset to force one.
"""
import json
import os
import re
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import numpy as np
import plotly.graph_objects as go
from skyfield import almanac
from skyfield.api import Loader, wgs84

# ---- Settings ----
MODE = os.environ.get("SKY_MAP_MODE", "auto")   # "auto", "sunrise", or "sunset"
LATITUDE, LONGITUDE = 42.3736, -71.1097
TZ = ZoneInfo("America/New_York")
WIDTH, HEIGHT = 1200, 825          # Inkplate 10 screen
USER_AGENT = "sky_map (github.com/gdonadio/sky_map)"   # NWS asks for a User-Agent

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

load = Loader(str(ROOT_DIR))
eph = load("de440s.bsp")
ts = load.timescale()
earth = eph["earth"]
place = wgs84.latlon(LATITUDE, LONGITUDE)
observer = earth + place

now_local = datetime.now(TZ)
print("Run time:", now_local.strftime("%a %b %d, %I:%M %p %Z"))

# --- Pick the moment to draw: today's sunrise (morning run) or sunset (afternoon run) ---
def fmt_time(t):
    """Skyfield Time -> '6:31 AM' in local time."""
    return t.astimezone(TZ).strftime("%I:%M %p").lstrip("0")

def fmt_day_time(t, ref_date):
    """Adds the weekday when the event isn't on ref_date, e.g. 'Sun 6:32 AM'."""
    local = t.astimezone(TZ)
    label = fmt_time(t)
    return label if local.date() == ref_date else f"{local:%a} {label}"

mode = MODE
if mode == "auto":
    mode = "sunrise" if now_local.hour < 12 else "sunset"

day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
t0, t1 = ts.from_datetime(day_start), ts.from_datetime(day_start + timedelta(days=1))
sun = eph["sun"]
finder = almanac.find_risings if mode == "sunrise" else almanac.find_settings
event_times, _ = finder(observer, sun, t0, t1)
map_time = event_times[0]

print(f"Mode: {mode}. Drawing the sky at {fmt_time(map_time)}")

# --- Sun and moon times: next rise / meridian / set after the map moment, each searched 30 h ahead ---
def next_event(func, body, start, hours=30):
    result = func(observer, body, start, start + timedelta(hours=hours))
    t = result[0] if isinstance(result, tuple) else result   # find_transits returns times only
    return t[0] if len(t) else None

def body_times(body, start):
    return {
        "Rise": next_event(almanac.find_risings, body, start),
        "Meridian": next_event(almanac.find_transits, body, start),
        "Set": next_event(almanac.find_settings, body, start),
    }

start = map_time - timedelta(minutes=1)   # so the map's own event counts
ref_date = map_time.astimezone(TZ).date()
almanac_rows = {"Sun": body_times(sun, start), "Moon": body_times(eph["moon"], start)}

# Moon phase: illuminated fraction, plus waxing (phase < 180 deg) or waning
moon_illum = almanac.fraction_illuminated(eph, "moon", map_time) * 100
moon_waxing = almanac.moon_phase(eph, map_time).degrees < 180
moon_label = f"Moon {moon_illum:.0f}%<br>{'waxing' if moon_waxing else 'waning'}"

for name, times in almanac_rows.items():
    print(name, {k: (fmt_day_time(v, ref_date) if v is not None else "-") for k, v in times.items()})
print(moon_label.replace('<br>', ' '))

# --- Weather: numbers from Open-Meteo, condition words from the NWS hourly forecast ---
def fetch_json(url, headers=None):
    req = Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urlopen(req, timeout=15) as resp:
        return json.load(resp)

def local_hour(day, hour):
    """Local datetime for `hour` o'clock, counting from midnight of `day` (hour may be >= 24)."""
    return datetime.combine(day, datetime.min.time(), TZ) + timedelta(hours=hour)

today = now_local.date()
if mode == "sunrise":
    table_start, table_end = local_hour(today, 6), local_hour(today, 21)        # 6 AM-9 PM
    segments = [("This morning", local_hour(today, 6), local_hour(today, 12)),
                ("This afternoon", local_hour(today, 12), local_hour(today, 18))]
else:
    table_start, table_end = local_hour(today, 17), local_hour(today, 24 + 8)   # 5 PM-8 AM
    segments = [("This evening", local_hour(today, 17), local_hour(today, 24)),
                ("Overnight", local_hour(today, 24), local_hour(today, 24 + 8))]

WMO_WORDS = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy", 45: "Fog", 48: "Fog",
             51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle",
             57: "Freezing drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
             66: "Freezing rain", 67: "Freezing rain", 71: "Light snow", 73: "Snow",
             75: "Heavy snow", 77: "Snow grains", 80: "Rain showers", 81: "Rain showers",
             82: "Heavy rain showers", 85: "Snow showers", 86: "Heavy snow showers",
             95: "Thunderstorms", 96: "Thunderstorms with hail", 99: "Thunderstorms with hail"}
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

def fetch_open_meteo_hours(start, end):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&hourly=temperature_2m,precipitation_probability,wind_speed_10m,wind_direction_10m,weather_code"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%2FNew_York"
        f"&start_hour={start:%Y-%m-%dT%H:00}&end_hour={end:%Y-%m-%dT%H:00}"
    )
    try:
        h = fetch_json(url)["hourly"]
    except (KeyError, URLError, TimeoutError, ValueError) as err:
        print("Open-Meteo failed:", err)
        return []
    return [
        {"time": datetime.fromisoformat(t).replace(tzinfo=TZ), "temp": round(temp),
         "pop": pop or 0, "wind": round(wspd), "wind_dir": COMPASS[round(wdir / 45) % 8],
         "words": WMO_WORDS.get(code, "")}
        for t, temp, pop, wspd, wdir, code in zip(
            h["time"], h["temperature_2m"], h["precipitation_probability"],
            h["wind_speed_10m"], h["wind_direction_10m"], h["weather_code"])
    ]

def fetch_nws_words():
    """{local hour datetime: 'Partly sunny'} from the NWS hourly forecast."""
    try:
        hdr = {"Accept": "application/geo+json"}
        points = fetch_json(f"https://api.weather.gov/points/{LATITUDE},{LONGITUDE}", hdr)
        periods = fetch_json(points["properties"]["forecastHourly"], hdr)["properties"]["periods"]
        return {datetime.fromisoformat(p["startTime"]).astimezone(TZ): p["shortForecast"].capitalize()
                for p in periods}
    except (KeyError, URLError, TimeoutError, ValueError) as err:
        print("NWS failed (using Open-Meteo condition words):", err)
        return {}

def summarize(label, rows):
    if not rows:
        return f"{label}: unavailable."
    words = [r["words"] for r in rows if r["words"]]
    sky = words[0] if words else ""
    if words and words[-1] != words[0]:
        sky = f"{words[0]}, becoming {words[-1].lower()}"
    t0, t1 = rows[0]["temp"], rows[-1]["temp"]
    if t1 - t0 >= 3:
        temps = f"rising from {t0}° to {t1}°"
    elif t0 - t1 >= 3:
        temps = f"falling from {t0}° to {t1}°"
    else:
        temps = f"around {round(sum(r['temp'] for r in rows) / len(rows))}°"
    parts = [f"{sky}, {temps}." if sky else f"{temps.capitalize()}."]
    windiest = max(rows, key=lambda r: r["wind"])
    if windiest["wind"] >= 5:
        parts.append(f"{windiest['wind_dir']} wind up to {windiest['wind']} mph.")
    max_pop = max(r["pop"] for r in rows)
    if max_pop >= 20:
        parts.append(f"Chance of precipitation up to {max_pop}%.")
    return f"{label}: " + " ".join(parts)

hourly = fetch_open_meteo_hours(table_start, table_end)
nws_words = fetch_nws_words()
for r in hourly:
    r["words"] = nws_words.get(r["time"], r["words"])
    r["hour"] = r["time"].strftime("%I%p").lstrip("0").lower()[:-1]   # '6a', '12p'

forecast_lines = [summarize(label, [r for r in hourly if a <= r["time"] < b])
                  for label, a, b in segments]
for r in hourly:
    print(r["hour"], r["temp"], r["pop"], r["wind_dir"], r["wind"], r["words"])
print("\n".join(forecast_lines))

# --- Sky drawing helpers ---
bodies = {
    "Sun": {"obj": eph["sun"], "magnitude": -26.74},
    "Moon": {"obj": eph["moon"], "magnitude": -12.6},
    "Mercury": {"obj": eph["mercury barycenter"], "magnitude": -0.23},
    "Venus": {"obj": eph["venus barycenter"], "magnitude": -4.89},
    "Mars": {"obj": eph["mars barycenter"], "magnitude": -2.0},
    "Jupiter": {"obj": eph["jupiter barycenter"], "magnitude": -2.94},
    "Saturn": {"obj": eph["saturn barycenter"], "magnitude": 0.46},
}

LEFT_AXIS_ROTATION, RIGHT_AXIS_ROTATION = -12, 12
LEFT_VIEW_ROTATION = 90 + LEFT_AXIS_ROTATION
RIGHT_VIEW_ROTATION = RIGHT_AXIS_ROTATION
SCREEN_SCALE = 1.2
LABEL_RADIUS = 1.12
CAMERA_EYE = dict(x=1.0416667, y=1.0416667, z=0.4166667)
SPHERE_ZOOM = 1.45    # bigger = larger spheres (orthographic view ignores camera distance)

def spherical_to_cartesian(alt, az, radius=1):
    alt_rad, az_rad = np.radians(alt), np.radians(az)
    return (radius * np.cos(alt_rad) * np.sin(az_rad),
            radius * np.cos(alt_rad) * np.cos(az_rad),
            radius * np.sin(alt_rad))

def rotate_az(az_deg, delta_deg):
    return (az_deg + delta_deg) % 360.0

def circle_in_plane(normal, radius=1, n_points=240):
    normal = np.asarray(normal, dtype=float)
    normal /= np.linalg.norm(normal)
    ref = np.array([0.0, 0.0, 1.0])
    if np.allclose(np.abs(np.dot(normal, ref)), 1.0):
        ref = np.array([0.0, 1.0, 0.0])
    u = np.cross(normal, ref); u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    theta = np.linspace(0, 2 * np.pi, n_points)
    return zip(*[radius * (np.cos(t) * u + np.sin(t) * v) for t in theta])

def line3d(scene, x, y, z, **line):
    return go.Scatter3d(x=x, y=y, z=z, mode="lines", line=line, showlegend=False, scene=scene)

def text3d(scene, x, y, z, text, size):
    return go.Scatter3d(x=[x], y=[y], z=[z], mode="text", text=[text],
                        textfont=dict(size=size, color="black"), showlegend=False, scene=scene)

def add_scene(fig, scene, view_rotation, positions):
    s = SCREEN_SCALE
    hx, hy, hz = circle_in_plane([CAMERA_EYE["x"], CAMERA_EYE["y"], CAMERA_EYE["z"]], radius=1.005)
    fig.add_trace(line3d(scene, hx, hy, hz, color="rgba(0,0,0,0.07)", width=round(7 * s)))

    ring_az = rotate_az(np.linspace(0, 360, 240), view_rotation)
    for lat in [-45, -20, 20, 45]:
        rx, ry, rz = zip(*[spherical_to_cartesian(lat, az) for az in ring_az])
        fig.add_trace(line3d(scene, rx, ry, rz, color="rgba(0,0,0,0.25)", width=max(1, round(s))))

    for name, (x, y, z) in positions.items():
        mag = bodies[name]["magnitude"]
        size = s * (6 if name in ["Sun", "Moon"]
                    else max(2, 10 + (mag - bodies["Moon"]["magnitude"]) * -1.5))
        fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[z], mode="markers",
                                   marker=dict(size=size, color="black"),
                                   showlegend=False, scene=scene))
        scale = LABEL_RADIUS + (0.03 if name in ["Sun", "Moon"] else 0.0)
        lx, ly, lz = np.array([x, y, z]) * scale
        fig.add_trace(text3d(scene, lx, ly, lz, name, round(15 * s)))

    for az in [90, 180, 270]:   # meridian lines from zenith to horizon
        pts = [spherical_to_cartesian(a, rotate_az(az, view_rotation)) for a in np.linspace(90, 0, 50)]
        lx, ly, lz = zip(*pts)
        fig.add_trace(line3d(scene, lx, ly, lz, color="black", width=round(2 * s), dash="dot"))

    ex, ey, ez = zip(*[spherical_to_cartesian(0, az) for az in ring_az])   # horizon
    fig.add_trace(line3d(scene, ex, ey, ez, color="black", width=round(2 * s)))

    for lbl, az in {"E": 90, "S": 180, "W": 270}.items():
        lx, ly, lz = spherical_to_cartesian(0, rotate_az(az, view_rotation))
        fig.add_trace(text3d(scene, lx, ly, lz, lbl, round(14 * s)))

def body_positions(t, view_rotation):
    out = {}
    for name, data in bodies.items():
        alt, az, _ = observer.at(t).observe(data["obj"]).apparent().altaz()
        out[name] = spherical_to_cartesian(alt.degrees, rotate_az(az.degrees, view_rotation))
    return out

# --- Build the page ---
fig = go.Figure()
add_scene(fig, "scene", LEFT_VIEW_ROTATION, body_positions(map_time, LEFT_VIEW_ROTATION))
add_scene(fig, "scene2", RIGHT_VIEW_ROTATION, body_positions(map_time, RIGHT_VIEW_ROTATION))

FONT = dict(color="black", size=16)
HEADER = dict(fill_color="white", line_color="black", font=dict(color="black", size=16), height=30)
CELLS = dict(fill_color="white", line_color="black", font=FONT, height=30)

def cell_time(body, col):
    t = almanac_rows[body][col]
    if t is None:
        return "-"
    return fmt_day_time(t, ref_date)    # weekday added if it's not today

# Sun / moon table
cols = ["Rise", "Meridian", "Set"]
fig.add_trace(go.Table(
    domain=dict(x=[0.01, 0.47], y=[0.20, 0.37]),
    columnwidth=[1.25, 1.45, 1.45, 1.45],
    header=dict(values=["", *cols], align="center", **HEADER),
    cells=dict(
        values=[["Sun", moon_label]] + [
            [cell_time(b, c) for b in ["Sun", "Moon"]]
            for c in cols
        ],
        align=["left", "center", "center", "center"],
        **CELLS,
    ),
))

# Hourly table: one column per hour
if hourly:
    fig.add_trace(go.Table(
        domain=dict(x=[0.01, 0.99], y=[0.0, 0.17]),
        columnwidth=[1.3] + [1] * len(hourly),
        header=dict(values=[""] + [h["hour"] for h in hourly], align="center", **HEADER),
        cells=dict(
            values=[["°F", "Rain"]] + [[f"{h['temp']}°", f"{h['pop']}%"] for h in hourly],
            align="center",
            **CELLS,
        ),
    ))

event_word = "Sunrise" if mode == "sunrise" else "Sunset"
title = f"{map_time.astimezone(TZ):%A, %B} {map_time.astimezone(TZ).day}  ·  Sky at {event_word.lower()}, {fmt_time(map_time)}"
annotations = [
    dict(x=0.5, y=1.0, xref="paper", yref="paper", text=title, showarrow=False,
         font=dict(size=24, color="black"), xanchor="center", yanchor="top"),
    dict(x=0.50, y=0.365, xref="paper", yref="paper",
         text="<br><br>".join("<br>".join(textwrap.wrap(line, 60)) for line in forecast_lines),
         showarrow=False, align="left",
         font=dict(size=16, color="black"), xanchor="left", yanchor="top"),
]
if not hourly:
    annotations.append(dict(x=0.5, y=0.08, xref="paper", yref="paper", showarrow=False,
                            text="Hourly forecast unavailable", font=FONT))

scene_common = dict(
    xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
    bgcolor="white", aspectmode="manual", aspectratio=dict(x=SPHERE_ZOOM, y=SPHERE_ZOOM, z=SPHERE_ZOOM),
    camera=dict(eye=CAMERA_EYE, projection=dict(type="orthographic")),
)
fig.update_layout(
    width=WIDTH, height=HEIGHT, showlegend=False,
    margin=dict(l=0, r=0, t=8, b=8),
    paper_bgcolor="white", plot_bgcolor="white",
    annotations=annotations,
    scene=dict(domain=dict(x=[0.0, 0.5], y=[0.39, 0.97]), **scene_common),
    scene2=dict(domain=dict(x=[0.5, 1.0], y=[0.39, 0.97]), **scene_common),
)

out_path = OUTPUT_DIR / "sky_map_bw.png"
fig.write_image(out_path, width=WIDTH, height=HEIGHT)
print("Saved", out_path)

# Record which map this is, so the GitHub workflow can skip later retries once it's done.
(OUTPUT_DIR / "sky_map_status.txt").write_text(f"{today.isoformat()} {mode}\n")

if os.environ.get("GITHUB_ACTIONS") != "true":
    fig.show()
