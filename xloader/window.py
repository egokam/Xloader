from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title="XLoader")
        self.set_default_size(800, 427)
        self.set_size_request(800, 427)
        self.set_resizable(False)
        self.add_css_class("xloader-window")
        self._build_window()

    def _build_window(self) -> None:
        titlebar = Gtk.HeaderBar()
        titlebar.add_css_class("window-titlebar")
        titlebar.set_show_title_buttons(False)
        titlebar.set_title_widget(Gtk.Label(label=""))

        traffic_lights = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        traffic_lights.add_css_class("traffic-lights")
        titlebar.pack_end(traffic_lights)

        minimize_button = Gtk.Button()
        minimize_button.add_css_class("traffic-dot-button")
        minimize_button.set_tooltip_text("Minimize XLoader")
        minimize_button.connect("clicked", lambda _button: self.minimize())
        minimize_dot = Gtk.Label(label="")
        minimize_dot.set_size_request(16, 16)
        minimize_dot.set_halign(Gtk.Align.CENTER)
        minimize_dot.set_valign(Gtk.Align.CENTER)
        minimize_dot.add_css_class("traffic-dot")
        minimize_dot.add_css_class("minimize-dot")
        minimize_button.set_child(minimize_dot)
        traffic_lights.append(minimize_button)

        close_button = Gtk.Button()
        close_button.add_css_class("traffic-dot-button")
        close_button.set_tooltip_text("Close XLoader")
        close_button.connect("clicked", lambda _button: self.close())
        close_dot = Gtk.Label(label="")
        close_dot.set_size_request(16, 16)
        close_dot.set_halign(Gtk.Align.CENTER)
        close_dot.set_valign(Gtk.Align.CENTER)
        close_dot.add_css_class("traffic-dot")
        close_dot.add_css_class("close-dot")
        close_button.set_child(close_dot)
        traffic_lights.append(close_button)

        self.set_titlebar(titlebar)

        empty_surface = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        empty_surface.add_css_class("empty-surface")
        self.set_child(empty_surface)
