import sys
import time
import datetime
import requests
import logging
from functools import lru_cache

# Configure logging
logging.basicConfig(
    filename="TermRad.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("TermRad")

@lru_cache(maxsize=6)
def fetch_json(url, desc):
    headers = {
    "User-Agent": "TermRad Terminal Weather App (https://github.com/berryjr02/TermRad)",
    "Accept": "application/json"
    }
    try:
        for count in range(3):
            r = requests.get(url,headers=headers)
            if r.status_code == 200:
                return r.json()
            else:
                time.sleep(2 ** count)
    except requests.RequestException as e:
        write_log(f"{desc} error! {e}")
        return None

def get_coords_manual(user_location):
    # If it's a 5-digit zip code, append ", USA" to avoid international results
    if user_location.isdigit() and len(user_location) == 5:
        search_query = f"{user_location}, USA"
    else:
        search_query = user_location

    url = (
        "https://nominatim.openstreetmap.org/search?"
        f"q={search_query}&format=json&limit=1"
    )
    data = fetch_json(url, "Geocode API")
    
    if not data or len(data) == 0:
        write_log(f"Geocode API returned no results for {search_query}")
        return None, None, None

    data = data[0]
    country = data.get("display_name", "").split(", ")[-1].upper()

    return str(data["lat"]), str(data["lon"]), str(country)

@lru_cache(maxsize=1)
def get_coords_auto():
    data = fetch_json("http://ipinfo.io/json", "IP geolocation")
    if not data:
        return None, None, None
    
    loc = data.get("loc", "")
    if "," in loc:
        lat, lon = loc.split(",")
    else:
        lat, lon = None, None
        
    country = data.get("country", "")
    return lat, lon, country

@lru_cache(maxsize=1)
def get_point_metadata(lat, lon):
    if lat is None or lon is None:
        return None 
    url = f"https://api.weather.gov/points/{lat},{lon}"
    write_log(f"Fetching point metadata from NWS for {lat}, {lon}")
    return fetch_json(url, "NWS location data")

@lru_cache(maxsize=1)
def get_alerts(lat, lon):
    if lat is None or lon is None:
        return {"features": []}  # Return empty alerts if location is unknown
    url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
    data = fetch_json(url, "NWS alerts")
    return data if data else {"features": []}

@lru_cache(maxsize=1)
def get_forecast(lat, lon):
    if lat is None or lon is None:
        return None
    
    metadata = get_point_metadata(lat, lon)
    if not metadata or "properties" not in metadata:
        return None
        
    forecast_url = metadata["properties"].get("forecast")
    if not forecast_url:
        return None
        
    return fetch_json(forecast_url, "NWS forecast")


@lru_cache(maxsize=2)
def get_numerical_forecast(lat, lon):
    if lat is None or lon is None:
        return []  # Return empty forecast if location is unknown
    
    raw_data = get_forecast(lat, lon)
    if not raw_data or "properties" not in raw_data:
        return []
    
    periods = raw_data["properties"].get("periods", [])
    
    forecast_list = []
    
    for period in periods:
        precip_dict = period.get("probabilityOfPrecipitation", {})
        precip_chance = precip_dict.get("value") or 0 
        
        stats = {
            "time": period.get("name"), # "Tuesday Night"
            "temp": period.get("temperature"),  # 72
            "unit": period.get("temperatureUnit"),  # "F"
            "precip": f"{precip_chance}%",  # "20%"
            "wind": period.get("windSpeed"),    # "5 to 10 mph"
            "is_day": period.get("isDaytime"),   # True/False
            "short_forecast": period.get("shortForecast")   # "Partly Cloudy"
        }
        forecast_list.append(stats)
        
    return forecast_list

def write_log(message):
    logger.info(message)
