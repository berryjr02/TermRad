from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Label, Static
from textual.screen import Screen
from textual.containers import Container, ScrollableContainer
from weather_api import get_numerical_forecast

class ForecastWidget(Static):
    def __init__(self, period: dict, **kwargs):
        super().__init__(**kwargs)
        self.period = period

    def render(self) -> str:
        p = self.period
        return f"[bold]{p['time']}[/bold]\n{p['temp']}°{p['unit']}\n{p['short_forecast']}\nWind: {p['wind']}\nPrecip: {p['precip']}"

class TermRad(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Pop screen")]

    #TermRad will not run with this code in the App class. I don't understand why
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ScrollableContainer(id="forecast_container")
        yield Footer()

    def on_mount(self) -> None:
        #this is hardcoded to flint right now for testing. 
        forecast_data = get_numerical_forecast(43.0125, -83.6875)

        #dynamically create forecast widget per recieved data 
        forecast_widgets = [
                ForecastWidget(period, id=f"forecast{i}", classes="forecast_item")
                for i, period in enumerate(forecast_data)
        ]

        container = self.query_one("#forecast_container", ScrollableContainer)
        container.mount(*forecast_widgets)
    
class TermRad(App):
    CSS_PATH = "TermRadStyles.tcss"
    SCREENS = {"termrad": TermRad}
    
    # async def on_key(self) -> None:
    #     await self.mount(Welcome())
    #     self.query_one(Button).label = "YES!"

    BINDINGS = [("ctrl+q", "quit", "Quit"), ("h", "home", "Home"), ("r", "radar", "Radar"), ("f", "push_screen('termrad')", "Forecast"), ("s", "settings", "Settings"), ("ctrl+s", "screenshot", "Screenshot"), ("ctrl+a", "maximize", "Maximize")]

    def action_quit(self) -> None:
        self.exit()

if __name__ == "__main__":
    app = TermRad()
    app.run()
