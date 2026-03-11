from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Label


class TermRad(App):
    """A basic Textual app."""
    CSS_PATH = "TermRadStyles.tcss"

    
    # Define the widgets that compose the UI
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("Do you love Textual?", id="question")
        yield Button("Yes", id="yes", variant="primary")
        yield Button("No", id="no", variant="error")
        yield Footer()

    # def on_mount(self) -> None:
    #     self.screen.styles.background = "darkblue"

    # async def on_key(self) -> None:
    #     await self.mount(Welcome())
    #     self.query_one(Button).label = "YES!"

    BINDINGS = [("ctrl+q", "quit", "Quit"), ("h", "home", "Home"), ("r", "radar", "Radar"), ("f", "forecast", "Forecast"), ("s", "settings", "Settings"), ("ctrl+s", "screenshot", "Screenshot"), ("ctrl+a", "maximize", "Maximize")]

    def action_quit(self) -> None:
        self.exit()

if __name__ == "__main__":
    app = TermRad()
    app.run()
