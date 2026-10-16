from __future__ import annotations

import re
import threading
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from .xtool import AuthStatus, XToolService


def label(text: str, style: str | None = None) -> Gtk.Label:
    widget = Gtk.Label(label=text)
    widget.set_xalign(0)
    widget.set_wrap(True)
    if style:
        widget.add_css_class(style)
    return widget


def icon(name: str, size: int = 18) -> Gtk.Image:
    widget = Gtk.Image.new_from_icon_name(name)
    widget.set_pixel_size(size)
    return widget


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title="Xloader")
        self.set_default_size(1260, 850)
        self.set_size_request(1120, 700)
        self.add_css_class("xloader-window")

        self.xtool = XToolService()
        self.device_name: str | None = None
        self.selected_ipa: str | None = None
        self.install_running = False
        self.device_scan_running = False
        self.auth_scan_running = False
        self.auth_action_running = False
        self.auth_status: AuthStatus | None = None
        self.toast_timeout = 0
        self.install_output: list[str] = []

        self._build_window()
        GLib.timeout_add_seconds(4, self._scan_device)
        GLib.timeout_add_seconds(5, self._scan_auth_status)
        self._scan_device()
        if self.xtool.available:
            self._scan_auth_status()
        else:
            self._apply_auth_status(AuthStatus(False, error="Xloader's signing engine was not found"))

    def _build_window(self) -> None:
        titlebar = Gtk.HeaderBar()
        titlebar.add_css_class("window-titlebar")
        titlebar.set_title_widget(label("Xloader", "titlebar-title"))
        self.set_titlebar(titlebar)

        overlay = Gtk.Overlay()
        overlay.add_css_class("app-canvas")
        self.set_child(overlay)

        layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        overlay.set_child(layout)

        self._build_sidebar(layout)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add_css_class("main-scroll")
        layout.append(scroll)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        content.add_css_class("main-content")
        scroll.set_child(content)

        self._build_topline(content)
        self._build_intro(content)
        self._build_cards(content)
        self._build_activity(content)

        self.toast_revealer = Gtk.Revealer()
        self.toast_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.toast_revealer.set_transition_duration(240)
        self.toast_revealer.set_halign(Gtk.Align.END)
        self.toast_revealer.set_valign(Gtk.Align.END)
        self.toast_revealer.set_margin_end(28)
        self.toast_revealer.set_margin_bottom(25)
        self.toast_revealer.set_child(self._build_toast())
        overlay.add_overlay(self.toast_revealer)

    def _build_sidebar(self, layout: Gtk.Box) -> None:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        sidebar.set_size_request(226, -1)
        sidebar.add_css_class("sidebar")
        sidebar.set_margin_top(23)
        sidebar.set_margin_bottom(22)
        sidebar.set_margin_start(18)
        sidebar.set_margin_end(15)
        layout.append(sidebar)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        brand.set_margin_start(8)
        brand.set_margin_bottom(14)
        sidebar.append(brand)

        mark = Gtk.Label(label="x")
        mark.add_css_class("brand-mark")
        brand.append(mark)

        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        brand.append(brand_text)
        brand_name = label("Xloader", "brand-name")
        brand_name.set_wrap(False)
        brand_text.append(brand_name)
        brand_caption = label("APPLE DEVICE STUDIO", "brand-caption")
        brand_caption.set_wrap(False)
        brand_text.append(brand_caption)

        sidebar.append(label("WORKSPACE", "sidebar-section-label"))
        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        sidebar.append(nav)
        nav.append(self._nav_button("Install & refresh", "document-send-symbolic", active=True))
        nav.append(self._nav_button("My apps", "view-grid-symbolic", disabled=True))
        nav.append(self._nav_button("Activity", "list-view-symbolic", disabled=True))

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        sidebar.append(spacer)

        self._build_account_card(sidebar)

        cable_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        cable_card.add_css_class("sidebar-cable-card")
        cable_card.set_margin_start(3)
        cable_card.set_margin_end(3)
        cable_card.set_margin_bottom(4)
        sidebar.append(cable_card)

        cable_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cable_card.append(cable_header)
        cable_header.append(icon("usb-symbolic", 16))
        cable_header.append(label("USB WORKFLOW", "sidebar-cable-title"))
        cable_card.append(label("Connect your iPhone by cable to install or refresh apps.", "sidebar-cable-copy"))

        if self.xtool.bundled:
            engine_label = "SIGNING ENGINE · INCLUDED"
        elif self.xtool.available:
            engine_label = "SIGNING ENGINE · DEVELOPMENT"
        else:
            engine_label = "SIGNING ENGINE · MISSING"
        sidebar.append(label(engine_label, "sidebar-footer"))

    def _build_account_card(self, sidebar: Gtk.Box) -> None:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        card.add_css_class("account-card")
        card.set_margin_start(3)
        card.set_margin_end(3)
        sidebar.append(card)

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card.append(heading)
        heading.append(icon("avatar-default-symbolic", 15))
        heading.append(label("APPLE DEVELOPER ACCOUNT", "account-heading"))

        self.account_id_label = label("Checking account…", "account-id")
        self.account_id_label.set_wrap(False)
        self.account_id_label.set_max_width_chars(24)
        self.account_id_label.set_ellipsize(Pango.EllipsizeMode.END)
        card.append(self.account_id_label)

        self.account_meta_label = label("Apple account sign-in", "account-meta")
        card.append(self.account_meta_label)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card.append(actions)
        self.account_login_button = Gtk.Button(label="Sign in")
        self.account_login_button.add_css_class("account-button")
        self.account_login_button.set_visible(False)
        self.account_login_button.connect("clicked", self._on_login_clicked)
        actions.append(self.account_login_button)

        self.account_logout_button = Gtk.Button(label="Sign out")
        self.account_logout_button.add_css_class("account-button")
        self.account_logout_button.set_visible(False)
        self.account_logout_button.connect("clicked", self._on_logout_clicked)
        actions.append(self.account_logout_button)

    @staticmethod
    def _nav_button(text: str, icon_name: str, active: bool = False, disabled: bool = False) -> Gtk.Button:
        button = Gtk.Button()
        button.set_halign(Gtk.Align.FILL)
        button.add_css_class("nav-button")
        if active:
            button.add_css_class("active")
        if disabled:
            button.set_sensitive(False)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.append(icon(icon_name, 17))
        row.append(label(text, "nav-label"))
        button.set_child(row)
        return button

    def _build_topline(self, content: Gtk.Box) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_halign(Gtk.Align.FILL)
        content.append(row)

        row.append(label("DEVICE MANAGEMENT", "eyebrow"))

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        row.append(spacer)

        self.device_pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.device_pill.add_css_class("device-pill")
        row.append(self.device_pill)

        self.device_dot = Gtk.Label(label="●")
        self.device_dot.add_css_class("device-dot")
        self.device_pill.append(self.device_dot)
        self.device_pill_label = label("Searching for iPhone…", "device-pill-label")
        self.device_pill.append(self.device_pill_label)

        self.xtool_badge = label(
            "ENGINE INCLUDED" if self.xtool.bundled else "ENGINE READY",
            "tool-badge",
        )
        if not self.xtool.available:
            self.xtool_badge.set_text("ENGINE UNAVAILABLE")
            self.xtool_badge.add_css_class("tool-badge-error")
        row.append(self.xtool_badge)

    def _build_intro(self, content: Gtk.Box) -> None:
        intro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        intro.set_margin_top(4)
        content.append(intro)

        intro.append(label("Refresh your apps.\nKeep them close.", "hero-title"))
        intro_copy = label(
            "Choose an IPA, connect your iPhone, and let Xloader handle signing and installation.",
            "hero-copy",
        )
        intro_copy.set_max_width_chars(86)
        intro.append(intro_copy)

    def _build_cards(self, content: Gtk.Box) -> None:
        grid = Gtk.Grid()
        grid.set_column_spacing(18)
        grid.set_row_spacing(18)
        grid.set_column_homogeneous(False)
        content.append(grid)

        install_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        install_card.add_css_class("glass-card")
        install_card.set_hexpand(True)
        install_card.set_size_request(500, -1)
        grid.attach(install_card, 0, 0, 1, 1)
        self._build_installer_card(install_card)

        side_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        side_column.set_size_request(250, -1)
        grid.attach(side_column, 1, 0, 1, 1)
        self._build_device_card(side_column)
        self._build_steps_card(side_column)

        self.progress_revealer = Gtk.Revealer()
        self.progress_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.progress_revealer.set_transition_duration(260)
        self.progress_revealer.set_reveal_child(False)
        content.append(self.progress_revealer)
        self.progress_revealer.set_child(self._build_progress_card())

    def _build_installer_card(self, card: Gtk.Box) -> None:
        card.set_margin_top(3)
        card.set_margin_bottom(3)
        card.set_margin_start(3)
        card.set_margin_end(3)

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.append(heading)
        heading_icon = Gtk.Label(label="01")
        heading_icon.add_css_class("step-number")
        heading.append(heading_icon)
        heading_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        heading.append(heading_text)
        heading_text.append(label("APP INSTALLER", "eyebrow"))
        heading_text.append(label("Choose an IPA", "card-title"))

        self.drop_zone = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.drop_zone.set_halign(Gtk.Align.FILL)
        self.drop_zone.set_valign(Gtk.Align.FILL)
        self.drop_zone.add_css_class("drop-zone")
        card.append(self.drop_zone)

        upload = Gtk.Label(label="↑")
        upload.add_css_class("upload-glyph")
        upload.set_halign(Gtk.Align.CENTER)
        self.drop_zone.append(upload)
        drop_title = label("Bring an app package", "drop-title")
        drop_title.set_xalign(0.5)
        self.drop_zone.append(drop_title)
        hint = label("Select an .ipa file from your computer. Xloader will sign it for the connected device.", "drop-copy")
        hint.set_justify(Gtk.Justification.CENTER)
        hint.set_xalign(0.5)
        hint.set_max_width_chars(64)
        self.drop_zone.append(hint)

        self.browse_button = Gtk.Button(label="Browse IPA")
        self.browse_button.add_css_class("secondary-button")
        self.browse_button.set_halign(Gtk.Align.CENTER)
        self.browse_button.connect("clicked", self._on_browse_clicked)
        self.drop_zone.append(self.browse_button)

        self.file_revealer = Gtk.Revealer()
        self.file_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.file_revealer.set_transition_duration(200)
        card.append(self.file_revealer)
        self.file_revealer.set_child(self._build_selected_file())

        divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        divider.add_css_class("card-divider")
        card.append(divider)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        footer.set_valign(Gtk.Align.CENTER)
        card.append(footer)

        footer_icon = icon("smartphone-symbolic", 18)
        footer_icon.add_css_class("footer-device-icon")
        footer.append(footer_icon)

        self.install_hint = label("Connect iPhone by USB to continue", "install-hint")
        self.install_hint.set_hexpand(True)
        footer.append(self.install_hint)

        self.install_button = Gtk.Button()
        self.install_button.add_css_class("primary-button")
        self.install_button.set_sensitive(False)
        self.install_button.connect("clicked", self._on_install_clicked)
        install_button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        install_button_content.append(label("Install / refresh", "primary-button-label"))
        install_button_content.append(icon("arrow-right-symbolic", 16))
        self.install_button.set_child(install_button_content)
        footer.append(self.install_button)

    def _build_selected_file(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("selected-file")

        file_icon = Gtk.Label(label="IPA")
        file_icon.add_css_class("file-type-icon")
        row.append(file_icon)

        file_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        file_info.set_hexpand(True)
        row.append(file_info)

        self.file_name_label = label("No file selected", "selected-file-name")
        self.file_info_label = label("Choose an .ipa file", "selected-file-meta")
        file_info.append(self.file_name_label)
        file_info.append(self.file_info_label)

        remove = Gtk.Button()
        remove.set_child(icon("window-close-symbolic", 14))
        remove.add_css_class("icon-button")
        remove.set_tooltip_text("Remove selected IPA")
        remove.connect("clicked", self._on_clear_file)
        row.append(remove)
        return row

    def _build_device_card(self, parent: Gtk.Box) -> None:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class("glass-card")
        parent.append(card)

        card.append(label("YOUR DEVICE", "eyebrow"))

        device_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.append(device_row)
        device_icon = icon("phone-symbolic", 22)
        device_icon.add_css_class("device-illustration")
        device_row.append(device_icon)

        device_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        device_row.append(device_text)
        self.device_name_label = label("Waiting for iPhone", "device-name")
        self.device_detail_label = label("Connect over USB", "device-detail")
        device_text.append(self.device_name_label)
        device_text.append(self.device_detail_label)

        self.device_status = Gtk.Revealer()
        self.device_status.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.device_status.set_transition_duration(180)
        card.append(self.device_status)
        self.device_status_label = label("iPhone detected over USB", "connected-note")
        self.device_status.set_child(self.device_status_label)

        self.device_instructions = label(
            "Unlock your iPhone and tap Trust if it asks. Xloader checks the cable connection automatically.",
            "device-instructions",
        )
        card.append(self.device_instructions)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.add_css_class("usb-tag")
        footer.append(icon("usb-symbolic", 14))
        footer.append(label("USB · SECURE PAIRING", "usb-tag-label"))
        card.append(footer)

    def _build_steps_card(self, parent: Gtk.Box) -> None:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("glass-card")
        parent.append(card)

        card.append(label("HOW IT WORKS", "eyebrow"))
        for number, title, copy in (
            ("1", "Choose your IPA", "Pick the app package you want to install."),
            ("2", "Connect by cable", "Keep your iPhone unlocked during setup."),
            ("3", "We handle signing", "Xloader provisions, signs, and installs it."),
        ):
            item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            card.append(item)
            step = Gtk.Label(label=number)
            step.add_css_class("mini-step-number")
            item.append(step)
            details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            details.set_hexpand(True)
            item.append(details)
            details.append(label(title, "mini-step-title"))
            details.append(label(copy, "mini-step-copy"))

    def _build_progress_card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=11)
        card.add_css_class("glass-card")
        card.add_css_class("progress-card")

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        card.append(top)
        self.progress_icon = icon("emblem-synchronizing-symbolic", 19)
        top.append(self.progress_icon)
        self.progress_title = label("Preparing install…", "progress-title")
        self.progress_title.set_hexpand(True)
        top.append(self.progress_title)
        self.progress_percent = label("", "progress-percent")
        top.append(self.progress_percent)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(False)
        self.progress_bar.add_css_class("install-progress-bar")
        card.append(self.progress_bar)

        self.progress_detail = label("Xloader is preparing your app.", "progress-detail")
        card.append(self.progress_detail)

        details_button = Gtk.Button(label="Show install details")
        details_button.add_css_class("log-toggle")
        details_button.set_halign(Gtk.Align.START)
        details_button.connect("clicked", self._on_toggle_log)
        card.append(details_button)

        self.log_revealer = Gtk.Revealer()
        self.log_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.log_revealer.set_transition_duration(180)
        card.append(self.log_revealer)

        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_min_content_height(110)
        log_scroll.set_max_content_height(170)
        log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_scroll.add_css_class("log-scroll")
        self.log_revealer.set_child(log_scroll)

        self.log_buffer = Gtk.TextBuffer()
        self.log_view = Gtk.TextView(buffer=self.log_buffer)
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_view.add_css_class("install-log")
        log_scroll.set_child(self.log_view)

        return card

    def _build_activity(self, content: Gtk.Box) -> None:
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        card.add_css_class("activity-strip")
        content.append(card)

        activity_icon = Gtk.Label(label="✦")
        activity_icon.add_css_class("activity-sparkle")
        card.append(activity_icon)

        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        details.set_hexpand(True)
        card.append(details)
        details.append(label("Your install activity will appear here", "activity-title"))
        self.activity_copy = label("Connect an iPhone and choose an IPA to get started.", "activity-copy")
        details.append(self.activity_copy)

        self.activity_time = label("READY", "activity-time")
        card.append(self.activity_time)

    def _build_toast(self) -> Gtk.Box:
        toast = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        toast.add_css_class("toast")
        self.toast_icon = icon("emblem-ok-symbolic", 17)
        toast.append(self.toast_icon)
        self.toast_label = label("Ready", "toast-label")
        toast.append(self.toast_label)
        return toast

    def _scan_device(self) -> bool:
        if self.device_scan_running:
            return GLib.SOURCE_CONTINUE
        self.device_scan_running = True

        def worker() -> None:
            name, error = self.xtool.find_usb_device()
            GLib.idle_add(self._apply_device_scan, name, error)

        threading.Thread(target=worker, name="xloader-device-scan", daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def _apply_device_scan(self, name: str | None, error: str | None) -> bool:
        self.device_scan_running = False
        self.device_name = name
        if name:
            self.device_dot.remove_css_class("offline")
            self.device_dot.add_css_class("online")
            self.device_pill_label.set_text(f"{name} connected")
            self.device_name_label.set_text(name)
            self.device_detail_label.set_text("Connected by USB")
            self.device_status.set_reveal_child(True)
            self.device_instructions.set_text("Your iPhone is ready. Keep it connected while Xloader signs and installs the app.")
        else:
            self.device_dot.remove_css_class("online")
            self.device_dot.add_css_class("offline")
            self.device_pill_label.set_text("Connect iPhone by USB")
            self.device_name_label.set_text("Waiting for iPhone")
            self.device_detail_label.set_text("No cable connection yet")
            self.device_status.set_reveal_child(False)
            if error and not self.xtool.available:
                self.device_instructions.set_text(
                    "Xloader's signing engine is missing. Reinstall Xloader to restore it."
                )
            else:
                self.device_instructions.set_text("Connect your iPhone by USB, unlock it, and tap Trust if prompted.")

        self._update_install_hint()
        self._update_install_button()
        return GLib.SOURCE_REMOVE

    def _scan_auth_status(self) -> bool:
        if self.auth_scan_running or self.auth_action_running or not self.xtool.available:
            return GLib.SOURCE_CONTINUE
        self.auth_scan_running = True

        def worker() -> None:
            status = self.xtool.auth_status()
            GLib.idle_add(self._apply_auth_status, status)

        threading.Thread(target=worker, name="xloader-auth-status", daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def _apply_auth_status(self, status: AuthStatus) -> bool:
        previous = self.auth_status.signed_in if self.auth_status is not None else None
        self.auth_scan_running = False
        self.auth_status = status

        if status.error:
            self.account_id_label.set_text("Account status unavailable")
            self.account_meta_label.set_text("Check the signing engine, then try again.")
            self.account_id_label.set_tooltip_text(status.error)
        elif status.signed_in:
            self.account_id_label.set_text(status.apple_id or "Apple Developer account")
            self.account_id_label.set_tooltip_text(status.apple_id)
            details = []
            if status.team_id:
                details.append(f"Team {status.team_id}")
            if status.token_expiry:
                details.append(f"Expires {status.token_expiry}")
            self.account_meta_label.set_text(" · ".join(details) or "Apple account connected")
        else:
            self.account_id_label.set_text("Not signed in")
            self.account_id_label.set_tooltip_text(None)
            self.account_meta_label.set_text("Sign in to install and refresh apps.")

        self.account_login_button.set_visible(self.xtool.available and not status.signed_in)
        self.account_logout_button.set_visible(status.signed_in)
        self.account_login_button.set_sensitive(not self.auth_action_running)
        self.account_logout_button.set_sensitive(not self.auth_action_running)
        self._update_install_hint()
        self._update_install_button()

        if previous is False and status.signed_in:
            self._show_toast("Apple account connected")
        elif previous is True and not status.signed_in and not self.auth_action_running:
            self._show_toast("Apple account signed out")
        return GLib.SOURCE_REMOVE

    def _update_install_hint(self) -> None:
        if not self.xtool.available:
            hint = "Xloader's signing engine is unavailable"
        elif self.auth_status is None:
            hint = "Checking Apple developer account…"
        elif self.auth_status.error:
            hint = "Apple account status could not be checked"
        elif not self.auth_status.signed_in:
            hint = "Sign in to Apple to continue"
        elif not self.device_name:
            hint = "Connect iPhone by USB to continue"
        else:
            hint = "iPhone ready over USB"
        self.install_hint.set_text(hint)

    def _on_browse_clicked(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Choose an iPhone app package")
        file_filter = Gtk.FileFilter.new()
        file_filter.set_name("iOS app package (.ipa)")
        file_filter.add_pattern("*.ipa")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)
        dialog.open(self, None, self._on_file_dialog_response)

    def _on_file_dialog_response(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            selected = dialog.open_finish(result)
        except GLib.Error:
            return
        if selected is not None:
            path = selected.get_path()
            if path:
                self._set_ipa(path)

    def _set_ipa(self, path: str) -> None:
        candidate = Path(path)
        if candidate.suffix.lower() != ".ipa":
            self._show_toast("Choose an .ipa file", success=False)
            return
        if not candidate.is_file():
            self._show_toast("That file is no longer available", success=False)
            return

        self.selected_ipa = str(candidate)
        size = candidate.stat().st_size
        self.file_name_label.set_text(candidate.name)
        self.file_info_label.set_text(f"iOS app package · {self._format_size(size)}")
        self.file_revealer.set_reveal_child(True)
        self._update_install_button()

    @staticmethod
    def _format_size(size: int) -> str:
        units = ("B", "KB", "MB", "GB")
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB"

    def _on_clear_file(self, _button: Gtk.Button) -> None:
        if self.install_running:
            return
        self.selected_ipa = None
        self.file_name_label.set_text("No file selected")
        self.file_info_label.set_text("Choose an .ipa file")
        self.file_revealer.set_reveal_child(False)
        self._update_install_button()

    def _update_install_button(self) -> None:
        signed_in = bool(self.auth_status and self.auth_status.signed_in)
        self.install_button.set_sensitive(
            bool(
                self.device_name
                and self.selected_ipa
                and not self.install_running
                and self.xtool.available
                and signed_in
            )
        )

    def _on_login_clicked(self, _button: Gtk.Button) -> None:
        dialog = Gtk.AlertDialog()
        dialog.set_message("Sign in to Apple Developer Services")
        dialog.set_detail(
            "Xloader will open a sign-in terminal for Apple ID and verification prompts. "
            "Enter credentials directly in the sign-in terminal; Xloader does not handle or save your password."
        )
        dialog.set_buttons(["Open sign-in terminal", "Cancel"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(1)
        dialog.choose(self, None, self._on_login_confirmation)

    def _on_login_confirmation(self, dialog: Gtk.AlertDialog, result: Gio.AsyncResult) -> None:
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            return
        if response != 0:
            return

        error = self.xtool.open_login_terminal()
        if error:
            self._show_simple_dialog(
                "Could not open sign-in terminal",
                error,
            )
        else:
            self._show_toast("Sign-in terminal opened")

    def _on_logout_clicked(self, _button: Gtk.Button) -> None:
        account = self.auth_status.apple_id if self.auth_status else None
        dialog = Gtk.AlertDialog()
        dialog.set_message("Sign out of Apple Developer Services?")
        detail = "Xloader will clear the saved Apple sign-in. Apps already installed on your iPhone will not be removed."
        if account:
            detail = f"Sign out {account}? {detail}"
        dialog.set_detail(detail)
        dialog.set_buttons(["Sign out", "Cancel"])
        dialog.set_default_button(1)
        dialog.set_cancel_button(1)
        dialog.choose(self, None, self._on_logout_confirmation)

    def _on_logout_confirmation(self, dialog: Gtk.AlertDialog, result: Gio.AsyncResult) -> None:
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            return
        if response != 0:
            return

        self.auth_action_running = True
        self.account_id_label.set_text("Signing out…")
        self.account_login_button.set_sensitive(False)
        self.account_logout_button.set_sensitive(False)

        def complete(success: bool, detail: str | None) -> None:
            GLib.idle_add(self._finish_logout, success, detail)

        self.xtool.logout(complete)

    def _finish_logout(self, success: bool, detail: str | None) -> bool:
        self.auth_action_running = False
        if success:
            self.auth_status = None
            self.account_id_label.set_text("Checking account…")
            self.account_meta_label.set_text("Checking saved Apple sign-in")
            self._scan_auth_status()
            self._show_toast("Apple account signed out")
        else:
            self.account_login_button.set_sensitive(True)
            self.account_logout_button.set_sensitive(True)
            self._show_simple_dialog(
                "Could not sign out",
                detail or "Xloader could not clear the saved Apple account. Try again.",
            )
        return GLib.SOURCE_REMOVE

    def _show_simple_dialog(self, title: str, detail: str) -> None:
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(detail)
        dialog.set_buttons(["Done"])
        dialog.set_default_button(0)
        dialog.show(self)

    def _on_install_clicked(self, _button: Gtk.Button) -> None:
        if not self.selected_ipa or not self.device_name or self.install_running:
            return
        self.install_running = True
        self.progress_title.set_text("Starting install…")
        self.progress_detail.set_text("Xloader is connecting to your iPhone.")
        self.progress_percent.set_text("")
        self.progress_bar.set_fraction(0.01)
        self.progress_icon.set_from_icon_name("emblem-synchronizing-symbolic")
        self.log_buffer.set_text("")
        self.install_output.clear()
        self.log_revealer.set_reveal_child(False)
        self.progress_revealer.set_reveal_child(True)
        self.activity_copy.set_text(f"Preparing {Path(self.selected_ipa).name} for your iPhone.")
        self.activity_time.set_text("IN PROGRESS")
        self.browse_button.set_sensitive(False)
        self._update_install_button()

        def output(line: str) -> None:
            GLib.idle_add(self._handle_install_output, line)

        def complete(return_code: int) -> None:
            GLib.idle_add(self._finish_install, return_code)

        self.xtool.install_ipa(self.selected_ipa, output, complete)

    def _handle_install_output(self, line: str) -> bool:
        self.install_output.append(line)
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end, line + "\n")
        match = re.search(r"\[([^\]]+)\]\s+(\d+)%", line)
        if match:
            stage = match.group(1)
            percent = int(match.group(2))
            self.progress_title.set_text(stage)
            self.progress_percent.set_text(f"{percent}%")
            self.progress_bar.set_fraction(max(1, min(percent, 100)) / 100)
            self.progress_detail.set_text(self._stage_copy(stage, percent))
        elif line.startswith("Waiting for device"):
            self.progress_title.set_text("Waiting for iPhone")
            self.progress_detail.set_text("Connect the iPhone with USB and keep it unlocked.")
        elif line.startswith("Installing to device:"):
            self.progress_title.set_text("Starting installation")
            self.progress_detail.set_text("Xloader has selected the connected iPhone.")
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _stage_copy(stage: str, percent: int) -> str:
        if percent >= 100:
            return f"{stage} complete."
        return f"{stage} · {percent}% complete"

    def _finish_install(self, return_code: int) -> bool:
        self.install_running = False
        self.browse_button.set_sensitive(True)
        if return_code == 0:
            self.progress_title.set_text("App installed")
            self.progress_detail.set_text("Xloader signed, installed, and verified the app.")
            self.progress_percent.set_text("100%")
            self.progress_bar.set_fraction(1)
            self.progress_icon.set_from_icon_name("emblem-ok-symbolic")
            self.activity_copy.set_text(f"Installed {Path(self.selected_ipa or 'app').name} successfully.")
            self.activity_time.set_text("JUST NOW")
            self._show_toast("App installed and verified")
            self._show_simple_dialog(
                "App installed and verified",
                f"{Path(self.selected_ipa or 'Your app').name} is ready on {self.device_name or 'your iPhone'}.",
            )
        else:
            output = "\n".join(self.install_output).casefold()
            free_profile_limit = "maximum number of installed apps using a free developer profile" in output
            if free_profile_limit:
                failure_title = "Free profile limit reached"
                failure_detail = (
                    "This iPhone has reached the free profile's installed-app limit. "
                    "Remove an app signed with this Apple account, then retry."
                )
                self.progress_title.set_text("Free profile limit reached")
                self.progress_detail.set_text(failure_detail)
                self.activity_copy.set_text(
                    "Remove one app using this free developer profile from the iPhone, then try again."
                )
            else:
                failure_title = "Could not install this app"
                failure_detail = "The signing engine stopped before installation completed. Open technical details for the exact reason."
                self.progress_title.set_text("Installation failed")
                self.progress_detail.set_text(failure_detail)
                self.activity_copy.set_text("The install did not complete. Open details to review the signing engine's message.")
            self.progress_icon.set_from_icon_name("dialog-error-symbolic")
            self.activity_time.set_text("NEEDS ATTENTION")
            self._show_toast(
                "Free profile limit reached" if free_profile_limit else "Install did not complete",
                success=False,
            )
            self._show_install_failure_dialog(failure_title, failure_detail, "\n".join(self.install_output))
        self._update_install_button()
        return GLib.SOURCE_REMOVE

    def _show_install_failure_dialog(self, title: str, detail: str, technical_details: str) -> None:
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(detail)
        dialog.set_buttons(["Show technical details", "Close"])
        dialog.set_default_button(1)
        dialog.set_cancel_button(1)

        def on_choice(alert: Gtk.AlertDialog, result: Gio.AsyncResult) -> None:
            try:
                response = alert.choose_finish(result)
            except GLib.Error:
                return
            if response == 0:
                self._show_technical_details(technical_details)

        dialog.choose(self, None, on_choice)

    def _show_technical_details(self, details: str) -> None:
        window = Gtk.Window(title="Install details")
        window.set_transient_for(self)
        window.set_modal(True)
        window.set_destroy_with_parent(True)
        window.set_default_size(760, 470)
        window.add_css_class("details-window")

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        layout.set_margin_top(18)
        layout.set_margin_bottom(18)
        layout.set_margin_start(18)
        layout.set_margin_end(18)
        window.set_child(layout)

        layout.append(label("INSTALL RESPONSE", "eyebrow"))
        layout.append(label("Technical details", "card-title"))

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add_css_class("log-scroll")
        layout.append(scroll)

        buffer = Gtk.TextBuffer()
        buffer.set_text(details or "The signing engine did not return additional details.")
        view = Gtk.TextView(buffer=buffer)
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.add_css_class("install-log")
        scroll.set_child(view)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        actions.set_halign(Gtk.Align.END)
        layout.append(actions)

        copy_button = Gtk.Button(label="Copy details")
        copy_button.add_css_class("secondary-button")
        copy_button.connect("clicked", lambda _button: self._copy_details(details))
        actions.append(copy_button)

        close_button = Gtk.Button(label="Close")
        close_button.add_css_class("primary-button")
        close_button.connect("clicked", lambda _button: window.close())
        actions.append(close_button)
        window.present()

    def _copy_details(self, details: str) -> None:
        display = Gdk.Display.get_default()
        if display is not None:
            display.get_clipboard().set_text(details)
            self._show_toast("Install details copied")

    def _on_toggle_log(self, _button: Gtk.Button) -> None:
        self.log_revealer.set_reveal_child(not self.log_revealer.get_reveal_child())

    def _show_toast(self, message: str, success: bool = True) -> None:
        self.toast_label.set_text(message)
        self.toast_icon.set_from_icon_name("emblem-ok-symbolic" if success else "dialog-warning-symbolic")
        self.toast_revealer.set_reveal_child(True)
        if self.toast_timeout:
            GLib.source_remove(self.toast_timeout)

        def dismiss() -> bool:
            self.toast_revealer.set_reveal_child(False)
            self.toast_timeout = 0
            return GLib.SOURCE_REMOVE

        self.toast_timeout = GLib.timeout_add(2800, dismiss)
