from textual.app import App, ComposeResult, Binding
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Label, Static, Switch, RadioSet, RadioButton, LoadingIndicator, Log, Input
from textual.containers import Horizontal, Vertical, Center, ScrollableContainer
from textual.theme import Theme
from textual import work
import json
from radar_animator import get_radar_frames
from weather_api import get_alerts, get_coords_auto, write_log, get_numerical_forecast, get_coords_manual
from datetime import datetime, timedelta
import concurrent.futures

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

with open('logo.txt', 'r') as file_handle:
    ASCII_ART = file_handle.read()

@lru_cache(maxsize=1)
def get_temperature_unit():
    """Load the temperature unit preference from settings.json."""
    try:
        with open("settings.json", "r") as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}
    
    temp_pref = settings.get("temperature", "Fahrenheit")
    return "C" if temp_pref == "Celsius" else "F"


with open('mich.txt', 'r') as file_handle:
    MICHIGAN_MAP_PLACEHOLDER = file_handle.read()

class HomeScreen(Screen):
    """The main menu screen."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="home-container"):
            with Center(): # <--- This container mathematically forces the block to center
                yield Static(ASCII_ART, id="title-art")
            with Center():
                yield Button("1. Michigan Radar", id="btn-radar", variant="default", classes="menu-button")
            with Center():
                yield Button("2. Michigan Forecast", id="btn-forecast", variant="default", classes="menu-button")
            with Center():
                yield Button("3. Config Settings", id="btn-settings", variant="default", classes="menu-button")
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
        

class ForecastWidget(Static):
    def __init__(self, period: dict, **kwargs):
        super().__init__(**kwargs)
        self.period = period

    def render(self) -> str:
        p = self.period
        unit = get_temperature_unit()
        if unit == "C":
            temp_c = round((p['temp'] - 32) * (5.0 / 9.0), 1)
            return f"[bold]{p['time']}[/bold]\n{temp_c}°{unit}\n{p['short_forecast']}\nWind: {p['wind']}\nPrecip: {p['precip']}"
        else:
            return f"[bold]{p['time']}[/bold]\n{p['temp']}°{unit}\n{p['short_forecast']}\nWind: {p['wind']}\nPrecip: {p['precip']}"
    
class ForecastScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ScrollableContainer(id="forecast_container")
        yield Footer()

    def on_mount(self) -> None:
        self.load_and_fetch()

    def load_and_fetch(self) -> None:
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
        except FileNotFoundError:
            settings = {}
        
        use_ip = settings.get("use_ip", True)
        zip_code = settings.get("zip_code", "")
        
        if use_ip in [True, "true", "True"]:
            self.lat, self.lon, self.country = get_coords_auto()
        elif zip_code and zip_code != "":
            self.lat, self.lon, self.country = get_coords_manual(zip_code)
        else:
            self.lat, self.lon, self.country = None, None, None

        forecast_data = get_numerical_forecast(self.lat, self.lon)  
        self.temperature_unit = get_temperature_unit()

        # Clear existing widgets
        container = self.query_one("#forecast_container", ScrollableContainer)
        for widget in container.query(ForecastWidget):
            widget.remove()

        # dynamically create forecast widget per recieved data 
        forecast_widgets = [
                ForecastWidget(period, id=f"forecast{i}", classes="forecast_item")
                for i, period in enumerate(forecast_data)
        ]

        container.mount(*forecast_widgets)
    
    def on_screen_resume(self):
        # Re-fetch data if settings changed (simple way for now)
        self.load_and_fetch()
    
class RadarScreen(Screen):
    """The forecast and radar map screen."""
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="radar-container"):

            # ALERTS Panel
            with Vertical(id="alert-panel"):
                yield Label("Checking for weather alerts...", id="alert-title")
                yield Label(
                    id="alert-description"
                )
                yield Label("Latest Forecast:\n", id="forecast-title")
                yield Static("", id="latest-forecast")

            # MAP w/ LEGEND Panel
            with Vertical(id="map-panel"):
                yield LoadingIndicator(id="loading")
                yield Static(MICHIGAN_MAP_PLACEHOLDER, id="map-art")
                
                # The Frame Counter (What your timer is updating)
                yield Label("FRAME  [ ]", id="legend-label") 
                
            # The New Color Legend
            with Vertical(id="legend-container"):
                yield Label("Snow/Ice", classes="legend-swatch swatch-snow")
                yield Label("Light Rain", classes="legend-swatch swatch-light")
                yield Label("Mod Rain", classes="legend-swatch swatch-mod")
                yield Label("Heavy Rain", classes="legend-swatch swatch-heavy")
                yield Label("Hail/Extreme", classes="legend-swatch swatch-hail") 
                yield Label("Your Location", classes="legend-swatch swatch-location")                    
        yield Footer()        

    def on_mount(self) -> None:
        self.frames = []
        self.current_frame_index = 0
        self.animation_timer = None
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
        except FileNotFoundError:
            settings = {}
        
        self.query_one("#loading").display = True
        self.query_one("#map-art").display = False
        
        self.lat, self.lon, self.country = None, None, None
        
        self.current_use_ip = settings.get("use_ip", True)
        self.current_zip_code = settings.get("zip_code", "")
        self.temperature_unit = get_temperature_unit()
        
        self.fetch_all_data(self.current_use_ip, self.current_zip_code)

    def on_screen_resume(self) -> None:
        """Called automatically every time the screen becomes active again."""
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
        except FileNotFoundError:
            settings = {}
            
        new_use_ip = settings.get("use_ip", True)
        new_zip_code = settings.get("zip_code", "")
        new_temperature = get_temperature_unit()

        if new_temperature != self.temperature_unit:
            self.temperature_unit = new_temperature
            if hasattr(self, 'forecast_data') and self.forecast_data:
                period = self.forecast_data[0]
                temp = period['temp']
                if self.temperature_unit == "C":
                    temp = round((temp - 32) * (5.0 / 9.0), 1)
                forecast_text = f"[bold]{period['time']}[/bold]\n{temp}°{self.temperature_unit}\n{period['short_forecast']}\nWind: {period['wind']}\nPrecip: {period['precip']}"
                self.query_one("#latest-forecast").update(forecast_text) 

        ip_changed = new_use_ip != self.current_use_ip
        zip_changed = new_zip_code != self.current_zip_code
        
        if ip_changed or zip_changed:
            self.current_use_ip = new_use_ip
            self.current_zip_code = new_zip_code
            
            if self.animation_timer:
                self.animation_timer.stop()
                self.animation_timer = None
                
            self.query_one("#loading").display = True
            self.query_one("#map-art").display = False
                
            self.fetch_all_data(new_use_ip, new_zip_code)

    @work(thread=True, exclusive=True) # exclusive=True prevents duplicate tasks from piling up
    def fetch_all_data(self, use_ip, zip_code) -> None:
        """Fetches coordinates, then fetches all API data simultaneously."""
        try:
            if use_ip in [True, "true", "True"]:
                self.lat, self.lon, self.country = get_coords_auto()
            elif zip_code and zip_code != "":
                self.lat, self.lon, self.country = get_coords_manual(zip_code)
            else:
                self.lat, self.lon, self.country = None, None, None

            # 2. Fetch the rest of the data concurrently (at the same time!)
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Launch all three network requests simultaneously
                future_frames = executor.submit(get_radar_frames, MICHIGAN_MAP_PLACEHOLDER, num_frames=5, highlight_lat=self.lat, highlight_lon=self.lon)
                future_alerts = executor.submit(get_alerts, self.lat, self.lon)
                future_forecast = executor.submit(get_numerical_forecast, self.lat, self.lon)

                # Wait for them all to finish and grab their results
                self.frames = future_frames.result()
                self.alerts = future_alerts.result()
                self.forecast_data = future_forecast.result()
        except Exception as e:
            write_log(f"Error fetching data: {e}")
            self.frames = []
            self.alerts = {"features": []}
            self.forecast_data = []
            
        # 3. Once all data is fetched, start the animation loop on the main UI thread
        self.app.call_from_thread(self.start_animation)

    def start_animation(self) -> None:
        # Hide loading, show map
        self.query_one("#loading").display = False
        self.query_one("#map-art").display = True  
        
        # Update alerts
        if hasattr(self, 'alerts') and self.alerts.get("features"):
            features = self.alerts["features"]
            if features:
                alert = features[0]["properties"]
                self.query_one("#alert-title").update(alert.get("headline", "Weather Alert"))
                self.query_one("#alert-description").update(alert.get("description", "No description available."))
            else:
                self.query_one("#alert-title").update("No Active Alerts")
                self.query_one("#alert-description").update("")
        else:
            self.query_one("#alert-title").update("No Active Alerts")
            self.query_one("#alert-description").update("")
        
        # Update forecast
        if hasattr(self, 'forecast_data') and self.forecast_data:
            period = self.forecast_data[0]
            unit = get_temperature_unit()
            temp = period['temp']
            if unit == "C":
                temp = round((temp - 32) * (5.0 / 9.0), 1)
            forecast_text = f"[bold]{period['time']}[/bold]\n{temp}°{unit}\n{period['short_forecast']}\nWind: {period['wind']}\nPrecip: {period['precip']}"
            self.query_one("#latest-forecast").update(forecast_text)
        else:
            self.query_one("#latest-forecast").update("Forecast unavailable")
        
        if not self.frames:
            self.query_one("#map-art", Static).update("Failed to load radar.")
            return
            
        now = datetime.now()
        self.base_time = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)

        # Set an interval to update the map every 0.5 seconds
        self.animation_timer = self.set_interval(0.5, self.update_frame)

    def update_frame(self) -> None:
        if self.frames:
            # Update the static widget with the current Rich Text frame
            map_widget = self.query_one("#map-art", Static)
            map_widget.update(self.frames[self.current_frame_index])
            
            frames_from_newest = (len(self.frames) - 1) - self.current_frame_index
            frame_time = self.base_time - timedelta(minutes=frames_from_newest * 15)
            
            # Format to 12-hour time (e.g., "4:15 PM"). The lstrip("0") removes leading zeros.
            time_str = frame_time.strftime("%I:%M %p").lstrip("0")
            
            # Update the legend with the time!
            legend = self.query_one("#legend-label", Label)
            legend.update(f"LEGEND  [ {time_str} ]")
            
            # Move to the next frame, loop back to 0 if at the end
            self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)

class SettingsScreen(Screen):
    """The configuration settings screen."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="settings-container"):
            with Vertical(classes="settings-box"):
                yield Label("Temperature units", classes="settings-title")
                with RadioSet(id="temp-format"):
                    yield RadioButton("Fahrenheit", value=True)
                    yield RadioButton("Celsius")
                
                with Horizontal(id="ip-switch-container"):
                    yield Label("Use IP:")
                    # FIX 1: Remove the hardcoded value=True so it defaults to off
                    yield Switch(id="use-ip")  
                    
                yield Label("Enter Zip Code")
                yield Input(placeholder="Zip Code", id="zip-code-input")
                yield Button("Save Zip Code", id="save-zip-btn")
            
            with Vertical(classes="settings-box"):
                yield Label("Time and Date Format", classes="settings-title")
                with RadioSet(id="time-format"):
                    yield RadioButton("24 hour")
                    yield RadioButton("12 hour", value=True)
                with RadioSet(id="date-format"):
                    yield RadioButton("ISO Date")
                    yield RadioButton("Standard Date", value=True)
        yield Footer()

    def on_mount(self) -> None:
        # Load settings from file
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
        except FileNotFoundError:
            settings = {}
        
        # Set temperature
        temp_radio = self.query_one("#temp-format", RadioSet)
        temp_value = settings.get("temperature", "Fahrenheit")
        for radio in temp_radio.children:
            if radio.label.plain == temp_value:
                radio.value = True
                break
        
        # Set time format
        time_radio = self.query_one("#time-format", RadioSet)
        time_value = settings.get("time_format", "12 hour")
        for radio in time_radio.children:
            if radio.label.plain == time_value:
                radio.value = True
                break
        
        # Set date format
        date_radio = self.query_one("#date-format", RadioSet)
        date_value = settings.get("date_format", "Standard Date")
        for radio in date_radio.children:
            if radio.label.plain == date_value:
                radio.value = True
                break
        
        # FIX 2: Default this to False instead of True if there's no saved setting
        use_ip = settings.get("use_ip", False) 
        
        # FIX 3: Remove the 'not' so it matches the logic in on_switch_changed.
        # If use_ip is True, disabled becomes True.
        self.query_one("#zip-code-input", Input).disabled = use_ip
        self.query_one("#save-zip-btn", Button).disabled = use_ip
        self.query_one("#use-ip", Switch).value = use_ip


    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        # Save settings
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
        except FileNotFoundError:
            settings = {}
        
        # Get temperature
        temp_radio = self.query_one("#temp-format", RadioSet)
        for radio in temp_radio.children:
            if radio.value:
                settings["temperature"] = radio.label.plain
                break
        
        # Get time format
        time_radio = self.query_one("#time-format", RadioSet)
        for radio in time_radio.children:
            if radio.value:
                settings["time_format"] = radio.label.plain
                break
        
        # Get date format
        date_radio = self.query_one("#date-format", RadioSet)
        for radio in date_radio.children:
            if radio.value:
                settings["date_format"] = radio.label.plain
                break
        
        with open("settings.json", "w") as f:
            json.dump(settings, f)
        
        # Clear cache so the UI updates immediately
        get_temperature_unit.cache_clear()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "use-ip":
            # Save use_ip setting
            try:
                with open("settings.json", "r") as f:
                    settings = json.load(f)
            except FileNotFoundError:
                settings = {}
            
            settings["use_ip"] = event.value
            
            with open("settings.json", "w") as f:
                json.dump(settings, f)
            
        self.query_one("#zip-code-input", Input).disabled = event.value
        self.query_one("#save-zip-btn", Button).disabled = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-zip-btn":
            zip_code = self.query_one("#zip-code-input", Input).value

            try:
                with open("settings.json", "r") as f:
                    settings = json.load(f)
            except FileNotFoundError:
                settings = {}
            
            settings["zip_code"] = zip_code
            
            with open("settings.json", "w") as f:
                json.dump(settings, f)
            
class LogScreen(Screen):

    def compose(self) -> ComposeResult:
        with Horizontal(id="log-container"):
            yield Header(show_clock=True)
            yield Log()
            yield Footer()

    def on_mount(self) -> None:
        log = self.query_one(Log)
        log.clear()
        
        self.last_read_position = 0
        try:
            with open("TermRad.log", "r") as f:
                f.seek(self.last_read_position)
                for line in f:
                    log.write_line(line.rstrip())
                self.last_read_position = f.tell()
        except FileNotFoundError:
            log.write_line("TermRad.log not found. No logs to display.")

        self.set_interval(1, self.update_log_content)

    def update_log_content(self) -> None:
        log = self.query_one(Log)
        try:
            with open("TermRad.log", "r") as f:
                f.seek(self.last_read_position)
                new_content = f.read()
                if new_content:
                    for line in new_content.splitlines():
                        log.write_line(line)
                    self.last_read_position = f.tell()
        except FileNotFoundError:
            pass


class TermRad(App):
    """A terminal radar and weather forecasting app."""
    CSS_PATH = "TermRadStyles.tcss"

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("h", "home", "Home"), 
        ("r", "radar", "Radar"), 
        ("f", "forecast", "Forecast"), 
        ("ctrl+l", "log", "Log")
        # ("s", "settings", "Settings"), 
        #("ctrl+s", "screenshot", "Screenshot"), 
        #("ctrl+a", "maximize", "Maximize")
    ]
    

    def on_mount(self) -> None:
        self.register_theme(termrad_theme)
        self.theme = "termrad"

        self.install_screen(HomeScreen(), name="home")
        self.install_screen(RadarScreen(), name="radar")
        self.install_screen(ForecastScreen(), name="forecast")
        self.install_screen(SettingsScreen(), name="settings")
        self.install_screen(LogScreen(), name="log")

        self.push_screen("home")

    # Action methods mapped to BINDINGS
    def action_quit(self) -> None:
        write_log("Exiting...")
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
        write_log("Switching to settings screen...")
        self.switch_screen("settings")

    def action_log(self) -> None:
        write_log("Switching to log screen...")
        self.switch_screen("log")

if __name__ == "__main__":
    app = TermRad()
    app.run()
