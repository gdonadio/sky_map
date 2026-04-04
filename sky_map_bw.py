import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from skyfield.api import Loader, Topos

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --- Skyfield setup ---
load = Loader(str(ROOT_DIR))
eph = load("de440s.bsp")
latitude, longitude = 42.3736, -71.1097
observer = eph["earth"] + Topos(
    latitude_degrees=latitude, longitude_degrees=longitude
)
ts = load.timescale()
time = ts.now()

def fetch_current_temperature_f(latitude, longitude):
    weather_url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        "&current=temperature_2m&temperature_unit=fahrenheit"
    )
    try:
        with urlopen(weather_url, timeout=10) as response:
            payload = json.load(response)
        temperature_f = payload["current"]["temperature_2m"]
        return f"Current Outdoor Temperature: {round(temperature_f)}\N{DEGREE SIGN}F"
    except (KeyError, URLError, TimeoutError, ValueError):
        return "Current Outdoor Temperature: unavailable"


temperature_text = fetch_current_temperature_f(latitude, longitude)

bodies = {
    "Sun": {"obj": eph["sun"], "magnitude": -26.74},
    "Moon": {"obj": eph["moon"], "magnitude": -12.6},
    "Mercury": {"obj": eph["mercury barycenter"], "magnitude": -0.23},
    "Venus": {"obj": eph["venus barycenter"], "magnitude": -4.89},
    "Mars": {"obj": eph["mars barycenter"], "magnitude": -2.0},
    "Jupiter": {"obj": eph["jupiter barycenter"], "magnitude": -2.94},
    "Saturn": {"obj": eph["saturn barycenter"], "magnitude": 0.46},
}

def spherical_to_cartesian(alt, az, radius=1):
    alt_rad = np.radians(alt)
    az_rad = np.radians(az)
    x = radius * np.cos(alt_rad) * np.sin(az_rad)
    y = radius * np.cos(alt_rad) * np.cos(az_rad)
    z = radius * np.sin(alt_rad)
    return x, y, z

def rotate_az(az_deg, delta_deg):
    return (az_deg + delta_deg) % 360.0


def circle_in_plane(normal, radius=1, n_points=240):
    normal = np.asarray(normal, dtype=float)
    normal = normal / np.linalg.norm(normal)
    ref = np.array([0.0, 0.0, 1.0])
    if np.allclose(np.abs(np.dot(normal, ref)), 1.0):
        ref = np.array([0.0, 1.0, 0.0])

    u = np.cross(normal, ref)
    u = u / np.linalg.norm(u)
    v = np.cross(normal, u)

    theta = np.linspace(0, 2 * np.pi, n_points)
    points = [radius * (np.cos(t) * u + np.sin(t) * v) for t in theta]
    x, y, z = zip(*points)
    return x, y, z


LEFT_AXIS_ROTATION = -12
RIGHT_AXIS_ROTATION = 12
LEFT_VIEW_ROTATION = 90 + LEFT_AXIS_ROTATION
RIGHT_VIEW_ROTATION = RIGHT_AXIS_ROTATION
SCREEN_SCALE = 1.5
LABEL_RADIUS = 1.12

# Compute body positions for each view
positions_left, positions_right = {}, {}
for name, data in bodies.items():
    ast = observer.at(time).observe(data["obj"]).apparent()
    alt, az, _ = ast.altaz()
    positions_left[name] = spherical_to_cartesian(
        alt.degrees, rotate_az(az.degrees, LEFT_VIEW_ROTATION)
    )
    positions_right[name] = spherical_to_cartesian(
        alt.degrees, rotate_az(az.degrees, RIGHT_VIEW_ROTATION)
    )

# --- Plotly: Two larger scenes side-by-side, no titles ---
fig = make_subplots(
    rows=1,
    cols=2,
    specs=[[{"type": "scene"}, {"type": "scene"}]],
    horizontal_spacing=0.0,
)


def add_scene(fig, col, positions, axis_rotation=0, base_rotation=0, equator_dash="solid"):
    camera_eye = np.array([1.0416667, 1.0416667, 0.4166667])
    halo_x, halo_y, halo_z = circle_in_plane(camera_eye, radius=1.005)
    fig.add_trace(
        go.Scatter3d(
            x=halo_x,
            y=halo_y,
            z=halo_z,
            mode="lines",
            line=dict(color="rgba(0,0,0,0.07)", width=int(round(7 * SCREEN_SCALE))),
            showlegend=False,
        ),
        row=1,
        col=col,
    )

    for latitude in [-45, -20, 20, 45]:
        ring_az = rotate_az(np.linspace(0, 360, 240), base_rotation + axis_rotation)
        rx, ry, rz = zip(*[spherical_to_cartesian(latitude, az) for az in ring_az])
        fig.add_trace(
            go.Scatter3d(
                x=rx,
                y=ry,
                z=rz,
                mode="lines",
                line=dict(
                    color="rgba(0,0,0,0.25)",
                    width=max(1, int(round(1 * SCREEN_SCALE))),
                ),
                showlegend=False,
            ),
            row=1,
            col=col,
        )

    for name, (x, y, z) in positions.items():
        mag = bodies[name]["magnitude"]
        size = SCREEN_SCALE * (
            6
            if name in ["Sun", "Moon"]
            else max(2, 10 + (mag - bodies["Moon"]["magnitude"]) * -1.5)
        )
        fig.add_trace(
            go.Scatter3d(
                x=[x],
                y=[y],
                z=[z],
                mode="markers",
                marker=dict(size=size, color="black"),
                showlegend=False,
            ),
            row=1,
            col=col,
        )

        label_scale = LABEL_RADIUS + (0.03 if name in ["Sun", "Moon"] else 0.0)
        lx, ly, lz = np.array([x, y, z]) * label_scale
        fig.add_trace(
            go.Scatter3d(
                x=[lx],
                y=[ly],
                z=[lz],
                mode="text",
                text=[name],
                textfont=dict(size=int(round(15 * SCREEN_SCALE)), color="black"),
                showlegend=False,
            ),
            row=1,
            col=col,
        )

    # Zenith lines
    view_rotation = base_rotation + axis_rotation
    for az in [90, 180, 270]:
        az_use = rotate_az(az, view_rotation)
        altitudes = np.linspace(90, 0, 50)
        pts = [spherical_to_cartesian(a, az_use) for a in altitudes]
        lx, ly, lz = zip(*pts)
        fig.add_trace(
            go.Scatter3d(
                x=lx,
                y=ly,
                z=lz,
                mode="lines",
                line=dict(color="black", width=int(round(2 * SCREEN_SCALE)), dash="dot"),
                showlegend=False,
            ),
            row=1,
            col=col,
        )

    # Equator circle
    circle_az = rotate_az(np.linspace(0, 360, 240), view_rotation)
    ex, ey, ez = zip(*[spherical_to_cartesian(0, az) for az in circle_az])
    fig.add_trace(
        go.Scatter3d(
            x=ex,
            y=ey,
            z=ez,
            mode="lines",
            line=(
                dict(color="black", width=int(round(2 * SCREEN_SCALE)))
                if equator_dash == "solid"
                else dict(
                    color="black",
                    width=int(round(2 * SCREEN_SCALE)),
                    dash=equator_dash,
                )
            ),
            showlegend=False,
        ),
        row=1,
        col=col,
    )

    # E/S/W labels
    for lbl, az in {"E": 90, "S": 180, "W": 270}.items():
        az_use = rotate_az(az, view_rotation)
        lx, ly, lz = spherical_to_cartesian(0, az_use)
        fig.add_trace(
            go.Scatter3d(
                x=[lx],
                y=[ly],
                z=[lz],
                mode="text",
                text=[lbl],
                textfont=dict(size=int(round(14 * SCREEN_SCALE)), color="black"),
                showlegend=False,
            ),
            row=1,
            col=col,
        )

add_scene(
    fig,
    1,
    positions_left,
    axis_rotation=LEFT_AXIS_ROTATION,
    base_rotation=90,
    equator_dash="solid",
)
add_scene(
    fig,
    2,
    positions_right,
    axis_rotation=RIGHT_AXIS_ROTATION,
    base_rotation=0,
    equator_dash="solid",
)

fig.update_layout(
    showlegend=False,
    margin=dict(l=0, r=0, t=48, b=48),
    paper_bgcolor="white",
    plot_bgcolor="white",
    annotations=[
        dict(
            x=0.5,
            y=-0.02,
            xref="paper",
            yref="paper",
            text=temperature_text,
            showarrow=False,
            font=dict(size=20, color="black"),
            xanchor="center",
            yanchor="top",
        )
    ],
    scene=dict(
        domain=dict(x=[0.00, 0.50], y=[0.00, 1.00]),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        zaxis=dict(visible=False),
        bgcolor="white",
        aspectmode='manual',
        aspectratio=dict(x=1, y=1, z=1),
        camera=dict(eye=dict(x=1.0416667, y=1.0416667, z=0.4166667)),
        camera_projection=dict(type="orthographic"),
    ),
    scene2=dict(
        domain=dict(x=[0.50, 1.00], y=[0.00, 1.00]),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        zaxis=dict(visible=False),
        bgcolor="white",
        aspectmode="manual",
        aspectratio=dict(x=1, y=1, z=1),
        camera=dict(eye=dict(x=1.0416667, y=1.0416667, z=0.4166667)),
        camera_projection=dict(type="orthographic"),
    ),
)

fig.write_image(OUTPUT_DIR / "sky_map_bw.png", width=1200, height=825, engine="kaleido")

if os.environ.get("GITHUB_ACTIONS") != "true":
    fig.show()
