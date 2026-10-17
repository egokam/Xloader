from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gtk, Pango

from .device import DeviceInfo, DeviceService
from .xtool import AuthStatus, XToolService


NO_DEVICE_TEXT = "No device detected, connect your iDevice with a cable."


class ReferenceImageLayer(Gtk.Widget):
    """Draw the left side of a reference screenshot over the live interface."""

    def __init__(self, titlebar: bool = False) -> None:
        super().__init__()
        self.texture: Gdk.Texture | None = None
        self.opacity = 0.45
        self.divider_x = 400
        self.titlebar = titlebar
        self.set_can_target(False)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self.set_hexpand(True)
        self.set_vexpand(True)

    def do_measure(
        self,
        _orientation: Gtk.Orientation,
        _for_size: int,
    ) -> tuple[int, int, int, int]:
        return 0, 0, -1, -1

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        if self.texture is None:
            return

        width = self.get_width()
        height = self.get_height()
        root = self.get_root()
        if width <= 0 or height <= 0 or not isinstance(root, Gtk.Window):
            return

        frame_width = root.get_width()
        frame_height = root.get_height()
        titlebar_widget = root.get_titlebar()
        titlebar_height = titlebar_widget.get_height() if titlebar_widget else 0
        image_y = 0 if self.titlebar else -titlebar_height

        full_bounds = Graphene.Rect().init(
            0,
            0,
            float(width),
            float(height),
        )
        image_bounds = Graphene.Rect().init(
            0,
            float(image_y),
            float(frame_width),
            float(frame_height),
        )
        comparison_bounds = Graphene.Rect().init(
            0,
            0,
            float(min(self.divider_x, width)),
            float(height),
        )

        snapshot.push_clip(full_bounds)
        snapshot.push_opacity(self.opacity)
        snapshot.push_clip(comparison_bounds)
        snapshot.append_texture(self.texture, image_bounds)
        snapshot.pop()
        snapshot.pop()
        snapshot.pop()


class MainWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        application: Gtk.Application,
        development_preview: bool = False,
    ) -> None:
        super().__init__(application=application, title="XLoader")
        self.set_default_size(800, 427)
        self.set_size_request(800, 427)
        self.set_resizable(False)
        self.add_css_class("xloader-window")
        self._device_service = DeviceService()
        self._devices: list[DeviceInfo] = []
        self._selected_device: DeviceInfo | None = None
        self._hide_sensitive_device_info = True
        self._device_scan_running = False
        self._updating_device_dropdown = False
        self._pairing_in_progress = False
        self._xtool_service = XToolService()
        self._auth_status_running = False
        self._auth_signed_in = False
        self._development_preview = development_preview
        self._preview_state_path = Path(
            os.environ.get(
                "XLOADER_DEV_PREVIEW_STATE",
                str(Path(GLib.get_user_cache_dir()) / "xloader" / "dev-preview.json"),
            )
        ).expanduser()
        self._preview_state = self._read_preview_state()
        self._preview_opacity = self._bounded_number(
            self._preview_state.get("opacity", 0.45),
            fallback=0.45,
            minimum=0.0,
            maximum=1.0,
        )
        self._preview_divider_x = int(
            self._bounded_number(
                self._preview_state.get("divider_x", 400),
                fallback=400,
                minimum=1,
                maximum=799,
            )
        )
        saved_reference = self._preview_state.get("image_path")
        if not isinstance(saved_reference, str):
            saved_reference = None
        self._preview_reference_path = (
            saved_reference or os.environ.get("XLOADER_REFERENCE_IMAGE")
        )
        self._preview_drag_origin = self._preview_divider_x
        self._build_window()
        self._schedule_device_scan()
        self._device_scan_source = GLib.timeout_add_seconds(3, self._schedule_device_scan)
        self._schedule_auth_status()
        self._auth_scan_source = GLib.timeout_add_seconds(15, self._schedule_auth_status)

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

        if self._development_preview:
            titlebar_overlay = Gtk.Overlay()
            titlebar_overlay.set_child(titlebar)
            self._titlebar_reference_layer = ReferenceImageLayer(titlebar=True)
            self._titlebar_reference_layer.opacity = self._preview_opacity
            self._titlebar_reference_layer.divider_x = self._preview_divider_x
            titlebar_overlay.add_overlay(self._titlebar_reference_layer)
            self._titlebar_divider_hitbox = self._create_preview_divider()
            titlebar_overlay.add_overlay(self._titlebar_divider_hitbox)
            self.set_titlebar(titlebar_overlay)
        else:
            self.set_titlebar(titlebar)

        surface = Gtk.Fixed()
        surface.add_css_class("empty-surface")
        if self._development_preview:
            self._preview_overlay = Gtk.Overlay()
            self._preview_overlay.set_child(surface)
            self._body_reference_layer = ReferenceImageLayer()
            self._body_reference_layer.opacity = self._preview_opacity
            self._body_reference_layer.divider_x = self._preview_divider_x
            self._preview_overlay.add_overlay(self._body_reference_layer)
            self._body_divider_hitbox = self._create_preview_divider()
            self._preview_overlay.add_overlay(self._body_divider_hitbox)
            self._add_preview_tools(self._preview_overlay)
            self.set_child(self._preview_overlay)
        else:
            self.set_child(surface)

        ipa_button = Gtk.Button()
        ipa_button.add_css_class("ipa-select-button")
        ipa_button.set_tooltip_text("Choose an IPA file")

        ipa_x, ipa_y = 25, 28
        ipa_name_gap = 21
        ipa_placeholder = Gtk.Box()
        ipa_placeholder.add_css_class("ipa-placeholder-area")
        ipa_placeholder.set_size_request(114, 142)

        ipa_image = Gtk.Picture.new_for_filename(
            str(Path(__file__).parent / "assets" / "ipa.png")
        )
        ipa_image.set_can_shrink(True)
        ipa_image.set_content_fit(Gtk.ContentFit.CONTAIN)
        ipa_image.set_size_request(114, 142)
        ipa_image.set_hexpand(True)
        ipa_image.set_vexpand(True)
        ipa_placeholder.append(ipa_image)
        ipa_button.set_child(ipa_placeholder)
        ipa_button.connect("clicked", self._choose_ipa_file)
        ipa_button.set_size_request(116, 142)
        surface.put(ipa_button, ipa_x, ipa_y)

        self.ipa_name_label = Gtk.Label(label="<none>")
        self.ipa_name_label.add_css_class("ipa-name-label")
        self.ipa_name_label.set_size_request(116, 22)
        self.ipa_name_label.set_max_width_chars(14)
        self.ipa_name_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.ipa_name_label.set_halign(Gtk.Align.CENTER)
        surface.put(self.ipa_name_label, ipa_x, ipa_y + 142 + ipa_name_gap)

        device_title = Gtk.Label(label="iDevice:")
        device_title.add_css_class("device-title")
        device_title.set_halign(Gtk.Align.START)
        surface.put(device_title, 178, 24)

        self.device_dropdown = Gtk.DropDown.new(
            Gtk.StringList.new([NO_DEVICE_TEXT]),
            None,
        )
        self.device_dropdown.add_css_class("device-dropdown")
        self.device_dropdown.set_size_request(350, 32)
        self.device_dropdown.connect("notify::selected", self._on_device_selected)
        surface.put(self.device_dropdown, 185, 80)

        self.copy_device_button = self._make_device_button(
            "edit-copy-symbolic",
            "Copy device UDID",
            self._copy_device_udid,
        )
        surface.put(self.copy_device_button, 627, 62)

        self.repair_device_button = self._make_device_button(
            "smartphone-symbolic",
            "Re-pair connected iDevice",
            self._repair_device_pairing,
        )
        surface.put(self.repair_device_button, 681, 62)

        self.privacy_button = self._make_device_button(
            "view-conceal-symbolic",
            "Show sensitive device information",
            self._toggle_device_privacy,
        )
        surface.put(self.privacy_button, 735, 62)

        apple_id_title = Gtk.Label(label="Apple ID:")
        apple_id_title.add_css_class("apple-id-title")
        apple_id_title.set_halign(Gtk.Align.START)
        surface.put(apple_id_title, 201, 119)

        apple_id_control = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        apple_id_control.add_css_class("apple-id-control")
        apple_id_control.set_size_request(566, 40)

        self.apple_id_entry = Gtk.Entry()
        self.apple_id_entry.add_css_class("apple-id-field")
        self.apple_id_entry.set_placeholder_text("Not signed in")
        self.apple_id_entry.set_editable(False)
        self.apple_id_entry.set_hexpand(True)
        apple_id_control.append(self.apple_id_entry)

        self.apple_id_menu = Gtk.MenuButton()
        self.apple_id_menu.add_css_class("apple-id-menu-button")
        self.apple_id_menu.set_tooltip_text("Apple ID account options")
        arrow = Gtk.Image.new_from_icon_name("pan-down-symbolic")
        arrow.set_pixel_size(16)
        self.apple_id_menu.set_child(arrow)

        account_menu = Gtk.Popover()
        account_actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        account_actions.add_css_class("apple-id-actions")

        self.sign_in_button = Gtk.Button(label="Sign in…")
        self.sign_in_button.add_css_class("apple-id-action")
        self.sign_in_button.connect("clicked", self._sign_in_to_apple)
        account_actions.append(self.sign_in_button)

        self.sign_out_button = Gtk.Button(label="Sign out")
        self.sign_out_button.add_css_class("apple-id-action")
        self.sign_out_button.set_sensitive(False)
        self.sign_out_button.connect("clicked", self._sign_out_of_apple)
        account_actions.append(self.sign_out_button)

        refresh_account_button = Gtk.Button(label="Refresh account")
        refresh_account_button.add_css_class("apple-id-action")
        refresh_account_button.connect(
            "clicked", lambda _button: self._schedule_auth_status()
        )
        account_actions.append(refresh_account_button)

        account_menu.set_child(account_actions)
        self.apple_id_menu.set_popover(account_menu)
        apple_id_control.append(self.apple_id_menu)
        surface.put(apple_id_control, 211, 151)

        refresh_button = Gtk.Button()
        refresh_button.add_css_class("refresh-button")
        refresh_button.set_tooltip_text("Refresh")
        refresh_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        refresh_icon.set_pixel_size(18)
        refresh_button.set_child(refresh_icon)
        refresh_button.set_size_request(35, 36)
        surface.put(refresh_button, 17, 268)

        start_button = Gtk.Button(label="Start")
        start_button.add_css_class("start-button")
        start_button.set_size_request(710, 28)
        surface.put(start_button, 72, 273)

        if self._development_preview:
            reference_path = os.environ.get("XLOADER_REFERENCE_IMAGE")
            reference_path = self._preview_reference_path or reference_path
            if reference_path:
                self._load_reference_image(reference_path)

    def _add_preview_tools(self, overlay: Gtk.Overlay) -> None:
        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tools.add_css_class("preview-tools")
        tools.set_halign(Gtk.Align.END)
        tools.set_valign(Gtk.Align.END)
        tools.set_margin_end(10)
        tools.set_margin_bottom(9)

        choose_button = Gtk.Button(label="Reference image…")
        choose_button.add_css_class("preview-tool-button")
        choose_button.connect("clicked", self._choose_reference_image)
        tools.append(choose_button)

        self._preview_opacity_label = Gtk.Label(
            label=f"{round(self._preview_opacity * 100)}%"
        )
        self._preview_opacity_label.add_css_class("preview-opacity-label")
        tools.append(self._preview_opacity_label)

        opacity_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0.0,
            1.0,
            0.01,
        )
        opacity_scale.add_css_class("preview-opacity-scale")
        opacity_scale.set_size_request(105, -1)
        opacity_scale.set_draw_value(False)
        opacity_scale.set_value(self._preview_opacity)
        opacity_scale.connect("value-changed", self._on_preview_opacity_changed)
        tools.append(opacity_scale)

        overlay.add_overlay(tools)

    def _create_preview_divider(self) -> Gtk.Box:
        hitbox = Gtk.Box()
        hitbox.add_css_class("preview-divider-hitbox")
        hitbox.set_halign(Gtk.Align.START)
        hitbox.set_valign(Gtk.Align.FILL)
        hitbox.set_size_request(15, -1)
        hitbox.set_margin_start(max(0, self._preview_divider_x - 7))
        hitbox.set_visible(False)
        hitbox.set_tooltip_text("Drag to compare the reference with the live UI")

        line = Gtk.Box()
        line.add_css_class("preview-divider-line")
        line.set_size_request(1, -1)
        line.set_halign(Gtk.Align.CENTER)
        line.set_valign(Gtk.Align.FILL)
        hitbox.append(line)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_preview_drag_begin)
        drag.connect("drag-update", self._on_preview_drag_update)
        drag.connect("drag-end", self._on_preview_drag_end)
        hitbox.add_controller(drag)
        return hitbox

    def _choose_reference_image(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserNative.new(
            "Choose reference design image",
            self,
            Gtk.FileChooserAction.OPEN,
            "_Open",
            "_Cancel",
        )
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Design images")
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"):
            image_filter.add_pattern(pattern)
        dialog.add_filter(image_filter)
        dialog.connect("response", self._on_reference_image_selected)
        dialog.show()

    def _on_reference_image_selected(
        self,
        dialog: Gtk.FileChooserNative,
        response: int,
    ) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            selected_file = dialog.get_file()
            if selected_file is not None and selected_file.get_path():
                self._load_reference_image(selected_file.get_path())
        dialog.destroy()

    def _load_reference_image(self, path: str) -> None:
        try:
            texture = Gdk.Texture.new_from_filename(str(Path(path).expanduser()))
        except GLib.Error as error:
            self._show_message("Could not load reference image", str(error))
            return

        for layer in (self._titlebar_reference_layer, self._body_reference_layer):
            layer.texture = texture
            layer.queue_draw()
        self._preview_reference_path = str(Path(path).expanduser().resolve())
        self._titlebar_divider_hitbox.set_visible(True)
        self._body_divider_hitbox.set_visible(True)
        self._save_preview_state()

    def _on_preview_opacity_changed(self, scale: Gtk.Scale) -> None:
        opacity = scale.get_value()
        self._preview_opacity = opacity
        self._preview_opacity_label.set_text(f"{round(opacity * 100)}%")
        self._titlebar_reference_layer.opacity = opacity
        self._body_reference_layer.opacity = opacity
        self._titlebar_reference_layer.queue_draw()
        self._body_reference_layer.queue_draw()
        self._save_preview_state()

    def _on_preview_drag_begin(
        self,
        _drag: Gtk.GestureDrag,
        _start_x: float,
        _start_y: float,
    ) -> None:
        self._preview_drag_origin = self._preview_divider_x

    def _on_preview_drag_update(
        self,
        _drag: Gtk.GestureDrag,
        offset_x: float,
        _offset_y: float,
    ) -> None:
        width = max(self.get_width(), 2)
        self._preview_divider_x = max(
            1,
            min(width - 1, round(self._preview_drag_origin + offset_x)),
        )
        for layer in (self._titlebar_reference_layer, self._body_reference_layer):
            layer.divider_x = self._preview_divider_x
            layer.queue_draw()
        for hitbox in (self._titlebar_divider_hitbox, self._body_divider_hitbox):
            hitbox.set_margin_start(max(0, self._preview_divider_x - 7))

    def _on_preview_drag_end(
        self,
        _drag: Gtk.GestureDrag,
        _offset_x: float,
        _offset_y: float,
    ) -> None:
        self._save_preview_state()

    def _read_preview_state(self) -> dict[str, object]:
        if not self._development_preview:
            return {}
        try:
            state = json.loads(self._preview_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return state if isinstance(state, dict) else {}

    @staticmethod
    def _bounded_number(
        value: object,
        *,
        fallback: float,
        minimum: float,
        maximum: float,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(minimum, min(maximum, number))

    def _save_preview_state(self) -> None:
        if not self._development_preview:
            return
        state = {
            "image_path": self._preview_reference_path,
            "opacity": self._preview_opacity,
            "divider_x": self._preview_divider_x,
        }
        try:
            self._preview_state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self._preview_state_path.with_suffix(".json.tmp")
            temporary_path.write_text(
                json.dumps(state, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary_path.replace(self._preview_state_path)
        except OSError as error:
            print(f"[preview] Could not save comparison settings: {error}", flush=True)

    @staticmethod
    def _make_device_button(
        icon_name: str,
        tooltip: str,
        callback: object,
    ) -> Gtk.Button:
        button = Gtk.Button()
        button.add_css_class("device-icon-button")
        button.set_tooltip_text(tooltip)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(18)
        button.set_child(icon)
        button.set_size_request(42, 42)
        button.connect("clicked", callback)
        return button

    def _schedule_device_scan(self) -> bool:
        if not self._device_scan_running:
            self._device_scan_running = True

            def scan() -> None:
                devices = self._device_service.list_usb_devices()
                GLib.idle_add(self._on_device_scan_complete, devices)

            threading.Thread(target=scan, name="xloader-device-scan", daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def _on_device_scan_complete(self, devices: list[DeviceInfo]) -> bool:
        self._device_scan_running = False
        if devices != self._devices:
            preferred_udid = self._selected_device.udid if self._selected_device else None
            self._devices = devices
            self._rebuild_device_dropdown(preferred_udid)
        return GLib.SOURCE_REMOVE

    def _rebuild_device_dropdown(self, preferred_udid: str | None = None) -> None:
        labels = [self._format_device(device) for device in self._devices]
        if not labels:
            labels = [NO_DEVICE_TEXT]

        selected_index = next(
            (
                index
                for index, device in enumerate(self._devices)
                if device.udid == preferred_udid
            ),
            0,
        )

        self._updating_device_dropdown = True
        self.device_dropdown.set_model(Gtk.StringList.new(labels))
        self.device_dropdown.set_selected(selected_index)
        self._updating_device_dropdown = False
        self._selected_device = (
            self._devices[selected_index] if self._devices else None
        )

    def _format_device(self, device: DeviceInfo) -> str:
        identity = f"{device.name} ({device.model})"
        identifier = (
            "*" * 16 if self._hide_sensitive_device_info else device.udid
        )
        return f"{identity}  {identifier}"

    def _on_device_selected(self, _dropdown: Gtk.DropDown, _parameter: object) -> None:
        if self._updating_device_dropdown:
            return
        selected_index = self.device_dropdown.get_selected()
        self._selected_device = (
            self._devices[selected_index]
            if selected_index < len(self._devices)
            else None
        )

    def _copy_device_udid(self, _button: Gtk.Button) -> None:
        if self._selected_device is None:
            return
        display = Gdk.Display.get_default()
        if display is not None:
            display.get_clipboard().set(self._selected_device.udid)

    def _toggle_device_privacy(self, _button: Gtk.Button) -> None:
        self._hide_sensitive_device_info = not self._hide_sensitive_device_info
        device = self._selected_device
        self._rebuild_device_dropdown(device.udid if device else None)
        image = self.privacy_button.get_child()
        if isinstance(image, Gtk.Image):
            image.set_from_icon_name(
                "view-conceal-symbolic"
                if self._hide_sensitive_device_info
                else "view-reveal-symbolic"
            )
        self.privacy_button.set_tooltip_text(
            "Show sensitive device information"
            if self._hide_sensitive_device_info
            else "Hide sensitive device information"
        )

    def _repair_device_pairing(self, _button: Gtk.Button) -> None:
        device = self._selected_device
        if device is None or self._pairing_in_progress:
            return

        self._pairing_in_progress = True
        self.repair_device_button.set_sensitive(False)

        def repair() -> None:
            success, message = self._device_service.repair_pairing(device.udid)
            GLib.idle_add(self._on_pairing_complete, success, message)

        threading.Thread(target=repair, name="xloader-device-pair", daemon=True).start()

    def _on_pairing_complete(self, success: bool, message: str) -> bool:
        self._pairing_in_progress = False
        self.repair_device_button.set_sensitive(self._selected_device is not None)
        dialog = Gtk.AlertDialog()
        dialog.set_message("Device paired" if success else "Could not pair device")
        dialog.set_detail(message)
        dialog.set_buttons(["OK"])
        dialog.set_default_button(0)
        dialog.show(self)
        return GLib.SOURCE_REMOVE

    def _schedule_auth_status(self) -> bool:
        if not self._auth_status_running:
            self._auth_status_running = True

            def check_status() -> None:
                status = self._xtool_service.auth_status()
                GLib.idle_add(self._on_auth_status_complete, status)

            threading.Thread(
                target=check_status,
                name="xloader-auth-status",
                daemon=True,
            ).start()
        return GLib.SOURCE_CONTINUE

    def _on_auth_status_complete(self, status: AuthStatus) -> bool:
        self._auth_status_running = False
        self._auth_signed_in = status.signed_in
        if status.signed_in:
            self.apple_id_entry.set_text(status.apple_id or "Signed in")
            details = []
            if status.team_id:
                details.append(f"Team ID: {status.team_id}")
            if status.token_expiry:
                details.append(f"Token expiry: {status.token_expiry}")
            self.apple_id_entry.set_tooltip_text("\n".join(details) or None)
        elif not self._xtool_service.available:
            self.apple_id_entry.set_placeholder_text("Signing engine unavailable")
            self.apple_id_entry.set_tooltip_text(status.error)
        else:
            self.apple_id_entry.set_text("")
            self.apple_id_entry.set_placeholder_text("Not signed in")
            self.apple_id_entry.set_tooltip_text(status.error)

        self.sign_in_button.set_sensitive(self._xtool_service.available)
        self.sign_out_button.set_sensitive(status.signed_in)
        return GLib.SOURCE_REMOVE

    def _sign_in_to_apple(self, _button: Gtk.Button) -> None:
        message = self._xtool_service.open_login_terminal()
        if message:
            self._show_message("Could not start Apple sign-in", message)
            return
        self.apple_id_entry.set_text("")
        self.apple_id_entry.set_placeholder_text("Complete sign-in in the terminal…")

    def _sign_out_of_apple(self, _button: Gtk.Button) -> None:
        self.sign_out_button.set_sensitive(False)

        def completed(success: bool, message: str | None) -> None:
            GLib.idle_add(self._on_sign_out_complete, success, message)

        self._xtool_service.logout(completed)

    def _on_sign_out_complete(self, success: bool, message: str | None) -> bool:
        if success:
            self._auth_signed_in = False
            self.apple_id_entry.set_text("")
            self.apple_id_entry.set_placeholder_text("Not signed in")
            self.apple_id_entry.set_tooltip_text(None)
            self.sign_out_button.set_sensitive(False)
        else:
            self.sign_out_button.set_sensitive(self._auth_signed_in)
            self._show_message(
                "Could not sign out",
                message or "Xloader could not end the Apple ID session.",
            )
        return GLib.SOURCE_REMOVE

    def _show_message(self, title: str, detail: str) -> None:
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(detail)
        dialog.set_buttons(["OK"])
        dialog.set_default_button(0)
        dialog.show(self)

    def _choose_ipa_file(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserNative.new(
            "Choose an IPA file",
            self,
            Gtk.FileChooserAction.OPEN,
            "_Open",
            "_Cancel",
        )
        ipa_filter = Gtk.FileFilter()
        ipa_filter.set_name("iOS app packages (*.ipa)")
        ipa_filter.add_pattern("*.ipa")
        ipa_filter.add_pattern("*.IPA")
        dialog.add_filter(ipa_filter)
        dialog.connect("response", self._on_ipa_file_selected)
        dialog.show()

    def _on_ipa_file_selected(
        self,
        dialog: Gtk.FileChooserNative,
        response: int,
    ) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            selected_file = dialog.get_file()
            if selected_file is not None:
                filename = selected_file.get_basename()
                if filename:
                    self.ipa_name_label.set_text(Path(filename).stem)
        dialog.destroy()
