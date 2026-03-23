import argparse
from weather_api import (
    get_coords_manual,
    get_coords_auto,
    get_alerts,
    get_forecast,
    get_numerical_forecast
)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog=__file__,
        description="Testing of weather api(s) for TermRad. Uses ipinfo.io for automatic geolocation, OpenStreetMap's Nominatim for manual geolocation, and the NWS API for weather data.",
    )
    parser.add_argument(
        "-m",
        "--manual",
        action="store_true",
        help="Manually enter location (otherwise auto-located via ipinfo.io)",
    )
    parser.add_argument(
        "-w",
        "--week",
        action="store_true",
        help="Print weekly forecast instead of current day",
    )
    parser.add_argument(
        "-a",
        "--alerts-only",
        action="store_true",
        help="Only print weather alerts",
    )
    return parser.parse_args(argv)


def display_alerts(alerts):
    features = alerts.get("features", [])
    if not features:
        return
    print("\nCURRENT ALERTS:\n")
    for feat in features:
        p = feat["properties"]
        print(f"{p['severity'].upper()} {p['headline']}\n{p['description']}\n")


def display_current(period):
    print("\nCurrent Forecast:\n")
    print(
        f"{period['name']}, {period['temperature']}{chr(176)} {period['temperatureUnit']}"
    )
    print(period["detailedForecast"].replace(". ", ".\n") + "\n")


def display_weekly(periods):
    print("\nWeekly Forecast:")
    for p in periods:
        print(
            f"============\n{p['name']} {p['temperature']}{chr(176)} {p['temperatureUnit']}"
        )
        print(p["detailedForecast"].replace(". ", ".\n"))
    print("============\n")


def main(argv=None):
    args = parse_args(argv)

    if args.manual:
        loc = input("Input location: ")
        lat, lon, country = get_coords_manual(loc)
    else:
        lat, lon, country = get_coords_auto()

    
    if country == "US" or country == "UNITED STATES":
        print("Descriptive forecast:\n")
        alerts = get_alerts(lat, lon)
        display_alerts(alerts)
    else:
        print("\nCLIweather currently only supports the United States.\n")
        return

    if args.alerts_only:
        return

    forecast = get_forecast(lat, lon)

    periods = forecast["properties"]["periods"]

    if args.week:
        display_weekly(periods)
    else:
        display_current(periods[0])

    forecast_data = get_numerical_forecast(lat, lon)
    print("\nNumerical Forecast Data:")
    if args.week:
        for day in forecast_data:
            print(f"{day['time']}: Temp {day['temp']}{day['unit']}, Precip {day['precip']}, Wind {day['wind']}, {day['short_forecast']}")
    else:
        current = forecast_data[0]
        print(f"{current['time']}: Temp {current['temp']}{current['unit']}, Precip {current['precip']}, Wind {current['wind']}, {current['short_forecast']}")

    

if __name__ == "__main__":
    main()