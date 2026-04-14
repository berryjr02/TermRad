#!/usr/bin/env python3
import json
import os

from rich.text import Text
from textual import work
from textual.app import App, Binding, ComposeResult
from textual.containers import Center, Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    Log,
    RadioButton,
    RadioSet,
    Static,
)

try:
    from .radar_animator import get_radar_frames
    from .weather_api import (
        get_alerts,
        get_coords_auto,
        get_coords_manual,
        get_numerical_forecast,
        write_log,
    )
except (ImportError, ValueError):
    from radar_animator import get_radar_frames
    from weather_api import (
        get_alerts,
        get_coords_auto,
        get_coords_manual,
        get_numerical_forecast,
        write_log,
    )
import argparse
import concurrent.futures
from datetime import datetime, timedelta
from functools import lru_cache

termrad_theme = Theme(
    name="termrad",
    primary="#CC8E39",
    secondary="#CC8E39",
    accent="#CC8E39",
    background="#222222",
    surface="#333333",
    error="#FF5555",
    success="#00FF00",
    warning="#FFFF00",
)

# Get the directory of the current script to find assets relative to it
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def load_asset(filename):
    """Utility to load a text asset from the assets folder."""
    try:
        with open(os.path.join(ASSETS_DIR, filename), "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


ASCII_ART = load_asset("logo.txt")


@lru_cache(maxsize=1)
def get_settings():
    """Load settings from the centralized settings file."""
    try:
        from .weather_api import SETTINGS_FILE
    except (ImportError, ValueError):
        from weather_api import SETTINGS_FILE

    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_temperature_unit():
    """Get the temperature unit preference."""
    settings = get_settings()
    temp_pref = settings.get("temperature", "Fahrenheit")
    return "C" if temp_pref == "Celsius" else "F"


def get_time_format():
    """Get the time format preference."""
    settings = get_settings()
    time_pref = settings.get("time_format", "12 hour")
    return "%H:%M:%S" if time_pref == "24 hour" else "%I:%M %p"


def get_radar_quality():
    """Get the radar rendering quality preference."""
    settings = get_settings()
    return settings.get("radar_quality", "High-Res")


def get_radar_profile():
    """Get the radar performance profile."""
    settings = get_settings()
    profile = settings.get("radar_profile", "Balanced (1 hr)")
    # Mapping profiles to (frames, interval)
    # Spans are calculated as: (frames - 1) * interval
    profiles = {
        "Lite (30 min)": (7, 5),  # (7-1)*5 = 30 mins
        "Balanced (1 hr)": (13, 5),  # (13-1)*5 = 60 mins
        "Deep (2 hr)": (25, 5),  # (25-1)*5 = 120 mins
    }
    return profiles.get(profile, (13, 5))


def get_animation_speed():
    """Get the radar animation speed in seconds."""
    settings = get_settings()
    speed_pref = settings.get("animation_speed", "Normal")
    speeds = {"Fast": 0.3, "Normal": 0.6, "Slow": 1.0}
    return speeds.get(speed_pref, 0.6)


def get_app_coordinates():
    """Get coordinates based on current app settings."""
    settings = get_settings()
    use_ip = settings.get("use_ip", True)
    zip_code = settings.get("zip_code", "")

    if use_ip in [True, "true", "True"]:
        return get_coords_auto()
    elif zip_code:
        return get_coords_manual(zip_code)
    return None, None, None


def convert_temp(temp_f, unit):
    """Convert Fahrenheit to the specified unit."""
    if unit == "C":
        return round((temp_f - 32) * (5.0 / 9.0), 1)
    return temp_f


def get_temp_color(temp_f: int) -> str:
    """Assign colors based on temperature heat levels."""
    if temp_f < 45:
        return "#5555FF"  # Cold (Blue)
    elif temp_f < 65:
        return "#FFFF55"  # Mild (Yellow)
    elif temp_f < 85:
        return "#FFAA00"  # Warm (Orange)
    return "#FF5555"  # Hot (Red)


MICHIGAN_MAP_PLACEHOLDER = load_asset("mich.txt")


class HomeScreen(Screen):
    """The main menu screen."""

    BINDINGS = [
        Binding("1", "go_radar", "Radar", show=False),
        Binding("2", "go_forecast", "Forecast", show=False),
        Binding("3", "go_settings", "Settings", show=False),
    ]

    def compose(self) -> ComposeResult:
        header = Header(show_clock=True)
        header.time_format = get_time_format()
        yield header
        with Vertical(id="home-container"):
            with (
                Center()
            ):  # <--- This container mathematically forces the block to center
                yield Static(ASCII_ART, id="title-art")
            with Center():
                yield Button(
                    "1. Michigan Radar",
                    id="btn-radar",
                    variant="default",
                    classes="menu-button",
                )
            with Center():
                yield Button(
                    "2. Michigan Forecast",
                    id="btn-forecast",
                    variant="default",
                    classes="menu-button",
                )
            if not self.app.public_mode:
                with Center():
                    yield Button(
                        "3. Config Settings",
                        id="btn-settings",
                        variant="default",
                        classes="menu-button",
                    )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-radar":
            self.app.switch_screen("radar")
        elif event.button.id == "btn-forecast":
            self.app.switch_screen("forecast")
        elif event.button.id == "btn-settings":
            self.app.switch_screen("settings")

    # --- Keyboard Action Handlers ---
    def action_go_radar(self) -> None:
        self.app.switch_screen("radar")

    def action_go_settings(self) -> None:
        self.app.switch_screen("settings")

    def action_go_forecast(self) -> None:
        self.app.switch_screen("forecast")

    def on_screen_resume(self) -> None:
        """Update header format when returning to home screen."""
        self.query_one(Header).time_format = get_time_format()


class ForecastWidget(Static):
    def __init__(self, period: dict, **kwargs):
        super().__init__(**kwargs)
        self.period = period

    def render(self) -> Text:
        p = self.period
        unit = get_temperature_unit()
        temp_val = convert_temp(p["temp"], unit)

        # Color based on Fahrenheit original value for consistency
        temp_color = get_temp_color(p["temp"])

        return Text.assemble(
            (f"{p['time']}\n", "bold underline"),
            (f"{temp_val}°{unit}\n", f"bold {temp_color}"),
            (f"{p['short_forecast']}\n", "italic"),
            ("Wind: ", "dim"),
            (f"{p['wind']}\n", ""),
            ("Precip: ", "dim"),
            (f"{p['precip']}", ""),
        )


class ForecastScreen(Screen):
    def compose(self) -> ComposeResult:
        header = Header(show_clock=True)
        header.time_format = get_time_format()
        yield header
        with Vertical(id="forecast-screen-content"):
            with Center(id="forecast-loading-container"):
                yield LoadingIndicator(id="forecast-loading")
            yield ScrollableContainer(id="forecast_container")
        yield Footer()

    def on_mount(self) -> None:
        settings = get_settings()
        self.current_use_ip = settings.get("use_ip", True)
        self.current_zip_code = settings.get("zip_code", "")
        self.temperature_unit = get_temperature_unit()
        self.fetch_forecast_data()

    @work(thread=True, exclusive=True)
    def fetch_forecast_data(self) -> None:
        """Fetch forecast data in a background thread."""
        self.app.call_from_thread(self.set_loading, True)

        self.lat, self.lon, self.country = get_app_coordinates()
        write_log(f"Fetching forecast for {self.lat}, {self.lon} ({self.country})")

        forecast_data = get_numerical_forecast(self.lat, self.lon)

        if forecast_data:
            write_log(f"Successfully fetched {len(forecast_data)} forecast periods.")
        else:
            write_log("Forecast data fetch returned empty result.")

        self.app.call_from_thread(self.update_forecast_ui, forecast_data)

    def set_loading(self, loading: bool) -> None:
        self.query_one("#forecast-loading-container").display = loading

    def update_forecast_ui(self, forecast_data: list) -> None:
        """Update the UI with new forecast data."""
        self.set_loading(False)
        container = self.query_one("#forecast_container", ScrollableContainer)
        container.display = True

        # Clear existing widgets
        container.query(ForecastWidget).remove()
        container.query(Label).remove()

        # Create new widgets
        forecast_widgets = [
            ForecastWidget(period, classes="forecast_item") for period in forecast_data
        ]

        if forecast_widgets:
            container.mount(*forecast_widgets)
        else:
            container.mount(Label("Forecast data unavailable.", id="no-forecast-label"))

    def on_screen_resume(self) -> None:
        """Check for settings changes and refresh if necessary."""
        settings = get_settings()
        new_use_ip = settings.get("use_ip", True)
        new_zip_code = settings.get("zip_code", "")
        new_temp_unit = get_temperature_unit()

        # Update header format
        self.query_one(Header).time_format = get_time_format()

        # If location changed, re-fetch everything
        if new_use_ip != self.current_use_ip or new_zip_code != self.current_zip_code:
            self.current_use_ip = new_use_ip
            self.current_zip_code = new_zip_code
            self.fetch_forecast_data()
        # If only temperature unit changed, just refresh existing widgets
        elif new_temp_unit != self.temperature_unit:
            self.temperature_unit = new_temp_unit
            for widget in self.query(ForecastWidget):
                widget.refresh()


class RadarScreen(Screen):
    """The forecast and radar map screen."""

    BINDINGS = [
        Binding("space", "toggle_pause", "Pause/Resume", show=False),
    ]

    def compose(self) -> ComposeResult:
        header = Header(show_clock=True)
        header.time_format = get_time_format()
        yield header
        yield LoadingIndicator(id="loading")
        with Horizontal(id="radar-container"):
            # ALERTS & FORECAST Panel
            with Vertical(id="alert-panel"):
                # Alert Section (Hidden if no alerts)
                with Vertical(id="alerts-section"):
                    yield Label("Weather Alerts", id="alert-header")
                    yield Static("", id="alert-content")

                # Today's Forecast Section (Always visible)
                with Vertical(id="forecast-section"):
                    yield Label("Today's Forecast", id="forecast-header")
                    yield Static("", id="latest-forecast")

            # MAP w/ LEGEND Panel
            with Vertical(id="map-panel"):
                yield Static(MICHIGAN_MAP_PLACEHOLDER, id="map-art")

                # The Frame Counter (What your timer is updating)
                yield Label("[ ]", id="legend-label")

            # The New Color Legend
            with Vertical(id="legend-container"):
                yield Label("Mist/Light", classes="legend-swatch swatch-snow")
                yield Label("Light Rain", classes="legend-swatch swatch-light")
                yield Label("Mod Rain", classes="legend-swatch swatch-mod")
                yield Label("Heavy Rain", classes="legend-swatch swatch-heavy")
                yield Label("Hail/Extreme", classes="legend-swatch swatch-hail")
        yield Footer()

    def on_mount(self) -> None:
        self.frames = []
        self.current_frame_index = 0
        self.animation_timer = None
        self.is_paused = False

        settings = get_settings()

        self.query_one("#loading").display = True
        self.query_one("#radar-container").display = False

        self.lat, self.lon, self.country = None, None, None
        self.current_use_ip = settings.get("use_ip", True)
        self.current_zip_code = settings.get("zip_code", "")
        self.current_quality = get_radar_quality()
        self.current_profile = settings.get("radar_profile", "Balanced")
        self.current_speed = settings.get("animation_speed", "Normal")
        self.temperature_unit = get_temperature_unit()
        self.time_format = get_time_format()

        self.fetch_all_data()

    def on_screen_resume(self) -> None:
        """Called automatically every time the screen becomes active again."""
        settings = get_settings()

        new_use_ip = settings.get("use_ip", True)
        new_zip_code = settings.get("zip_code", "")
        new_quality = settings.get("radar_quality", "High-Res")
        new_profile = settings.get("radar_profile", "Balanced (1 hr)")
        new_speed = settings.get("animation_speed", "Normal")
        new_temperature = "C" if settings.get("temperature") == "Celsius" else "F"
        new_time_format = (
            "%H:%M:%S" if settings.get("time_format") == "24 hour" else "%I:%M %p"
        )

        if new_temperature != self.temperature_unit:
            self.temperature_unit = new_temperature
            if hasattr(self, "forecast_data") and self.forecast_data:
                p = self.forecast_data[0]
                temp = convert_temp(p["temp"], self.temperature_unit)
                forecast_text = Text.assemble(
                    (f"{p['time']}\n", "bold underline"),
                    (f"{temp}°{self.temperature_unit}\n", "bold yellow"),
                    (f"{p['short_forecast']}\n\n", "italic"),
                    ("Wind: ", "dim"),
                    (f"{p['wind']}\n", ""),
                    ("Precip: ", "dim"),
                    (f"{p['precip']}\n", ""),
                )
                self.query_one("#latest-forecast").update(forecast_text)

        if new_time_format != self.time_format:
            self.time_format = new_time_format
            self.query_one(Header).time_format = new_time_format

        ip_changed = new_use_ip != self.current_use_ip
        zip_changed = new_zip_code != self.current_zip_code
        quality_changed = new_quality != self.current_quality
        profile_changed = new_profile != self.current_profile
        speed_changed = new_speed != self.current_speed

        if (
            ip_changed
            or zip_changed
            or quality_changed
            or profile_changed
            or speed_changed
        ):
            self.current_use_ip = new_use_ip
            self.current_zip_code = new_zip_code
            self.current_quality = new_quality
            self.current_profile = new_profile
            self.current_speed = new_speed
            self.current_frame_index = 0  # Reset counter to prevent IndexError

            if self.animation_timer:
                self.animation_timer.stop()
                self.animation_timer = None

            self.query_one("#loading").display = True
            self.query_one("#radar-container").display = False

            self.fetch_all_data()

    @work(
        thread=True, exclusive=True
    )  # exclusive=True prevents duplicate tasks from piling up
    def fetch_all_data(self) -> None:
        """Fetches coordinates, then fetches all API data simultaneously."""
        try:
            self.lat, self.lon, self.country = get_app_coordinates()
            write_log(
                f"Fetching radar and alerts for {self.lat}, {self.lon} ({self.country})"
            )

            # 2. Fetch the rest of the data concurrently (at the same time!)
            with concurrent.futures.ThreadPoolExecutor() as executor:
                num_f, interval = get_radar_profile()
                # Launch all three network requests simultaneously
                future_frames = executor.submit(
                    get_radar_frames,
                    MICHIGAN_MAP_PLACEHOLDER,
                    num_frames=num_f,
                    highlight_lat=self.lat,
                    highlight_lon=self.lon,
                    quality=get_radar_quality(),
                    interval_mins=interval,
                )
                future_alerts = executor.submit(get_alerts, self.lat, self.lon)
                future_forecast = executor.submit(
                    get_numerical_forecast, self.lat, self.lon
                )

                # Wait for them all to finish and grab their results
                self.frames = future_frames.result()
                self.alerts = future_alerts.result()
                self.forecast_data = future_forecast.result()
                write_log(
                    f"Successfully fetched {len(self.frames)} radar frames and {len(self.alerts.get('features', []))} alerts."
                )
        except Exception as e:
            write_log(f"Error fetching data: {e}")
            self.frames = []
            self.alerts = {"features": []}
            self.forecast_data = []

        # 3. Once all data is fetched, start the animation loop on the main UI thread
        self.app.call_from_thread(self.start_animation)

    def start_animation(self) -> None:
        # Hide loading, show the full dashboard container
        self.query_one("#loading").display = False
        self.query_one("#radar-container").display = True

        # Update alerts

        alert_section = self.query_one("#alerts-section")
        if hasattr(self, "alerts") and self.alerts.get("features"):
            features = self.alerts["features"]
            if features:
                alert_section.display = True
                alert = features[0]["properties"]
                alert_text = Text.assemble(
                    (f"{alert.get('headline', 'Weather Alert')}\n", "bold red"),
                    (f"{alert.get('description', 'No description available.')}", ""),
                )
                self.query_one("#alert-content").update(alert_text)
            else:
                alert_section.display = False
        else:
            alert_section.display = False

        # Update forecast
        if hasattr(self, "forecast_data") and self.forecast_data:
            p = self.forecast_data[0]
            unit = get_temperature_unit()
            temp_val = convert_temp(p["temp"], unit)
            temp_color = get_temp_color(p["temp"])

            forecast_text = Text.assemble(
                (f"{p['time']}\n", "bold underline"),
                (f"{temp_val}°{unit}\n", f"bold {temp_color}"),
                (f"{p['short_forecast']}\n\n", "italic"),
                ("Wind:  ", "dim"),
                (f"{p['wind']}\n", ""),
                ("Precip: ", "dim"),
                (f"{p['precip']}\n", ""),
            )
            self.query_one("#latest-forecast").update(forecast_text)
        else:
            self.query_one("#latest-forecast").update("Forecast unavailable")

        if not self.frames:
            self.query_one("#map-art", Static).update("Failed to load radar.")
            # Ensure container is still shown so user can see alerts/forecast
            self.query_one("#loading").display = False
            self.query_one("#radar-container").display = True
            return

        # Update first frame immediately before showing
        self.query_one("#map-art", Static).update(self.frames[0])
        self.query_one("#loading").display = False
        self.query_one("#map-art").display = True

        now = datetime.now()
        # Offset by 10 mins to match the API buffer and align to 5-min increments safely
        offset_now = now - timedelta(minutes=10)
        self.base_time = offset_now.replace(
            minute=(offset_now.minute // 5) * 5, second=0, microsecond=0
        )

        # Set an interval to update the map based on user speed preference
        speed = get_animation_speed()
        self.animation_timer = self.set_interval(speed, self.update_frame)

    def update_frame(self) -> None:
        if self.is_paused:
            return

        if self.frames:
            # Update the static widget with the current Rich Text frame
            map_widget = self.query_one("#map-art", Static)
            map_widget.update(self.frames[self.current_frame_index])

            frames_from_newest = (len(self.frames) - 1) - self.current_frame_index
            frame_time = self.base_time - timedelta(minutes=frames_from_newest * 5)

            # Format time based on user preference
            time_format = get_time_format()
            if "%H" in time_format:
                time_str = frame_time.strftime("%H:%M")
            else:
                time_str = frame_time.strftime("%I:%M %p").lstrip("0")

            # Update the legend with the time!
            legend = self.query_one("#legend-label", Label)
            legend.update(f"[ {time_str} ]")

            # Move to the next frame, loop back to 0 if at the end
            self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)

    def action_toggle_pause(self) -> None:
        """Pause/Resume the radar animation with the space bar."""
        if self.animation_timer:
            self.is_paused = not self.is_paused
            if self.is_paused:
                self.animation_timer.pause()
                self.query_one("#legend-label", Label).update("[ PAUSED ]")
            else:
                self.animation_timer.resume()
                # Force an immediate update so the user sees it resume instantly
                self.update_frame()
                # UI will update on next timer tick


def save_settings(settings):
    """Save settings to the centralized settings file."""
    try:
        from .weather_api import SETTINGS_FILE
    except (ImportError, ValueError):
        from weather_api import SETTINGS_FILE

    write_log(f"Updating settings: {settings}")
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)
    # Clear caches
    get_settings.cache_clear()


class SettingsScreen(Screen):
    """The configuration settings screen."""

    def compose(self) -> ComposeResult:
        header = Header(show_clock=True)
        header.time_format = get_time_format()
        yield header
        with Horizontal(id="settings-container"):
            with Vertical(classes="settings-box"):
                yield Label("Temperature units", classes="settings-title")
                with RadioSet(id="temp-format"):
                    yield RadioButton("Fahrenheit", value=True)
                    yield RadioButton("Celsius")

                yield Label("Time Format", classes="settings-title")
                with RadioSet(id="time-format"):
                    yield RadioButton("12 hour", value=True)
                    yield RadioButton("24 hour")

                yield Label("Location Method", classes="settings-title")
                with RadioSet(id="location-method"):
                    yield RadioButton("Use IP", id="use-ip-radio")
                    yield RadioButton("Zip Code", id="zip-code-radio")

                with Vertical(id="zip-code-group"):
                    yield Label("Zip Code Entry", id="zip-label")
                    yield Input(placeholder="Zip Code", id="zip-code-input")
                    yield Button("Save Zip Code", id="save-zip-btn")

            with Vertical(classes="settings-box"):
                yield Label("Radar Quality", classes="settings-title")
                with RadioSet(id="radar-quality"):
                    yield RadioButton("High-Res", value=True)
                    yield RadioButton("Standard")

                yield Label("Radar History", classes="settings-title")
                with RadioSet(id="radar-profile"):
                    yield RadioButton("Lite (30 min)")
                    yield RadioButton("Balanced (1 hr)", value=True)
                    yield RadioButton("Deep (2 hr)")

                yield Label("Animation Speed", classes="settings-title")
                with RadioSet(id="animation-speed"):
                    yield RadioButton("Fast")
                    yield RadioButton("Normal", value=True)
                    yield RadioButton("Slow")
            yield Footer()

    def on_mount(self) -> None:
        # Load settings from file
        settings = get_settings()

        # Set temperature
        temp_radio = self.query_one("#temp-format", RadioSet)
        temp_value = settings.get("temperature", "Fahrenheit")
        for radio in temp_radio.children:
            if radio.label.plain == temp_value:
                radio.value = True
                break

        # Set radar quality
        quality_radio = self.query_one("#radar-quality", RadioSet)
        quality_value = settings.get("radar_quality", "High-Res")
        for radio in quality_radio.children:
            if radio.label.plain == quality_value:
                radio.value = True
                break

        # Set radar profile
        profile_radio = self.query_one("#radar-profile", RadioSet)
        profile_value = settings.get("radar_profile", "Balanced (1 hr)")
        for radio in profile_radio.children:
            if radio.label.plain == profile_value:
                radio.value = True
                break

        # Set animation speed
        speed_radio = self.query_one("#animation-speed", RadioSet)
        speed_value = settings.get("animation_speed", "Normal")
        for radio in speed_radio.children:
            if radio.label.plain == speed_value:
                radio.value = True
                break

        # Set time format
        time_radio = self.query_one("#time-format", RadioSet)
        time_value = settings.get("time_format", "12 hour")
        for radio in time_radio.children:
            if radio.label.plain == time_value:
                radio.value = True
                break

        # Set location method
        use_ip = settings.get("use_ip", True)
        if use_ip:
            self.query_one("#use-ip-radio", RadioButton).value = True
        else:
            self.query_one("#zip-code-radio", RadioButton).value = True

        # Enable/Disable zip code input
        self.update_zip_input_state(use_ip)

        if "zip_code" in settings:
            self.query_one("#zip-code-input", Input).value = settings["zip_code"]

    def update_zip_input_state(self, use_ip: bool) -> None:
        self.query_one("#zip-code-input", Input).disabled = use_ip
        self.query_one("#save-zip-btn", Button).disabled = use_ip
        # Toggle entire group visibility
        self.query_one("#zip-code-group").display = not use_ip

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        # Save settings
        settings = get_settings()

        if event.radio_set.id == "temp-format":
            for radio in event.radio_set.children:
                if radio.value:
                    settings["temperature"] = radio.label.plain
                    break
        elif event.radio_set.id == "radar-quality":
            for radio in event.radio_set.children:
                if radio.value:
                    settings["radar_quality"] = radio.label.plain
                    break
        elif event.radio_set.id == "radar-profile":
            for radio in event.radio_set.children:
                if radio.value:
                    settings["radar_profile"] = radio.label.plain
                    break
        elif event.radio_set.id == "animation-speed":
            for radio in event.radio_set.children:
                if radio.value:
                    settings["animation_speed"] = radio.label.plain
                    break
        elif event.radio_set.id == "time-format":
            for radio in event.radio_set.children:
                if radio.value:
                    settings["time_format"] = radio.label.plain
                    break
            # Immediately update the header clock format on this screen
            self.query_one(Header).time_format = get_time_format()
        elif event.radio_set.id == "location-method":
            use_ip = self.query_one("#use-ip-radio", RadioButton).value
            settings["use_ip"] = use_ip
            self.update_zip_input_state(use_ip)

        save_settings(settings)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-zip-btn":
            zip_code = self.query_one("#zip-code-input", Input).value
            settings = get_settings()
            settings["zip_code"] = zip_code
            save_settings(settings)


class LogScreen(Screen):
    def compose(self) -> ComposeResult:
        with Horizontal(id="log-container"):
            header = Header(show_clock=True)
            header.time_format = get_time_format()
            yield header
            yield Log()
            yield Footer()

    def on_mount(self) -> None:
        try:
            from .weather_api import LOG_FILE
        except (ImportError, ValueError):
            from weather_api import LOG_FILE

        log = self.query_one(Log)
        log.clear()

        self.last_read_position = 0
        try:
            with open(LOG_FILE, "r") as f:
                f.seek(self.last_read_position)
                for line in f:
                    log.write_line(line.rstrip())
                self.last_read_position = f.tell()
        except FileNotFoundError:
            log.write_line(f"Log file not found at {LOG_FILE}")

        self.set_interval(1, self.update_log_content)

    def on_screen_resume(self) -> None:
        """Update header format when returning to log screen."""
        self.query_one(Header).time_format = get_time_format()

    def update_log_content(self) -> None:
        try:
            from .weather_api import LOG_FILE
        except (ImportError, ValueError):
            from weather_api import LOG_FILE

        log = self.query_one(Log)
        try:
            with open(LOG_FILE, "r") as f:
                f.seek(self.last_read_position)
                new_content = f.read()
                if new_content:
                    for line in new_content.splitlines():
                        log.write_line(line)
                    self.last_read_position = f.tell()
                    log.scroll_end(animate=False)
        except FileNotFoundError:
            pass


class TermRad(App):
    """A terminal radar and weather forecasting app."""

    CSS_PATH = os.path.join(os.path.dirname(__file__), "TermRadStyles.tcss")

    BINDINGS = [
        Binding("h", "home", "Home"),
        Binding("r", "radar", "Radar"),
        Binding("f", "forecast", "Forecast"),
        Binding("s", "settings", "Settings"),
        Binding("ctrl+l", "log", "Log"),
        Binding("ctrl+p", "palette", "Palette"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, public_mode=False, **kwargs):
        super().__init__(**kwargs)
        self.public_mode = public_mode

    def on_mount(self) -> None:
        self.register_theme(termrad_theme)

        # Load saved theme from settings
        settings = get_settings()
        saved_theme = settings.get("theme", "termrad")

        # Update theme colors
        self.app.theme_variables["text"] = "#FFFFFF"
        self.app.theme_variables["foreground"] = "#FFFFFF"
        self.app.theme_variables["panel"] = "#333333"

        try:
            self.theme = saved_theme
        except Exception:
            self.theme = "termrad"

        self.install_screen(HomeScreen(), name="home")
        self.install_screen(RadarScreen(), name="radar")
        self.install_screen(ForecastScreen(), name="forecast")
        self.install_screen(SettingsScreen(), name="settings")
        self.install_screen(LogScreen(), name="log")

        self.push_screen("home")

        # Start pre-fetching weather data immediately in the background
        self.pre_fetch_data(settings)

    @work(thread=True, exclusive=True)
    def pre_fetch_data(self, settings: dict) -> None:
        """Fetch all weather data in the background so screens load instantly."""
        write_log("Starting background data pre-fetch...")
        try:
            # Get current preferences directly from passed settings
            use_ip = settings.get("use_ip", True)
            zip_code = settings.get("zip_code", "")

            # 1. Resolve coordinates
            if use_ip in [True, "true", "True"]:
                lat, lon, _ = get_coords_auto()
            elif zip_code:
                lat, lon, _ = get_coords_manual(zip_code)
            else:
                lat, lon, _ = None, None, None

            if lat and lon:
                # 2. Fire off data fetches (cached via @lru_cache)
                get_numerical_forecast(lat, lon)

                # Use settings to get profile/quality without re-reading file
                profile = settings.get("radar_profile", "Balanced (1 hr)")
                profiles = {
                    "Lite (30 min)": (7, 5),
                    "Balanced (1 hr)": (13, 5),
                    "Deep (2 hr)": (25, 5),
                }
                num_f, interval = profiles.get(profile, (13, 5))
                quality = settings.get("radar_quality", "High-Res")

                get_radar_frames(
                    MICHIGAN_MAP_PLACEHOLDER,
                    num_frames=num_f,
                    highlight_lat=lat,
                    highlight_lon=lon,
                    quality=quality,
                    interval_mins=interval,
                )
                get_alerts(lat, lon)
                write_log("Background pre-fetch complete.")
        except Exception as e:
            write_log(f"Background pre-fetch failed: {e}")

    # Action methods mapped to BINDINGS
    def action_quit(self) -> None:
        write_log("Exiting...")
        # Save current theme preference
        settings = get_settings()
        settings["theme"] = self.theme
        save_settings(settings)
        self.exit()

    def action_home(self) -> None:
        write_log("Switching to home screen...")
        self.switch_screen("home")

    def action_radar(self) -> None:
        write_log("Switching to radar screen...")
        self.switch_screen("radar")

    def action_forecast(self) -> None:
        write_log("Switching to forecast screen...")
        self.switch_screen("forecast")

    def action_settings(self) -> None:
        if self.public_mode:
            return
        write_log("Switching to settings screen...")
        self.switch_screen("settings")

    def action_log(self) -> None:
        if self.public_mode:
            return
        write_log("Switching to log screen...")
        self.switch_screen("log")

    def action_palette(self) -> None:
        """Action for switching the color palette."""
        self.app.action_toggle_dark()


def main():
    parser = argparse.ArgumentParser(description="TermRad Terminal Weather App")
    parser.add_argument(
        "--public",
        action="store_true",
        help="Run in public mode (disables settings and logs)",
    )
    args = parser.parse_args()

    if args.public:
        # Filter bindings at the class level before instantiation
        # This is the most reliable way to remove them from the footer
        TermRad.BINDINGS = [
            b
            for b in TermRad.BINDINGS
            if (isinstance(b, Binding) and b.key not in ("s", "ctrl+l"))
            or (isinstance(b, tuple) and b[0] not in ("s", "ctrl+l"))
        ]

    app = TermRad(public_mode=args.public)
    app.run()


if __name__ == "__main__":
    main()
