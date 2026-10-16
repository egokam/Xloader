from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from .window import MainWindow


class XloaderApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="com.egokam.Xloader")
        self.connect("activate", self.on_activate)

    def on_activate(self, _application: Gtk.Application) -> None:
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property(
                "gtk-interface-color-scheme",
                Gtk.InterfaceColorScheme.DARK,
            )

        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).parent / "assets" / "style.css"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

        window = MainWindow(self)
        window.present()


def main() -> None:
    app = XloaderApp()
    app.run(None)
