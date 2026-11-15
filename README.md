# sky_map

Black-and-white sky map for an Inkplate 10, made with Plotly and Skyfield.

Twice a day it draws the sky at sunrise or sunset and adds:
- sun and moon rise, meridian and set times
- an hourly temperature / rain-chance table (Open-Meteo)
- a two-part forecast built from the NWS hourly forecast

## Schedule (Boston time)

| Map | Made by GitHub Actions | Shown on the Inkplate | Hourly table | Forecast lines |
|---|---|---|---|---|
| Sunrise | overnight (four tries, 1-5 AM) | 5:30 AM | 6 AM - 9 PM | This morning / This afternoon |
| Sunset | during the day (four tries, 12-4 PM) | 4:30 PM | 5 PM - 8 AM | This evening / Overnight |

Each successful run writes `output/sky_map_status.txt`; later tries in the same window see it and stop. A failed run is retried by the next try.

## Contents

- `sky_map_bw.py`: main script, writes `output/sky_map_bw.png`
- `sky_map_for_inkplate10.ino`: Inkplate code that downloads the image at 5:30 AM and 4:30 PM
- `.github/workflows/sky-map.yml`: the schedule

## Usage

The script expects the JPL ephemeris file `de440s.bsp` in this folder.

```bash
python sky_map_bw.py                        # before noon: sunrise map; after noon: sunset map
SKY_MAP_MODE=sunset python sky_map_bw.py    # force one
```
