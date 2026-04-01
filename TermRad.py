from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Label, Static, Switch, RadioSet, RadioButton
from textual.containers import Container, Horizontal, Vertical, Center
from textual import work
from radar_animator import get_radar_frames

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
                yield Switch(value=True)
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

class RadarScreen(Screen):
    """The forecast and radar map screen."""
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="radar-container"):

            # ALERTS Panel
            with Vertical(id="alert-panel"):
                yield Label("URGENT WEATHER ALERT", id="alert-title")
                yield Label(
                    "Areas of dense fog and freezing fog will continue to develop across "
                    "portions of northern Michigan through the morning hours. Visibilities "
                    "of one half mile or less have been observed in localized areas..."
                )

            # MAP w/ LEGEND Panel
            with Vertical(id="map-panel"):
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
        yield Footer()

    def on_mount(self) -> None:
        self.frames = []
        self.current_frame_index = 0
        self.animation_timer = None
        
        self.fetch_radar_data()

    @work(thread=True) # Runs in a background thread
    def fetch_radar_data(self) -> None:
        # Fetch the frames using our new function
        self.frames = get_radar_frames(MICHIGAN_MAP_PLACEHOLDER, num_frames=5)
        
        # Once data is fetched, start the animation loop on the main UI thread
        self.app.call_from_thread(self.start_animation)

    def start_animation(self) -> None:
        if not self.frames:
            self.query_one("#map-art", Static).update("Failed to load radar.")
            return
            
        # Set an interval to update the map every 0.5 seconds
        self.animation_timer = self.set_interval(0.5, self.update_frame)

    def update_frame(self) -> None:
        if self.frames:
            # Update the static widget with the current Rich Text frame
            map_widget = self.query_one("#map-art", Static)
            map_widget.update(self.frames[self.current_frame_index])
            
            # Update the legend to prove the timer is running! --> Will change later
            legend = self.query_one("#legend-label", Label)
            legend.update(f"LEGEND  [ Frame {self.current_frame_index + 1} of {len(self.frames)} ]")
            
            # Move to the next frame, loop back to 0 if at the end
            self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)

class SettingsScreen(Screen):
    """The configuration settings screen."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="settings-container"):
            with Vertical(classes="settings-box"):
                yield Label("Temperature units", classes="settings-title")
                with RadioSet():
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

class TermRad(App):
    """A terminal radar and weather forecasting app."""
    CSS_PATH = "TermRadStyles.tcss"

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"), 
        ("h", "home", "Home"), 
        ("r", "radar", "Radar"), 
        ("f", "radar", "Forecast"), # Mapping 'f' to radar screen to match screenshots
        ("s", "settings", "Settings"), 
        ("ctrl+s", "screenshot", "Screenshot"), 
        ("ctrl+a", "maximize", "Maximize")
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
