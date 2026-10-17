import os
from pathlib import Path
import sys

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from .window import MainWindow


class XloaderApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="com.egokam.Xloader")
        self._css_provider: Gtk.CssProvider | None = None
        self._css_monitor: Gio.FileMonitor | None = None
        self._css_reload_source = 0
        self._development_preview = os.environ.get("XLOADER_DEV_PREVIEW") == "1"
        self.connect("activate", self.on_activate)

    def on_activate(self, _application: Gtk.Application) -> None:
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property(
                "gtk-interface-color-scheme",
                Gtk.InterfaceColorScheme.DARK,
            )

        if self._css_provider is None:
            css_path = Path(__file__).parent / "assets" / "style.css"
            provider = Gtk.CssProvider()
            provider.connect("parsing-error", self._on_css_parsing_error)
            provider.load_from_path(str(css_path))
            self._css_provider = provider

            display = Gdk.Display.get_default()
            if display is not None:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                )

            if self._development_preview:
                self._watch_stylesheet(css_path)

        window = MainWindow(self)
        window.present()

    def _watch_stylesheet(self, css_path: Path) -> None:
        try:
            directory = Gio.File.new_for_path(str(css_path.parent))
            self._css_monitor = directory.monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES,
                None,
            )
            self._css_monitor.connect("changed", self._on_stylesheet_changed, css_path.name)
            print("[preview] CSS live reload enabled", flush=True)
        except GLib.Error as error:
            print(f"[preview] Could not watch stylesheet: {error}", file=sys.stderr, flush=True)

    def _on_stylesheet_changed(
        self,
        _monitor: Gio.FileMonitor,
        file: Gio.File,
        other_file: Gio.File | None,
        _event: Gio.FileMonitorEvent,
        css_name: str,
    ) -> None:
        changed_names = {file.get_basename()}
        if other_file is not None:
            changed_names.add(other_file.get_basename())
        if css_name not in changed_names:
            return

        if self._css_reload_source:
            GLib.source_remove(self._css_reload_source)
        self._css_reload_source = GLib.timeout_add(180, self._reload_stylesheet)

    def _reload_stylesheet(self) -> bool:
        self._css_reload_source = 0
        if self._css_provider is not None:
            css_path = Path(__file__).parent / "assets" / "style.css"
            try:
                self._css_provider.load_from_path(str(css_path))
                print("[preview] CSS reloaded", flush=True)
            except GLib.Error as error:
                print(f"[preview] CSS reload failed: {error}", file=sys.stderr, flush=True)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _on_css_parsing_error(
        _provider: Gtk.CssProvider,
        _section: object,
        error: GLib.Error,
    ) -> None:
        print(f"[preview] CSS parse error: {error}", file=sys.stderr, flush=True)


def main() -> None:
    app = XloaderApp()
    app.run(None)
