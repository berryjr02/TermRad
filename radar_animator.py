import time
import requests
from io import BytesIO
from PIL import Image
from rich.text import Text
from datetime import datetime, timedelta, timezone
from weather_api import write_log
from functools import lru_cache

# Michigan's rough bounding box (West, South, East, North) - specifically for the Lower Peninsula!
MICHIGAN_BBOX = "-87.00,41.69,-82.50,45.80"

@lru_cache(maxsize=10)
def process_radar_image(img_bytes, padded_lines_tuple, highlight_coord=None):
    """Processes a raw image byte string and converts it to a Rich Text object."""
    img = Image.open(BytesIO(img_bytes)).convert("RGBA")
    width, height = img.size
    text = Text()

    for y in range(height):
        for x in range(width):
            char = padded_lines_tuple[y][x]
            r, g, b, a = img.getpixel((x, y))
            style = ""
            
            # If there's radar data, set the background color
            if a >= 50:
                style = f"on #{r:02x}{g:02x}{b:02x}"

            # Apply the location highlight OVER the map
            if highlight_coord:
                hx, hy = highlight_coord
                if x == hx and y == hy or (hx - 1 <= x <= hx + 1 and hy - 1 <= y <= hy + 1):
                    char = "X"
                    style = "bold black on #FFFFFF"

            # Append the character with the determined style
            if style:
                text.append(char, style=style)
            else:
                text.append(char)
                
        if y < height - 1:
            text.append("\n")
            
    return text

def latlon_to_pixel(lat, lon, bbox_str, width, height):
    """Converts a latitude and longitude to a pixel coordinate."""
    try:
        west_lon, south_lat, east_lon, north_lat = [float(c) for c in bbox_str.split(',')]
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

def get_radar_frames(ascii_map_string, num_frames=5, highlight_lat=None, highlight_lon=None):
    """Fetches radar frames and returns a list of Rich Text objects."""
    
    # 1. Determine dimensions of your ascii map
    lines = ascii_map_string.strip("\n").split("\n")
    
    # Format Map
    lines = [line.rstrip() for line in lines]
    min_indent = min(len(line) - len(line.lstrip()) for line in lines if line.strip())
    lines = [line[min_indent:] for line in lines]
    
    height = len(lines)
    width = max(len(line) for line in lines)

    # Pad lines so they are all exactly the same width for the grid
    padded_lines = [line.ljust(width) for line in lines]
    frames = []
    
    # 2. Fetch images from IEM WMS
    base_url = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q-t.cgi"
    
    # Calculate the pixel to highlight for location, if provided
    highlight_coord = None
    if highlight_lat is not None and highlight_lon is not None:
        highlight_coord = latlon_to_pixel(highlight_lat, highlight_lon, MICHIGAN_BBOX, width, height)
    
    now = datetime.now(timezone.utc)
    now = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)

    for i in range(num_frames, 0, -1):
        frame_time = now - timedelta(minutes=((i - 1) * 15))
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
            "HEIGHT": str(height),
            "TIME": time_str
        }

        try:
            response = requests.get(base_url, params=params, timeout=10)
            if response.status_code == 200:
                if "image" in response.headers.get("Content-Type", ""):
                    # Store raw bytes for caching
                    frames.append(response.content)
        except Exception as e:
            write_log(f"Radar fetch error: {e}") # Log if network drops or API fails

    # 3. Process pixels and build Rich Text frames
    rich_frames = []
    padded_lines_tuple = tuple(padded_lines) # Tuples are hashable for lru_cache
    for img_bytes in frames:
        rich_frames.append(process_radar_image(img_bytes, padded_lines_tuple, highlight_coord)) 
    
    if not rich_frames:
        return [Text(ascii_map_string)]
        
    return rich_frames
