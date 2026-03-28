from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Label, Static, Switch, RadioSet, RadioButton
from textual.containers import Container, Horizontal, Vertical, Center

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

            # ALERTS Placeholder
            with Vertical(id="alert-panel"):
                yield Label("URGENT WEATHER ALERT", id="alert-title")
                yield Label(
                    "Areas of dense fog and freezing fog will continue to develop across "
                    "portions of northern Michigan through the morning hours. Visibilities "
                    "of one half mile or less have been observed in localized areas. Untreated "
                    "roadways may be slick in spots due to patchy areas of freezing fog. If you "
                    "encounter dense fog while traveling, use low beam headlights and increase "
                    "following distance."
                )

            # MAP w/ LEGEND
            with Vertical(id="map-panel"):
                yield Static(MICHIGAN_MAP_PLACEHOLDER, id="map-art")
                yield Label("LEGEND  [ ]", id="legend-label") # Placeholder for legend
        yield Footer()

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
