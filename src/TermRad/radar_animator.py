from datetime import datetime, timedelta, timezone
from io import BytesIO

import concurrent.futures
import requests
from PIL import Image
from rich.text import Text

try:
    from .weather_api import write_log
except (ImportError, ValueError):
    from weather_api import write_log
from functools import lru_cache

# Shifted 0.3 degrees east to pull the marker left onto Michigan
MICHIGAN_BBOX = "-87.6643,41.69,-81.2357,45.80"


@lru_cache(maxsize=10)
def process_radar_image(
    img_bytes, padded_lines_tuple, highlight_coord=None, quality="High-Res"
):
    """Processes a raw image and converts it to Rich Text based on quality setting."""
    img = Image.open(BytesIO(img_bytes)).convert("RGBA")
    width, img_height = img.size
    pixels = img.load()
    text = Text()

    # Pre-calculate the highlight area
    hx, hy = highlight_coord if highlight_coord else (-10, -10)

    # HIGH-RES MODE (Half-blocks)
    if quality == "High-Res":
        char_height = img_height // 2
        for y_char in range(char_height):
            y_top = y_char * 2
            y_bot = y_top + 1
            for x in range(width):
                r1, g1, b1, a1 = pixels[x, y_top]
                r2, g2, b2, a2 = pixels[x, y_bot]
                char = padded_lines_tuple[y_char][x]

                # Marker Logic (Highest Priority)
                is_plus = (x == hx and abs(y_char - hy) <= 1) or (
                    y_char == hy and abs(x - hx) <= 1
                )
                if is_plus:
                    marker_char = "X" if x == hx and y_char == hy else "+"
                    has_any_radar = a1 >= 50 or a2 >= 50
                    if has_any_radar:
                        # Blend marker with strongest radar background
                        r_bg, g_bg, b_bg = (r1, g1, b1) if a1 >= a2 else (r2, g2, b2)
                        style = f"bold #FFFFFF on #{r_bg:02x}{g_bg:02x}{b_bg:02x}"
                    else:
                        style = "bold #FFFFFF on #000000"
                    text.append(marker_char, style=style)
                    continue

                # Radar Rendering Logic (The "Hybrid" System)
                has_top = a1 >= 50 and (r1 + g1 + b1 > 30)
                has_bot = a2 >= 50 and (r2 + g2 + b2 > 30)

                if has_top and has_bot:
                    # DENSE STORM: Use high-res half block
                    style = f"#{r1:02x}{g1:02x}{b1:02x} on #{r2:02x}{g2:02x}{b2:02x}"
                    text.append("▀", style=style)
                elif has_top:
                    # EDGE (Top only): Use map character with radar background
                    # This removes black pixels and integrates the map art
                    text.append(char, style=f"on #{r1:02x}{g1:02x}{b1:02x}")
                elif has_bot:
                    # EDGE (Bottom only): Use map character with radar background
                    text.append(char, style=f"on #{r2:02x}{g2:02x}{b2:02x}")
                else:
                    # NO RADAR: Just the map character
                    text.append(char)

            if y_char < char_height - 1:
                text.append("\n")

    # STANDARD MODE (Classic Blocks)
    else:
        for y in range(img_height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                char = padded_lines_tuple[y][x]

                # Marker Logic
                is_plus = (x == hx and abs(y - hy) <= 1) or (
                    y == hy and abs(x - hx) <= 1
                )
                if is_plus:
                    marker_char = "X" if x == hx and y == hy else "+"
                    style = (
                        f"bold #FFFFFF on #{r:02x}{g:02x}{b:02x}"
                        if a >= 50
                        else "bold #FFFFFF on #000000"
                    )
                    text.append(marker_char, style=style)
                    continue

                # Radar Logic
                if a >= 50 and (r + g + b > 30):
                    text.append(char, style=f"on #{r:02x}{g:02x}{b:02x}")
                else:
                    text.append(char)

            if y < img_height - 1:
                text.append("\n")

    return text


def latlon_to_pixel(lat, lon, bbox_str, width, height):
    """Converts a latitude and longitude to a pixel coordinate."""
    try:
        west_lon, south_lat, east_lon, north_lat = [
            float(c) for c in bbox_str.split(",")
        ]
        lat, lon = float(lat), float(lon)

        # Check if the coordinate is within the bounding box
        if not (south_lat <= lat <= north_lat and west_lon <= lon <= east_lon):
            return None

        # Calculate percentage across the map
        lon_fraction = (lon - west_lon) / (east_lon - west_lon)
        lat_fraction = (north_lat - lat) / (north_lat - south_lat)

        # FIX: Use round() and (width - 1) for accurate 0-indexed terminal mapping
        x = round(lon_fraction * (width - 1))
        y = round(lat_fraction * (height - 1))

        # Clamp values to be safely within image bounds
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))

        return x, y
    except (ValueError, IndexError):
        return None


def fetch_radar_frame(base_url, params):
    """Helper to fetch a single radar frame."""
    try:
        response = requests.get(base_url, params=params, timeout=10)
        if response.status_code == 200 and "image" in response.headers.get(
            "Content-Type", ""
        ):
            return response.content
    except Exception as e:
        write_log(f"Radar frame fetch error: {e}")
    return None


@lru_cache(maxsize=2)
def get_radar_frames(
    ascii_map_string,
    num_frames=5,
    highlight_lat=None,
    highlight_lon=None,
    quality="High-Res",
    interval_mins=5,
):
    """Fetches radar frames and returns a list of Rich Text objects."""

    # 1. Determine dimensions of your ascii map
    raw_lines = ascii_map_string.split("\n")

    # Programmatically pad every line with 15 spaces on both sides
    # This ensures perfect centering and a 100-character wide view
    lines = [" " * 15 + line + " " * 15 for line in raw_lines]

    height = len(lines)
    width = max(len(line) for line in lines)

    # Pad lines so they are all exactly the same width for the grid
    padded_lines = [line.ljust(width) for line in lines]

    # 2. Fetch images from IEM WMS
    base_url = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q-t.cgi"

    # Calculate the pixel to highlight for location, if provided
    highlight_coord = None
    if highlight_lat is not None and highlight_lon is not None:
        highlight_coord = latlon_to_pixel(
            highlight_lat, highlight_lon, MICHIGAN_BBOX, width, height
        )

    now = datetime.now(timezone.utc)
    # Align to 5-minute mark and offset by 10 mins to ensure data is available
    now = now - timedelta(minutes=10)
    now = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)

    # Prepare all request parameters first
    request_params = []
    # Adjust download height based on quality mode
    fetch_height = height * 2 if quality == "High-Res" else height

    for i in range(num_frames, 0, -1):
        # Dynamic intervals for smoother movement or wider history
        frame_time = now - timedelta(minutes=((i - 1) * interval_mins))
        time_str = frame_time.strftime("%Y-%m-%dT%H:%M:00Z")

        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetMap",
            "FORMAT": "image/png",
            "TRANSPARENT": "true",
            "LAYERS": "nexrad-n0q-wmst",
            "SRS": "EPSG:4326",
            "BBOX": MICHIGAN_BBOX,
            "WIDTH": str(width),
            "HEIGHT": str(fetch_height),
            "TIME": time_str,
        }
        request_params.append(params)

    # Fetch images in parallel
    frames_results = [None] * num_frames
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_frames) as executor:
        # We use a list to keep the frames in the correct chronological order
        future_to_index = {
            executor.submit(fetch_radar_frame, base_url, p): i
            for i, p in enumerate(request_params)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            frames_results[idx] = future.result()

    # Filter out any failed frames
    frames = [f for f in frames_results if f is not None]

    # 3. Process pixels and build Rich Text frames
    rich_frames = []
    padded_lines_tuple = tuple(padded_lines)  # Tuples are hashable for lru_cache
    for img_bytes in frames:
        rich_frames.append(
            process_radar_image(img_bytes, padded_lines_tuple, highlight_coord, quality)
        )

    if not rich_frames:
        return [Text(ascii_map_string)]

    return rich_frames
