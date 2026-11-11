from __future__ import annotations

import math
import os
import threading
from pathlib import Path

from PySide6.QtCore import Property, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QWidget,
)

from .device import DeviceInfo, DeviceService
from .xtool import AuthStatus, XToolService

WIDTH, HEIGHT = 800, 427
TITLEBAR_H = 38
STYLESHEET = Path(__file__).parent / "assets" / "style.css"
APP_TITLE = "Xloader"
PURPLE = QColor("#5b57d1")
AA = QPainter.RenderHint.Antialiasing

NO_DEVICE_TEXT = "No device detected, connect your iDevice with a cable."


def _pen(color, width: float = 1.8):
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def draw_gear(p, c):
    path = QPainterPath()
    path.addEllipse(QPointF(0, 0), 6.2, 6.2)
    for i in range(4):
        tooth = QPainterPath()
        tooth.addRoundedRect(QRectF(-2.2, -8.6, 4.4, 17.2), 1, 1)
        path = path.united(QTransform().rotate(45 * i).map(tooth))
    hole = QPainterPath()
    hole.addEllipse(QPointF(0, 0), 2.6, 2.6)
    p.fillPath(path.subtracted(hole), c)


def draw_link(p, c):
    p.setPen(_pen(c, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.rotate(-45)
    p.drawRoundedRect(QRectF(-10, -3.6, 11, 7.2), 3.6, 3.6)
    p.drawRoundedRect(QRectF(-1, -3.6, 11, 7.2), 3.6, 3.6)


def draw_phone(p, c):
    p.setPen(_pen(c, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-5, -8.5, 10, 17), 2.2, 2.2)
    p.drawLine(QPointF(-1.8, 6), QPointF(1.8, 6))


def draw_eye_slash(p, c):
    path = QPainterPath()
    path.moveTo(-9.5, 0)
    path.quadTo(0, -10, 9.5, 0)
    path.quadTo(0, 10, -9.5, 0)
    p.setPen(_pen(c, 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.drawEllipse(QPointF(0, 0), 2.6, 2.6)
    p.drawLine(QPointF(-8, -8), QPointF(8, 8))


def draw_people(p, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(-3.5, -3.6), 3, 3)
    p.drawEllipse(QPointF(4.2, -3.0), 2.5, 2.5)
    body = QPainterPath()
    body.addRoundedRect(QRectF(-8.5, 0.5, 10, 7), 3.5, 3.5)
    body.addRoundedRect(QRectF(2, 1.5, 7, 6), 3, 3)
    p.drawPath(body)


def draw_flag(p, c):
    p.setPen(_pen(c, 1.8))
    p.drawLine(QPointF(-5, -8), QPointF(-5, 8))
    flag = QPolygonF(
        [
            QPointF(-5, -8),
            QPointF(7, -8),
            QPointF(4, -3.5),
            QPointF(7, 1),
            QPointF(-5, 1),
        ]
    )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPolygon(flag)


def draw_refresh(p, c):
    r = 7.0
    p.setPen(_pen(c, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(-r, -r, 2 * r, 2 * r), 40 * 16, 280 * 16)
    a = math.radians(320)
    px, py = r * math.cos(a), -r * math.sin(a)
    tx, ty = -math.sin(a), -math.cos(a)
    nx, ny = -ty, tx
    head = QPolygonF(
        [
            QPointF(px + tx * 4.4, py + ty * 4.4),
            QPointF(px + nx * 3.8, py + ny * 3.8),
            QPointF(px - nx * 3.8, py - ny * 3.8),
        ]
    )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPolygon(head)


def draw_updown(p, c):
    p.setPen(_pen(c, 2.0))
    p.drawLine(QPointF(-3.5, 8), QPointF(-3.5, -4))
    p.drawLine(QPointF(3.5, -8), QPointF(3.5, 4))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(-3.5, -9.5), QPointF(-7.8, -3.5), QPointF(0.8, -3.5)]))
    p.drawPolygon(QPolygonF([QPointF(3.5, 9.5), QPointF(-0.8, 3.5), QPointF(7.8, 3.5)]))


ICONS = {
    "gear": draw_gear,
    "link": draw_link,
    "phone": draw_phone,
    "eye": draw_eye_slash,
    "people": draw_people,
    "flag": draw_flag,
    "refresh": draw_refresh,
    "updown": draw_updown,
}


class IconButton(QPushButton):
    def __init__(self, kind, dx=0.0, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._dx = dx
        self._icon_color = QColor("#f0f0f0")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _get_icon_color(self):
        return self._icon_color

    def _set_icon_color(self, color):
        self._icon_color = QColor(color)
        self.update()

    iconColor = Property(QColor, _get_icon_color, _set_icon_color)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(AA)
        if not self.isEnabled():
            p.setOpacity(0.35)
        p.translate(self.width() / 2 + self._dx, self.height() / 2)
        ICONS[self._kind](p, self._icon_color)


class PurpleCombo(QComboBox):
    def __init__(self, chevrons="updown", btn_w=21, margin_x=3, margin_y=2, parent=None):
        super().__init__(parent)
        self._chev = chevrons
        self._bw = btn_w
        self._mx = margin_x
        self._my = margin_y
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(AA)
        w, h = self.width(), self.height()
        rect = QRectF(w - self._bw - self._mx, self._my, self._bw, h - 2 * self._my)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(PURPLE)
        p.drawRoundedRect(rect, 4, 4)
        p.translate(rect.center())
        p.setPen(_pen(QColor("white"), 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self._chev == "updown":
            p.drawPolyline(QPolygonF([QPointF(-3, -1.6), QPointF(0, -4.6), QPointF(3, -1.6)]))
            p.drawPolyline(QPolygonF([QPointF(-3, 1.6), QPointF(0, 4.6), QPointF(3, 1.6)]))
        else:
            p.drawPolyline(QPolygonF([QPointF(-3.6, -1.6), QPointF(0, 2.0), QPointF(3.6, -1.6)]))


class IpaIcon(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ipaBox")
        self._pixmap = None

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHints(AA | QPainter.RenderHint.SmoothPixmapTransform)
        tile = QRectF(7, 18, 104, 106)
        if self._pixmap is not None:
            p.drawPixmap(tile.toRect(), self._pixmap)
        else:
            p.fillRect(tile, QColor("#3f5bff"))
            p.save()
            p.translate(tile.center())
            p.rotate(12)
            outer = QPainterPath()
            outer.addRoundedRect(QRectF(-28, -28, 56, 56), 5, 5)
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(-10, -10, 20, 20), 1.5, 1.5)
            p.fillPath(outer.subtracted(hole), QColor("white"))
            p.restore()
        p.setPen(_pen(QColor("white"), 1.4))
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(QRectF(7, 8, 14, 11), 2.5, 2.5)
        p.setBrush(QColor("white"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(11.5, 12), 1.4, 1.4)
        p.drawEllipse(QPointF(17, 15.5), 1.1, 1.1)


class BrandIcon(QWidget):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self._kind = kind

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(AA)
        bg = QColor("#f5f5f6")
        white = QColor("#ffffff")
        p.translate(self.width() / 2, self.height() / 2)
        if self._kind == "twitter":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(white)
            p.drawEllipse(QPointF(0, 0), 6.2, 6.2)
            p.setPen(_pen(QColor("#2c2c2c"), 1.1))
            p.drawLines([QPointF(-2.8, 2.0), QPointF(-0.2, -2.2), QPointF(4.2, -2.2)])
            p.drawLine(QPointF(-2.2, -1.2), QPointF(0.0, 2.0))
        elif self._kind == "reddit":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(white)
            p.drawEllipse(QPointF(0, 0), 7.0, 7.0)
            p.setBrush(QColor("#f8f8f8"))
            p.drawEllipse(QPointF(-2.4, 1.2), 1.1, 1.1)
            p.drawEllipse(QPointF(2.4, 1.2), 1.1, 1.1)
            p.setBrush(bg)
            p.drawEllipse(QPointF(0, 2), 5.2, 3.2)
            p.setPen(_pen(QColor("#2c2c2c"), 1.1))
            p.drawLine(QPointF(0, -2.4), QPointF(1.4, -5.4))
            p.drawLine(QPointF(1.4, -5.4), QPointF(4.4, -5.6))
        else:
            p.drawRect(QRectF(-5.2, -6, 2.4, 12))
            p.drawEllipse(QPointF(1.6, -1.8), 4.2, 4.2)


class ClickLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class SideloadlyWindow(QWidget):
    def __init__(self, development_preview: bool = False):
        super().__init__()
        self._development_preview = development_preview
        self._device_service = DeviceService()
        self._xtool_service = XToolService()
        self._devices: list[DeviceInfo] = []
        self._selected_device: DeviceInfo | None = None
        self._hide_sensitive = True
        self._selected_ipa_path: str | None = None
        self._install_running = False
        self._install_output: list[str] = []
        self._status_text = "Ready"
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)
        self._build()
        self._refresh_devices()
        self._refresh_auth_status()
        self._device_timer = QTimer(self)
        self._device_timer.timeout.connect(self._refresh_devices)
        self._device_timer.start(3000)

    @staticmethod
    def _place(widget, x, y, w, h):
        widget.setGeometry(x, y, w, h)
        return widget

    def _label(self, parent, name, text, x, y, w, h, align=Qt.AlignmentFlag.AlignLeft):
        lbl = QLabel(text, parent)
        lbl.setObjectName(name)
        lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        return self._place(lbl, x, y, w, h)

    def _build(self):
        root = QFrame(self)
        root.setObjectName("root")
        root.setGeometry(0, 0, WIDTH, HEIGHT)

        bar = QFrame(root)
        bar.setObjectName("titleBar")
        bar.setGeometry(1, 1, WIDTH - 2, TITLEBAR_H - 1)

        title = self._label(
            bar,
            "titleLabel",
            APP_TITLE,
            0,
            0,
            WIDTH - 2,
            TITLEBAR_H - 1,
            Qt.AlignmentFlag.AlignHCenter,
        )
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.btn_close = QPushButton(bar)
        self.btn_close.setObjectName("trafficClose")
        self.btn_min = QPushButton(bar)
        self.btn_min.setObjectName("trafficMin")
        self.btn_zoom = QPushButton(bar)
        self.btn_zoom.setObjectName("trafficZoom")
        self.btn_zoom.setEnabled(False)
        for btn, x in ((self.btn_close, 15), (self.btn_min, 36), (self.btn_zoom, 57)):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._place(btn, x, 12, 12, 12)
        self.btn_close.clicked.connect(self.close)
        self.btn_min.clicked.connect(self.showMinimized)

        self.ipa_icon = self._place(IpaIcon(root), 24, 69, 115, 143)
        self.ipa_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ipa_icon.mousePressEvent = self._ipa_click
        self.lbl_filename = self._label(root, "fileName", "", 14, 243, 135, 44, Qt.AlignmentFlag.AlignHCenter)
        self.set_filename("")

        self.lbl_device = self._label(root, "fieldLabel", "iDevice:", 175, 62, 140, 22)
        self.btn_count = self._place(IconButton("people", dx=-18, parent=root), 607, 62, 75, 25)
        self.btn_count.setObjectName("countBtn")
        self.btn_count.setText("0")
        self.btn_flag = self._place(IconButton("flag", parent=root), 704, 62, 64, 25)
        self.btn_flag.setObjectName("flagBtn")
        self.btn_count.clicked.connect(self._refresh_devices)
        self.btn_flag.clicked.connect(self._show_engine_status)

        self.combo_device = PurpleCombo("updown", btn_w=20, margin_x=3, margin_y=2, parent=root)
        self.combo_device.setObjectName("deviceCombo")
        self.combo_device.addItem(NO_DEVICE_TEXT)
        self._place(self.combo_device, 183, 124, 404, 25)
        self.combo_device.currentIndexChanged.connect(self._on_device_selected)

        self.btn_gear = self._place(IconButton("gear", parent=root), 608, 119, 38, 34)
        self.btn_gear.setObjectName("gearBtn")
        self.btn_link = self._place(IconButton("link", parent=root), 654, 119, 38, 34)
        self.btn_link.setObjectName("linkBtn")
        self.btn_phone = self._place(IconButton("phone", parent=root), 698, 119, 36, 34)
        self.btn_phone.setObjectName("phoneBtn")
        self.btn_eye = self._place(IconButton("eye", parent=root), 743, 119, 36, 34)
        self.btn_eye.setObjectName("eyeBtn")
        self.btn_link.clicked.connect(self._copy_device_udid)
        self.btn_phone.clicked.connect(self._repair_pairing)
        self.btn_eye.clicked.connect(self._toggle_device_privacy)
        self.btn_gear.clicked.connect(self._show_device_menu)

        self.lbl_appleid = self._label(root, "fieldLabel", "Apple ID:", 175, 173, 140, 22)
        self.combo_appleid = PurpleCombo("down", btn_w=22, margin_x=3, margin_y=3, parent=root)
        self.combo_appleid.setObjectName("appleIdCombo")
        self.combo_appleid.setEditable(True)
        self.combo_appleid.lineEdit().setObjectName("appleIdEdit")
        self.combo_appleid.addItem("Not signed in")
        self._place(self.combo_appleid, 176, 209, 601, 28)

        self.btn_advanced = self._place(QPushButton("Advanced Options", root), 176, 259, 601, 26)
        self.btn_advanced.setObjectName("advancedBtn")
        self.btn_advanced.clicked.connect(self._show_advanced_options)

        self.btn_refresh = self._place(IconButton("refresh", parent=root), 14, 311, 34, 33)
        self.btn_refresh.setObjectName("refreshBtn")
        self.btn_refresh.clicked.connect(self._refresh_all)

        self.btn_start = self._place(QPushButton("Start", root), 69, 314, 715, 27)
        self.btn_start.setObjectName("startBtn")
        self.btn_start.clicked.connect(self._start_install)
        self.btn_swap = self._place(IconButton("updown", parent=root), 752, 373, 35, 35)
        self.btn_swap.setObjectName("swapBtn")
        self.btn_swap.clicked.connect(self._toggle_install_mode)

        self.status_label = self._label(root, "statusLabel", "Ready", 176, 290, 600, 18)
        self.status_label.setVisible(True)

        for b in (self.btn_advanced, self.btn_start):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._place(BrandIcon("twitter", root), 181, 374, 20, 20)
        self.link_twitter = self._social(root, "@Xloader", 207, 375, 112)
        self._place(BrandIcon("reddit", root), 314, 374, 20, 20)
        self.link_reddit = self._social(root, "r/Xloader", 337, 375, 102)
        self._place(BrandIcon("patreon", root), 439, 374, 20, 20)
        self.link_patreon = self._social(root, "Xloader", 466, 375, 90)

        self.link_twitter.clicked.connect(lambda: self._open("https://github.com/egokam/Xloader"))
        self.link_reddit.clicked.connect(lambda: self._open("https://github.com/egokam/Xloader/discussions"))
        self.link_patreon.clicked.connect(lambda: self._open("https://xtool.sh/"))

        self._update_action_state()
        self._set_status("Ready")

    def _social(self, parent, text, x, y, w):
        lbl = ClickLabel(text, parent)
        lbl.setObjectName("socialLink")
        font = lbl.font()
        font.setUnderline(True)
        lbl.setFont(font)
        lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        return self._place(lbl, x, y, w, 20)

    @staticmethod
    def _open(url):
        QDesktopServices.openUrl(QUrl(url))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < TITLEBAR_H and self.windowHandle():
            self.windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def _ipa_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._choose_ipa_file()

    def set_filename(self, value: str) -> None:
        safe_value = value or ""
        self.lbl_filename.setText(safe_value)
        self.lbl_filename.setProperty("empty", not bool(safe_value))
        self.lbl_filename.style().unpolish(self.lbl_filename)
        self.lbl_filename.style().polish(self.lbl_filename)

    def _set_status(self, text: str) -> None:
        self._status_text = text or "Ready"
        self.status_label.setText(self._status_text)

    def _show_device_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Refresh connected devices", self._refresh_devices)
        menu.addAction("Repair device pairing", self._repair_pairing)
        menu.addAction("Copy device identifier", self._copy_device_udid)
        menu.exec(self.btn_gear.mapToGlobal(self.btn_gear.rect().bottomLeft()))

    def _show_advanced_options(self) -> None:
        QMessageBox.information(
            self,
            "Advanced options",
            "Connection: USB\nSigning: xtool automatic\nHide device IDs is enabled by default.",
        )

    def _toggle_install_mode(self) -> None:
        self._set_status("Refresh mode selected")

    def _refresh_all(self) -> None:
        self._refresh_devices()
        self._refresh_auth_status()

    def _refresh_devices(self) -> None:
        def worker() -> None:
            devices = self._device_service.list_usb_devices()
            QTimer.singleShot(0, lambda: self._apply_devices(devices))

        threading.Thread(target=worker, name="xloader-devices", daemon=True).start()

    def _apply_devices(self, devices: list[DeviceInfo]) -> None:
        self._devices = devices
        self.btn_count.setText(str(len(devices)))
        if not devices:
            self.combo_device.clear()
            self.combo_device.addItem(NO_DEVICE_TEXT)
            self._selected_device = None
            self._update_action_state()
            return

        current = self._selected_device.udid if self._selected_device else None
        items = []
        for device in devices:
            label = self._format_device(device)
            items.append(label)
        self.combo_device.blockSignals(True)
        self.combo_device.clear()
        self.combo_device.addItems(items)
        self.combo_device.blockSignals(False)

        if current is not None:
            for idx, device in enumerate(devices):
                if device.udid == current:
                    self.combo_device.setCurrentIndex(idx)
                    break
        else:
            self.combo_device.setCurrentIndex(0)

        self._selected_device = devices[self.combo_device.currentIndex()] if self.combo_device.currentIndex() < len(devices) else None
        self._update_action_state()

    def _on_device_selected(self, index: int) -> None:
        if index < 0 or index >= len(self._devices):
            self._selected_device = None
            self._update_action_state()
            return
        self._selected_device = self._devices[index]
        self._update_action_state()

    def _format_device(self, device: DeviceInfo) -> str:
        identifier = "********" if self._hide_sensitive else device.udid
        return f"{device.name} ({device.model})  {identifier}"

    def _update_action_state(self) -> None:
        has_device = self._selected_device is not None
        self.btn_link.setEnabled(has_device)
        self.btn_phone.setEnabled(has_device)
        self.btn_start.setEnabled(
            has_device and self._selected_ipa_path is not None and self._xtool_service.available and not self._install_running
        )

    def _copy_device_udid(self) -> None:
        device = self._selected_device
        if device is None:
            return
        QApplication.clipboard().setText(device.udid)
        self._set_status(f"Copied device ID for {device.name}")

    def _toggle_device_privacy(self) -> None:
        self._hide_sensitive = not self._hide_sensitive
        self._apply_devices(self._devices)
        self._set_status("Device identifier privacy is now " + ("hidden" if self._hide_sensitive else "visible"))

    def _repair_pairing(self) -> None:
        device = self._selected_device
        if device is None:
            return

        def worker() -> None:
            success, message = self._device_service.repair_pairing(device.udid)
            QTimer.singleShot(0, lambda: self._repair_done(success, message))

        threading.Thread(target=worker, name="xloader-pairing", daemon=True).start()

    def _repair_done(self, success: bool, message: str) -> None:
        status = "Device paired" if success else "Could not pair device"
        QMessageBox.information(self, status, message)
        self._set_status(status)

    def _refresh_auth_status(self) -> None:
        def worker() -> None:
            status = self._xtool_service.auth_status()
            QTimer.singleShot(0, lambda: self._apply_auth_status(status))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_auth_status(self, status: AuthStatus) -> None:
        if status.signed_in:
            value = status.apple_id or "Signed in"
            self.combo_appleid.blockSignals(True)
            self.combo_appleid.clear()
            self.combo_appleid.addItem(value)
            self.combo_appleid.blockSignals(False)
            details = []
            if status.team_id:
                details.append(f"Team ID: {status.team_id}")
            if status.token_expiry:
                details.append(f"Token expiry: {status.token_expiry}")
            self.combo_appleid.setToolTip("\n".join(details) if details else "Signed in")
            self._set_status("Apple account ready")
        else:
            self.combo_appleid.blockSignals(True)
            self.combo_appleid.clear()
            self.combo_appleid.addItem("Not signed in")
            self.combo_appleid.blockSignals(False)
            self.combo_appleid.setToolTip(status.error or "Not signed in")
            self._set_status(status.error or "Apple ID not signed in")

    def _show_engine_status(self) -> None:
        if self._xtool_service.available:
            QMessageBox.information(self, "Signing engine ready", f"Xtool found at:\n{self._xtool_service.executable}")
        else:
            QMessageBox.warning(self, "Signing engine missing", "Xtool is unavailable. Install the bundled runtime or set XLOADER_XTOOL.")

    def _choose_ipa_file(self) -> None:
        ipa_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select IPA",
            str(Path.home()),
            "iOS app (*.ipa)",
        )
        if not ipa_path:
            return
        self._selected_ipa_path = ipa_path
        self.set_filename(Path(ipa_path).name)
        self._set_status(f"Selected {Path(ipa_path).name}")
        self._update_action_state()

    def _start_install(self) -> None:
        if self._install_running:
            return
        if self._selected_device is None:
            QMessageBox.warning(self, "No device selected", "Connect an iPhone via USB and select it before installing.")
            return
        if not self._selected_ipa_path:
            self._choose_ipa_file()
            if not self._selected_ipa_path:
                return
        if not self._xtool_service.available:
            QMessageBox.warning(self, "Xtool unavailable", "The signing engine could not be found. Set XLOADER_XTOOL or install the bundled runtime.")
            return

        self._install_running = True
        self.btn_start.setEnabled(False)
        self.btn_start.setText("Installing…")
        self._install_output = []

        def on_output(line: str) -> None:
            self._install_output.append(line)
            if line:
                QTimer.singleShot(0, lambda: self._set_status(line))

        def on_complete(exit_code: int) -> None:
            QTimer.singleShot(0, lambda: self._install_finished(exit_code))

        self._xtool_service.install_ipa(self._selected_ipa_path, on_output, on_complete)

    def _install_finished(self, exit_code: int) -> None:
        self._install_running = False
        self.btn_start.setEnabled(self._selected_device is not None and self._selected_ipa_path is not None and self._xtool_service.available)
        self.btn_start.setText("Start")
        if exit_code == 0:
            message = f"{Path(self._selected_ipa_path or '').name} was installed successfully."
            QMessageBox.information(self, "Installation complete", message)
            self._set_status("Install complete")
        else:
            details = "\n".join(self._install_output[-6:]) or "Xtool exited before it could finish the install."
            QMessageBox.warning(self, "Could not install app", details)
            self._set_status("Install failed")



MainWindow = SideloadlyWindow


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("Xloader")
    app.setOrganizationName("Xloader")
    app.setStyle("Fusion")
    window = SideloadlyWindow()
    window.show()
    app.exec()
