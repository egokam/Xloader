"""
window.py — Sideloadly-style desktop window, fixed 800x427, frameless with a
custom (macOS-like) title bar.

Requirements:   pip install PySide6
Run:            python window.py
Styling:        styles.css (Qt stylesheet) next to this file.

Every element is placed with absolute pixel coordinates to match the design.
Hook your backend into the "BACKEND HOOKS" section at the bottom of
SideloadlyWindow.
"""
import math
import sys
from pathlib import Path

from PySide6.QtCore import Property, QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QPainter,
                           QPainterPath, QPen, QPolygonF, QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QLabel,
                               QPushButton, QWidget)

WIDTH, HEIGHT = 800, 427
TITLEBAR_H = 38
STYLESHEET = Path(__file__).with_name("styles.css")
APP_TITLE = "Sideloadly! v0.60"
PURPLE = QColor("#5b57d1")
AA = QPainter.RenderHint.Antialiasing


# ============================================================================
#  Vector icons (drawn around the origin; caller translates to the centre)
# ============================================================================
def _pen(color, width=1.8):
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
    flag = QPolygonF([QPointF(-5, -8), QPointF(7, -8), QPointF(4, -3.5),
                      QPointF(7, 1), QPointF(-5, 1)])
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
    head = QPolygonF([QPointF(px + tx * 4.4, py + ty * 4.4),
                      QPointF(px + nx * 3.8, py + ny * 3.8),
                      QPointF(px - nx * 3.8, py - ny * 3.8)])
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
    "gear": draw_gear, "link": draw_link, "phone": draw_phone,
    "eye": draw_eye_slash, "people": draw_people, "flag": draw_flag,
    "refresh": draw_refresh, "updown": draw_updown,
}


# ============================================================================
#  Custom widgets
# ============================================================================
class IconButton(QPushButton):
    """QPushButton (styled by CSS) with a vector icon painted on top.
    Icon colour comes from CSS:  qproperty-iconColor: #rrggbb;"""

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
        super().paintEvent(event)  # CSS background / border / text
        p = QPainter(self)
        p.setRenderHint(AA)
        if not self.isEnabled():
            p.setOpacity(0.35)
        p.translate(self.width() / 2 + self._dx, self.height() / 2)
        ICONS[self._kind](p, self._icon_color)


class PurpleCombo(QComboBox):
    """Combo box with the purple macOS-style popup button painted on the right."""

    def __init__(self, chevrons="updown", btn_w=21, margin_x=3, margin_y=2, parent=None):
        super().__init__(parent)
        self._chev, self._bw, self._mx, self._my = chevrons, btn_w, margin_x, margin_y
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
    """Left icon box. Placeholder = blue tile with a white tilted square.
    Call set_pixmap(QPixmap) to show a real IPA icon instead."""

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
        # small badge, top-left
        p.setPen(_pen(QColor("white"), 1.4))
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(QRectF(7, 8, 14, 11), 2.5, 2.5)
        p.setBrush(QColor("white"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(11.5, 12), 1.4, 1.4)
        p.drawEllipse(QPointF(17, 15.5), 1.1, 1.1)


class BrandIcon(QWidget):
    """20x20 round social icons (simplified glyphs — swap for real assets)."""

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self._kind = kind
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(AA)
        white = QColor("white")
        p.setPen(Qt.PenStyle.NoPen)
        bg = {"twitter": "#1d9bf0", "reddit": "#f2402d", "patreon": "#f96854"}[self._kind]
        p.setBrush(QColor(bg))
        p.drawEllipse(QRectF(0, 0, 20, 20))
        p.translate(10, 10)
        p.setBrush(white)
        if self._kind == "twitter":
            p.drawEllipse(QPointF(-0.8, 1.8), 5, 3.2)
            p.drawEllipse(QPointF(3.2, -1.6), 2.6, 2.6)
            p.drawPolygon(QPolygonF([QPointF(5.2, -2.4), QPointF(8, -1.6), QPointF(5.4, -0.8)]))
            p.drawPolygon(QPolygonF([QPointF(-4.5, 2.5), QPointF(-8, 4.5), QPointF(-4, 4.5)]))
        elif self._kind == "reddit":
            p.drawEllipse(QPointF(0, 2), 6.6, 4.4)
            p.drawEllipse(QPointF(-6, -0.6), 1.6, 1.6)
            p.drawEllipse(QPointF(6, -0.6), 1.6, 1.6)
            p.drawEllipse(QPointF(4.6, -5.6), 1.3, 1.3)
            p.setPen(_pen(white, 1.0))
            p.drawLine(QPointF(0, -2.4), QPointF(1.4, -5.4))
            p.drawLine(QPointF(1.4, -5.4), QPointF(4.4, -5.6))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(bg))
            p.drawEllipse(QPointF(-2.4, 1.2), 1.1, 1.1)
            p.drawEllipse(QPointF(2.4, 1.2), 1.1, 1.1)
        else:  # patreon
            p.drawRect(QRectF(-5.2, -6, 2.4, 12))
            p.drawEllipse(QPointF(1.6, -1.8), 4.2, 4.2)


class ClickLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


# ============================================================================
#  Main window
# ============================================================================
class SideloadlyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)
        self._build()

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _place(widget, x, y, w, h):
        widget.setGeometry(x, y, w, h)
        return widget

    def _label(self, parent, name, text, x, y, w, h, align=Qt.AlignmentFlag.AlignLeft):
        lbl = QLabel(text, parent)
        lbl.setObjectName(name)
        lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        return self._place(lbl, x, y, w, h)

    # ---- layout -----------------------------------------------------------
    def _build(self):
        root = QFrame(self)
        root.setObjectName("root")
        root.setGeometry(0, 0, WIDTH, HEIGHT)

        # Title bar ---------------------------------------------------------
        bar = QFrame(root)
        bar.setObjectName("titleBar")
        bar.setGeometry(1, 1, WIDTH - 2, TITLEBAR_H - 1)

        title = self._label(bar, "titleLabel", APP_TITLE, 0, 0, WIDTH - 2, TITLEBAR_H - 1,
                            Qt.AlignmentFlag.AlignHCenter)
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

        # Left: IPA icon + file name ---------------------------------------
        self.ipa_icon = self._place(IpaIcon(root), 24, 69, 115, 143)
        self.lbl_filename = self._label(root, "fileName", "", 14, 243, 135, 44,
                                        Qt.AlignmentFlag.AlignHCenter)
        self.set_filename("Delta-2.705.924.ipa")

        # Top-right small buttons ------------------------------------------
        self.lbl_device = self._label(root, "fieldLabel", "iDevice:", 175, 62, 140, 22)
        self.btn_count = self._place(IconButton("people", dx=-18, parent=root), 607, 62, 75, 25)
        self.btn_count.setObjectName("countBtn")
        self.btn_count.setText("0")
        self.btn_flag = self._place(IconButton("flag", parent=root), 704, 62, 64, 25)
        self.btn_flag.setObjectName("flagBtn")

        # Device row --------------------------------------------------------
        self.combo_device = PurpleCombo("updown", btn_w=20, margin_x=3, margin_y=2, parent=root)
        self.combo_device.setObjectName("deviceCombo")
        self.combo_device.addItem("Apple Silicon (********_****************)")
        self._place(self.combo_device, 183, 124, 404, 25)

        self.btn_gear = self._place(IconButton("gear", parent=root), 608, 119, 38, 34)
        self.btn_gear.setObjectName("gearBtn")
        self.btn_link = self._place(IconButton("link", parent=root), 654, 119, 38, 34)
        self.btn_link.setObjectName("linkBtn")
        self.btn_link.setEnabled(False)
        self.btn_phone = self._place(IconButton("phone", parent=root), 698, 119, 36, 34)
        self.btn_phone.setObjectName("phoneBtn")
        self.btn_eye = self._place(IconButton("eye", parent=root), 743, 119, 36, 34)
        self.btn_eye.setObjectName("eyeBtn")

        # Apple ID row ------------------------------------------------------
        self.lbl_appleid = self._label(root, "fieldLabel", "Apple ID:", 175, 173, 140, 22)
        self.combo_appleid = PurpleCombo("down", btn_w=22, margin_x=3, margin_y=3, parent=root)
        self.combo_appleid.setObjectName("appleIdCombo")
        self.combo_appleid.setEditable(True)
        self.combo_appleid.lineEdit().setObjectName("appleIdEdit")
        self.combo_appleid.addItem("******@*****.*** [* * *** *** *********]")
        self._place(self.combo_appleid, 176, 209, 601, 28)

        # Advanced Options --------------------------------------------------
        self.btn_advanced = self._place(QPushButton("Advanced Options", root), 176, 259, 601, 26)
        self.btn_advanced.setObjectName("advancedBtn")

        # Bottom row --------------------------------------------------------
        self.btn_refresh = self._place(IconButton("refresh", parent=root), 14, 311, 34, 33)
        self.btn_refresh.setObjectName("refreshBtn")
        self.btn_start = self._place(QPushButton("Start", root), 69, 314, 715, 27)
        self.btn_start.setObjectName("startBtn")
        self.btn_swap = self._place(IconButton("updown", parent=root), 752, 373, 35, 35)
        self.btn_swap.setObjectName("swapBtn")
        for b in (self.btn_advanced, self.btn_start):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Social links ------------------------------------------------------
        self._place(BrandIcon("twitter", root), 181, 374, 20, 20)
        self.link_twitter = self._social(root, "@Sideloadly", 207, 375, 112)
        self._place(BrandIcon("reddit", root), 314, 374, 20, 20)
        self.link_reddit = self._social(root, "r/Sideloadly", 337, 375, 102)
        self._place(BrandIcon("patreon", root), 439, 374, 20, 20)
        self.link_patreon = self._social(root, "Sideloadly", 466, 375, 90)

        # TODO: replace with your real URLs
        self.link_twitter.clicked.connect(lambda: self._open("https://twitter.com/"))
        self.link_reddit.clicked.connect(lambda: self._open("https://reddit.com/"))
        self.link_patreon.clicked.connect(lambda: self._open("https://patreon.com/"))

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

    # ---- frameless window dragging (title bar only) -----------------------
    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and event.position().y() < TITLEBAR_H and self.windowHandle()):
            self.windowHandle().startSystemMove()
        super().mousePressEvent(event)

    # ========================================================================
    #  BACKEND HOOKS — connect your app here
    # ========================================================================
    # Signals you can connect to, e.g.:
    #   self.btn_start.clicked.connect(self.on_start)
    #   self.btn_advanced.clicked.connect(...)
    #   self.btn_refresh.clicked.connect(...)      # rescan devices
    #   self.btn_gear / btn_link / btn_phone / btn_eye / btn_count / btn_flag
    #   self.btn_swap.clicked.connect(...)
    #   self.combo_device.currentIndexChanged / self.combo_appleid.currentTextChanged

    def set_filename(self, name: str):
        """Shows the file name wrapped after 13 chars like the design."""
        self.lbl_filename.setText(name[:13] + ("\n" + name[13:] if len(name) > 13 else ""))

    def set_ipa_icon(self, pixmap):
        self.ipa_icon.set_pixmap(pixmap)

    def set_devices(self, devices):
        self.combo_device.clear()
        self.combo_device.addItems(devices)

    def set_apple_ids(self, ids):
        self.combo_appleid.clear()
        self.combo_appleid.addItems(ids)

    def set_device_count(self, n: int):
        self.btn_count.setText(str(n))


def main():
    app = QApplication(sys.argv)
    font = QFont()
    font.setFamilies(["SF Pro Text", "Helvetica Neue", "Segoe UI", "Arial"])
    font.setPixelSize(15)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET.read_text(encoding="utf-8"))
    win = SideloadlyWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
