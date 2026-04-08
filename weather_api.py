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
        print(f"{desc} error! {e}")
        sys.exit(1)

@lru_cache(maxsize=1)
def get_coords_manual(user_location):
    url = (
        "https://nominatim.openstreetmap.org/search?"
        f"q={user_location}&format=json&limit=1"
    )
    data = fetch_json(url, "Geocode API")[0]

    country = data["display_name"].split(", ")[-1].upper()

    return str(data["lat"]), str(data["lon"]), str(country)

@lru_cache(maxsize=1)
def get_coords_auto():
    data = fetch_json("http://ipinfo.io/json", "IP geolocation")
    lat, lon = data["loc"].split(",")
    country = data["country"]
    return lat, lon, country

@lru_cache(maxsize=1)
def get_point_metadata(lat, lon):
    if lat is None or lon is None:
        return {"properties": {"forecast": None}}  # Return empty metadata if location is unknown
    url = f"https://api.weather.gov/points/{lat},{lon}"
    print(f"Fetching point metadata from NWS for {lat}, {lon} with URL: {url}")
    return fetch_json(url, "NWS location data")

@lru_cache(maxsize=1)
def get_alerts(lat, lon):
    if lat is None or lon is None:
        return {"features": []}  # Return empty alerts if location is unknown
    url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
    return fetch_json(url, "NWS alerts")

@lru_cache(maxsize=1)
def get_forecast(lat, lon):
    if lat is None or lon is None:
        return []  # Return empty forecast if location is unknown
    return fetch_json(get_point_metadata(lat, lon)["properties"]["forecast"], "NWS forecast")


@lru_cache(maxsize=2)
def get_numerical_forecast(lat, lon):
    if lat is None or lon is None:
        return []  # Return empty forecast if location is unknown
    raw_data = get_forecast(lat, lon)
    
    periods = raw_data.get("properties", {}).get("periods", [])
    
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
