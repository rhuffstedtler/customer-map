

import argparse
import datetime
import json
import os
import sys
import time
import urllib.parse
import folium
import pandas as pd
import requests

API_KEY = "YOUR NEW API KEY HERE"  # Replace with your actual Google API key
INPUT_CSV = "20261121 Active Recurring Customers.csv"
OUTPUT_CSV = "20261121_Customers_With_Drive_Times.csv"
ZCTA_CACHE = "ga_zcta_boundaries.geojson"
OUTPUT_MAP = "customer_map.html"
ORIGIN = "1242 Clairmont Rd, Decatur, GA 30030"

parser = argparse.ArgumentParser(
    description="Enrich customer CSV with Monday 9AM drive times and map by zip code."
)
parser.add_argument(
    "--refresh",
    action="store_true",
    help="Force re-querying Google Routes & Geocoding APIs even if enriched CSV exists.",
)
args = parser.parse_args()

# 24 high-contrast hex colors so all 23 unique zip codes get a distinct color
PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#17becf",
    "#bcbd22",
    "#393b79",
    "#637939",
    "#8c6d31",
    "#843c39",
    "#7b4173",
    "#3182bd",
    "#e6550d",
    "#31a354",
    "#756bb1",
    "#636363",
    "#d62728",
    "#008080",
    "#c51b8a",
    "#2b8cbe",
    "#d95f02",
    "#54278f",
]


def build_address(row):
    parts = [
        str(row["address_line_one"]).strip(),
        str(row["city"]).strip(),
        str(row["state"]).strip(),
        str(row["zip_code"]).split("-")[0].strip(),
    ]
    return ", ".join([p for p in parts if p and p.lower() != "nan"])


def dump_http_error(api_name, row_idx, dest, payload, resp):
    print("\n" + "=" * 70)
    print(f"[FATAL - {api_name} ERROR] Failed on Row {row_idx + 1}: {dest}")
    print(f"HTTP Status: {resp.status_code}")
    if payload:
        print(f"Request Payload:\n{json.dumps(payload, indent=2)}")
    print(f"Response Headers:\n{dict(resp.headers)}")
    try:
        print(f"Full JSON Error Body:\n{json.dumps(resp.json(), indent=2)}")
    except Exception:
        print(f"Raw Response Text:\n{resp.text}")
    print("=" * 70 + "\n")


def get_drive_time_range(row_idx, dest, arrival_iso, max_retries=3):
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration",
    }
    payload = {
        "origin": {"address": ORIGIN},
        "destination": {"address": dest},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "arrivalTime": arrival_iso,
    }

    for attempt in range(1, max_retries + 1):
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        try:
            data = resp.json()
        except Exception:
            dump_http_error("ROUTES API (NON-JSON)", row_idx, dest, payload, resp)
            sys.exit(1)

        if "error" in data:
            status = data["error"].get("status", "")
            if (
                status in ("PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "UNAVAILABLE")
                and attempt < max_retries
            ):
                wait = attempt * 3
                print(
                    f"  [RETRY {attempt}/{max_retries}] {status} on '{dest}' — waiting {wait}s..."
                )
                time.sleep(wait)
                continue

            dump_http_error("ROUTES API", row_idx, dest, payload, resp)
            sys.exit(1)

        try:
            route = data["routes"][0]
            traffic_secs = int(route["duration"].rstrip("s"))
            static_secs = int(route["staticDuration"].rstrip("s"))
            mn = round(min(traffic_secs, static_secs) / 60, 1)
            mx = round(max(traffic_secs, static_secs) / 60, 1)
            return mn, mx
        except (KeyError, IndexError):
            print(
                f"  [WARNING] No route returned for '{dest}'. Raw response: {json.dumps(data)}"
            )
            return None, None


def geocode(row_idx, dest, max_retries=3):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(dest)}&key={API_KEY}"

    for attempt in range(1, max_retries + 1):
        resp = requests.get(url, timeout=15)
        try:
            data = resp.json()
        except Exception:
            dump_http_error("GEOCODING API (NON-JSON)", row_idx, dest, None, resp)
            sys.exit(1)

        status = data.get("status")
        if (
            status in ("REQUEST_DENIED", "OVER_QUERY_LIMIT", "UNKNOWN_ERROR")
            and attempt < max_retries
        ):
            wait = attempt * 3
            print(
                f"  [RETRY {attempt}/{max_retries}] Geocode {status} on '{dest}' — waiting {wait}s..."
            )
            time.sleep(wait)
            continue

        if status in ("REQUEST_DENIED", "OVER_DAILY_LIMIT", "INVALID_REQUEST"):
            dump_http_error("GEOCODING API", row_idx, dest, None, resp)
            sys.exit(1)

        if status != "OK":
            print(f"  [WARNING] Could not geocode ({status}): {dest}")
            return None, None

        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]


def get_zcta_geojson(zip_list):
    """Fetch ZCTA polygon boundaries & internal label coordinates from U.S. Census TIGERweb and cache locally."""
    if os.path.exists(ZCTA_CACHE):
        with open(ZCTA_CACHE, "r", encoding="utf-8") as f:
            cached = json.load(f)
        cached_zips = {
            feat["properties"]["ZCTA5"] for feat in cached.get("features", [])
        }
        if set(zip_list).issubset(cached_zips):
            print(f"Loaded cached zip boundaries from '{ZCTA_CACHE}'.")
            return cached

    print(
        f"Fetching polygon boundaries for {len(zip_list)} zip codes from U.S. Census TIGERweb..."
    )
    in_clause = ",".join([f"'{z}'" for z in zip_list])
    tiger_url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query"
    params = {
        "where": f"ZCTA5 IN ({in_clause})",
        "outFields": "ZCTA5,CENTLAT,CENTLON,INTPTLAT,INTPTLON",
        "outSR": "4326",
        "f": "geojson",
    }
    resp = requests.get(tiger_url, params=params, timeout=30)
    resp.raise_for_status()
    geojson_data = resp.json()

    with open(ZCTA_CACHE, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f)
    print(f"Saved zip boundaries to '{ZCTA_CACHE}'.")
    return geojson_data


def make_pin_icon(hex_color):
    """Create a crisp SVG teardrop pin in any arbitrary hex color."""
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="26" height="36" viewBox="0 0 26 36">
      <path d="M13 0C5.8 0 0 5.8 0 13c0 9.8 13 23 13 23s13-13.2 13-23C26 5.8 20.2 0 13 0z"
            fill="{hex_color}" stroke="#ffffff" stroke-width="2"/>
      <circle cx="13" cy="13" r="4.5" fill="#ffffff"/>
    </svg>
    """
    return folium.DivIcon(
        html=svg,
        icon_size=(26, 36),
        icon_anchor=(13, 36),
        popup_anchor=(0, -32),
    )


# 1. Load cached enriched CSV if available and --refresh is not set
required_cols = {
    "min_drive_time_mins",
    "max_drive_time_mins",
    "latitude",
    "longitude",
}
use_cache = False

if os.path.exists(OUTPUT_CSV) and not args.refresh:
    cached_df = pd.read_csv(OUTPUT_CSV)
    if required_cols.issubset(cached_df.columns):
        print(
            f"Loaded existing enriched data from '{OUTPUT_CSV}' (pass --refresh to re-query Google APIs)."
        )
        df = cached_df
        use_cache = True
    else:
        print(
            f"'{OUTPUT_CSV}' exists but is missing lat/lng columns; enriching from '{INPUT_CSV}'..."
        )

if not use_cache:
    now = datetime.datetime.now().astimezone()
    days_ahead = (0 - now.weekday() + 7) % 7 or 7
    next_monday_9am = (now + datetime.timedelta(days=days_ahead)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    arrival_iso = next_monday_9am.astimezone(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    print(f"Target Arrival (Local): {next_monday_9am} | (UTC): {arrival_iso}\n")

    df = pd.read_csv(INPUT_CSV)
    min_times, max_times, lats, lngs = [], [], [], []

    for idx, row in df.iterrows():
        addr = build_address(row)
        mn, mx = get_drive_time_range(idx, addr, arrival_iso)
        lat, lng = geocode(idx, addr)
        min_times.append(mn)
        max_times.append(mx)
        lats.append(lat)
        lngs.append(lng)
        print(f"[{idx+1}/{len(df)}] {addr} -> {mn}–{mx} min ({lat}, {lng})")
        time.sleep(0.2)

    df["min_drive_time_mins"] = min_times
    df["max_drive_time_mins"] = max_times
    df["latitude"] = lats
    df["longitude"] = lngs

    try:
        df.to_csv(OUTPUT_CSV, index=False)
        print(f"\nSaved enriched CSV to '{OUTPUT_CSV}'.")
    except PermissionError:
        fallback = f"20261121_Customers_With_Drive_Times_{int(time.time())}.csv"
        df.to_csv(fallback, index=False)
        print(
            f"\n[WARNING] '{OUTPUT_CSV}' was open/locked. Saved to '{fallback}' instead."
        )

# 2. Map zip codes to unique hex colors
df["zip5"] = df["zip_code"].astype(str).str[:5]
unique_zips = sorted(df["zip5"].unique())
zip_color_map = {z: PALETTE[i % len(PALETTE)] for i, z in enumerate(unique_zips)}

# 3. Initialize map on Esri Light Gray Canvas
office_lat, office_lng = 33.7891791, -84.3076112
m = folium.Map(
    location=[office_lat, office_lng],
    zoom_start=11,
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles &copy; Esri",
    name="Labels",
    overlay=True,
    control=False,
).add_to(m)

# 4. Add zip code polygon borders and color-matched zip code labels
try:
    zcta_geojson = get_zcta_geojson(unique_zips)
    # Filter features strictly to zip codes present in our dataset
    zcta_geojson["features"] = [
        feat
        for feat in zcta_geojson.get("features", [])
        if feat["properties"].get("ZCTA5") in zip_color_map
    ]

    folium.GeoJson(
        zcta_geojson,
        name="Zip Code Boundaries",
        style_function=lambda feat: {
            "color": zip_color_map.get(feat["properties"]["ZCTA5"], "#333333"),
            "weight": 2.5,
            "opacity": 0.9,
            "fillColor": zip_color_map.get(feat["properties"]["ZCTA5"], "#333333"),
            "fillOpacity": 0.06,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["ZCTA5"],
            aliases=["Zip Code:"],
            sticky=True,
        ),
    ).add_to(m)

    # Place a color-matched text badge at each zip code's internal centroid
    for feat in zcta_geojson["features"]:
        props = feat["properties"]
        z = props["ZCTA5"]
        color = zip_color_map[z]
        clat = float(props.get("INTPTLAT") or props.get("CENTLAT"))
        clon = float(props.get("INTPTLON") or props.get("CENTLON"))

        label_html = (
            f'<div style="font-size: 11px; font-weight: 700; color: {color}; '
            f"background: rgba(255, 255, 255, 0.85); border: 1.5px solid {color}; "
            f"border-radius: 4px; padding: 1px 5px; white-space: nowrap; "
            f'box-shadow: 0 1px 2px rgba(0,0,0,0.15);">{z}</div>'
        )
        folium.Marker(
            [clat, clon],
            icon=folium.DivIcon(
                html=label_html,
                icon_size=(54, 20),
                icon_anchor=(27, 10),
            ),
        ).add_to(m)
except Exception as e:
    print(f"[WARNING] Could not load Census zip boundaries: {e}")

# 5. Add Office Pin
folium.Marker(
    [office_lat, office_lng],
    popup="<b>Office:</b> 1242 Clairmont Rd, Decatur, GA 30030",
    tooltip="<b>Office</b><br>1242 Clairmont Rd, Decatur, GA 30030",
    icon=folium.Icon(color="red", icon="home"),
).add_to(m)

# 6. Add Customer Pins with Name + Min/Max Drive Time in both Hover Tooltip & Click Popup
for idx, row in df.iterrows():
    if pd.notna(row["latitude"]) and pd.notna(row["longitude"]):
        name = f"{row['user__first_name']} {row['user__last_name']}"
        z = row["zip5"]
        mn = row["min_drive_time_mins"]
        mx = row["max_drive_time_mins"]
        pin_color = zip_color_map[z]

        info_html = (
            f"<b>{name}</b><br>"
            f"{build_address(row)}<br>"
            f"<b>Zip:</b> {z}<br>"
            f"<b>Mon 9AM Drive:</b> {mn}–{mx} mins"
        )
        hover_html = (
            f"<b>{name}</b> ({z})<br>" f"Mon 9AM Drive: <b>{mn}–{mx} mins</b>"
        )

        folium.Marker(
            [row["latitude"], row["longitude"]],
            popup=folium.Popup(info_html, max_width=260),
            tooltip=folium.Tooltip(hover_html),
            icon=make_pin_icon(pin_color),
        ).add_to(m)

m.save(OUTPUT_MAP)
print(f"Saved map to '{OUTPUT_MAP}'.")