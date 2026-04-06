from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Label, Static, Switch, RadioSet, RadioButton, LoadingIndicator
from textual.containers import Container, Horizontal, Vertical, Center
from textual import work
import json
from radar_animator import get_radar_frames
from weather_api import get_alerts, get_coords_auto
from datetime import datetime, timedelta

with open('logo.txt', 'r') as file_handle:
    ASCII_ART = file_handle.read()


with open('mich.txt', 'r') as file_handle:
    MICHIGAN_MAP_PLACEHOLDER = file_handle.read()

class HomeScreen(Screen):
    """The main menu screen."""

    BINDINGS = [
        ("1", "go_forecast", "Michigan Forecast"),
        ("2", "go_settings", "Config Settings")
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="home-container"):
            with Center(): # <--- This container mathematically forces the block to center
                yield Static(ASCII_ART, id="title-art")
            with Center():
                yield Button("1. Michigan Forecast", id="btn-forecast", variant="default", classes="menu-button")
            with Center():
                yield Button("2. Config Settings", id="btn-settings", variant="default", classes="menu-button")
            with Horizontal(id="ip-switch-container"):
                yield Label("Use IP:")
                yield Switch(value=True, id="use-ip")                
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-forecast":
            self.app.switch_screen("radar")
        elif event.button.id == "btn-settings":
            self.app.switch_screen("settings")

    # --- Keyboard Action Handlers ---
    def action_go_forecast(self) -> None:
        self.app.switch_screen("radar")
        
    def action_go_settings(self) -> None:
        self.app.switch_screen("settings")

    def on_mount(self) -> None:
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
        except FileNotFoundError:
            settings = {}
        
        use_ip = settings.get("use_ip", True)
        self.query_one("#use-ip", Switch).value = use_ip

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "use-ip":
            try:
                with open("settings.json", "r") as f:
                    settings = json.load(f)
            except FileNotFoundError:
                settings = {}
            
            settings["use_ip"] = event.value
            
            with open("settings.json", "w") as f:
                json.dump(settings, f)

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

            # MAP w/ LEGEND Panel
            with Vertical(id="map-panel"):
                yield LoadingIndicator(id="loading")
                yield Static(MICHIGAN_MAP_PLACEHOLDER, id="map-art")
                
                # The Frame Counter (What your timer is updating)
                yield Label("FRAME  [ ]", id="legend-label") 
                
                # The New Color Legend
                with Horizontal(id="legend-container"):
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
        
        # Show loading, hide map initially
        self.query_one("#loading").display = True
        self.query_one("#map-art").display = False
        
        self.lat, self.lon, self.country = None, None, None
        
        # Get coordinates
        use_ip_setting = settings.get("use_ip", True)
        self.current_use_ip = use_ip_setting # <-- ADD THIS LINE TO TRACK IT
        
        if use_ip_setting in [True, "true", "True"]:
            self.lat, self.lon, self.country = get_coords_auto()
        
        self.fetch_radar_data(self.lat, self.lon)

    def on_screen_resume(self) -> None:
        """Called automatically every time the screen becomes active again."""
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
        except FileNotFoundError:
            settings = {}
            
        new_use_ip = settings.get("use_ip", True)
        
        # If the IP setting changed while we were away, we MUST re-render
        if new_use_ip != self.current_use_ip:
            self.current_use_ip = new_use_ip
            
            # Stop the old animation
            if self.animation_timer:
                self.animation_timer.stop()
                
            # Show loading indicator again
            self.query_one("#loading").display = True
            self.query_one("#map-art").display = False
            
            # Get new coordinates based on the new setting
            if new_use_ip in [True, "true", "True"]:
                self.lat, self.lon, self.country = get_coords_auto()
            else:
                self.lat, self.lon, self.country = None, None, None
                
            # Fetch new data!
            self.fetch_radar_data(self.lat, self.lon)

    @work(thread=True) # Runs in a background thread
    def fetch_radar_data(self, lat, lon) -> None:
        self.frames = get_radar_frames(MICHIGAN_MAP_PLACEHOLDER, num_frames=5, highlight_lat=lat, highlight_lon=lon)
        
        self.alerts = get_alerts(lat, lon)
        
        # Once data is fetched, start the animation loop on the main UI thread
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

class TermRad(App):
    """A terminal radar and weather forecasting app."""
    CSS_PATH = "TermRadStyles.tcss"

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("h", "home", "Home"), 
        ("r", "radar", "Radar"), 
        ("f", "radar", "Forecast"), # Mapping 'f' to radar screen to match screenshots
        ("s", "settings", "Settings"), 
        #("ctrl+s", "screenshot", "Screenshot"), 
        #("ctrl+a", "maximize", "Maximize")
    ]

    def on_mount(self) -> None:
        # Register screens
        self.install_screen(HomeScreen(), name="home")
        self.install_screen(RadarScreen(), name="radar")
        self.install_screen(SettingsScreen(), name="settings")

        # Start on the home screen
        self.push_screen("home")

    # Action methods mapped to BINDINGS
    def action_quit(self) -> None:
        self.exit()
    
    def action_home(self) -> None:
        self.switch_screen("home")
        
    def action_radar(self) -> None:
        self.switch_screen("radar")
        
    def action_settings(self) -> None:
        self.switch_screen("settings")

if __name__ == "__main__":
    app = TermRad()
    app.run()
