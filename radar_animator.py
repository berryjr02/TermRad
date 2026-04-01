import time
import requests
from io import BytesIO
from PIL import Image
from rich.text import Text
from datetime import datetime, timedelta, timezone

# Michigan's rough bounding box (West, South, East, North)
MICHIGAN_BBOX = "-90.41,41.69,-82.41,48.30"

def get_radar_frames(ascii_map_string, num_frames=5):
    """Fetches radar frames and returns a list of Rich Text objects."""
    
    # 1. Determine dimensions of your ascii map
    lines = ascii_map_string.strip("\n").split("\n")
    height = len(lines)
    width = max(len(line) for line in lines)
    
    # Pad lines so they are all exactly the same width
    padded_lines = [line.ljust(width) for line in lines]

    frames = []
    
    # 2. Fetch images from IEM WMS
    base_url = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q-t.cgi"
    
    # Get current time, offset by 10 minutes to allow radar processing, then round to 15 mins
    now = datetime.now(timezone.utc) - timedelta(minutes=10)
    now = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)

    for i in range(num_frames, 0, -1):
        frame_time = now - timedelta(minutes=(i * 15))
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
                # SAFETY CHECK: Ensure the server actually sent an image, not an XML error
                content_type = response.headers.get("Content-Type", "")
                
                if "image" in content_type:
                    img = Image.open(BytesIO(response.content)).convert("RGBA")
                    
                    # DEBUG: Save the last frame to your folder so you can verify it exists
                    if i == 1:
                        img.save("debug_radar.png")
                        
                    frames.append(img)
                else:
                    # If it's XML/text, log what the server is actually complaining about!
                    with open("radar_error.log", "a") as f:
                        f.write(f"[{time_str}] Server returned text error: {response.text[:300]}\n")
            else:
                with open("radar_error.log", "a") as f:
                    f.write(f"[{time_str}] Failed with status: {response.status_code}\n")
        except Exception as e:
            with open("radar_error.log", "a") as f:
                f.write(f"[{time_str}] Request exception: {e}\n")

    # 3. Process pixels and build Rich Text frames
    rich_frames = []
    for img in frames:
        text = Text()
        for y in range(height):
            for x in range(width):
                char = padded_lines[y][x]
                
                # Get the pixel color at this exact character's position
                r, g, b, a = img.getpixel((x, y))

                # If the pixel is mostly transparent, just draw the character
                if a < 50:
                    text.append(char)
                else:
                    # Apply the radar pixel color as the background of the character
                    hex_color = f"#{r:02x}{g:02x}{b:02x}"
                    text.append(char, style=f"on {hex_color}")
                    
            if y < height - 1:
                text.append("\n")
                
        rich_frames.append(text) 
    
    # If all API requests failed, return the static map as a fallback
    if not rich_frames:
        return [Text(ascii_map_string)]
        
    return rich_frames