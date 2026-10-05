from PyQt6.QtWidgets import QPushButton, QWidget, QLineEdit
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor
from constants import DARK
from utils import icon_font
import random

def ibtn(glyph, size=52, px=20, bg=DARK, fg="#fff", cb=None):
    b = QPushButton(glyph); b.setFont(icon_font(px)); b.setFixedSize(size, size)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(f"QPushButton{{background:{bg};color:{fg};border:none;border-radius:{size // 2}px}}"
                    f"QPushButton:hover{{background:#3a3a3c}}")
    if cb: b.clicked.connect(cb)
    return b

def chip(text, cb):
    b = QPushButton(text); b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet("QPushButton{background:#1c1c1e;color:#fff;border:none;border-radius:16px;"
                    "padding:7px 18px;font-size:14px}QPushButton:hover{background:#3a3a3c}")
    b.clicked.connect(cb); return b

class Bar(QWidget):
    changed = pyqtSignal(float)
    def __init__(self, color, r, live=False, ro=False):
        super().__init__(); self.c, self.r, self.live, self.ro = color, r, live, ro
        self.v = self.hov = 0; self.setMouseTracking(True); self.setFixedHeight(r * 2)
    def set(self, v): self.v = max(0, min(1, v)); self.update()
    def mouseMoveEvent(self, e):
        self.hov = max(0, min(1, e.pos().x() / self.width())); self.update()
        if e.buttons() & Qt.MouseButton.LeftButton and not self.ro:
            self.set(self.hov)
            if self.live: self.changed.emit(self.hov)
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.ro:
            self.hov = max(0, min(1, e.pos().x() / self.width()))
            self.set(self.hov)
            self.changed.emit(self.hov if self.live else self.v)
    def leaveEvent(self, e): self.hov = 0; self.update()
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#3a3a3c")); p.drawRoundedRect(0, (self.height() - 8) // 2, self.width(), 8, 4, 4)
        p.setBrush(QColor(self.c)); w = int(self.v * self.width())
        p.drawRoundedRect(0, (self.height() - 8) // 2, w, 8, 4, 4)
        if not self.ro and self.cursor() != Qt.CursorShape.PointingHandCursor:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

class Eq(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedSize(24, 16); self.playing = False
        self.bars = [random.random() for _ in range(4)]; self.t = QTimer(self)
        self.t.timeout.connect(self.tick); self.t.start(100)
    def tick(self):
        if self.playing: self.bars = [min(1, max(0.1, b + random.uniform(-0.3, 0.3))) for b in self.bars]; self.update()
    def paintEvent(self, e):
        if not self.playing: return
        p = QPainter(self); p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#0a84ff"))
        for i, b in enumerate(self.bars):
            h = b * 16; p.drawRoundedRect(i * 6, int(16 - h), 4, int(h), 2, 2)

class Mascot(QWidget):
    def __init__(self, s=24):
        super().__init__(); self.setFixedSize(s, s); self.s = s
        self.blink = False
        import random; self.rng = random
        self.t = QTimer(self); self.t.timeout.connect(self.update); self.t.start(50)
        self.blink_t = QTimer(self); self.blink_t.timeout.connect(self.do_blink)
        self.blink_t.start(self.rng.randint(2000, 5000))
    def do_blink(self):
        self.blink = True; QTimer.singleShot(150, lambda: setattr(self, 'blink', False))
        self.blink_t.start(self.rng.randint(2000, 6000))
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#fff")); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, self.s, self.s)
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QCursor
        g = self.mapToGlobal(QPoint(self.s//2, self.s//2)); m = QCursor.pos()
        dx, dy = m.x() - g.x(), m.y() - g.y()
        dist = (dx**2 + dy**2)**0.5; max_d = self.s * 0.12
        if dist > 0: ex, ey = (dx / dist) * min(dist/60, max_d), (dy / dist) * min(dist/60, max_d)
        else: ex = ey = 0
        p.setBrush(QColor("#000")); y, d = self.s * 0.35 + ey, self.s * 0.15
        if self.blink:
            p.drawRoundedRect(QRectF(self.s * 0.3 + ex, y + d/2 - 1, d, 2), 1, 1)
            p.drawRoundedRect(QRectF(self.s * 0.7 - d + ex, y + d/2 - 1, d, 2), 1, 1)
        else:
            p.drawEllipse(QRectF(self.s * 0.3 + ex, y, d, d)); p.drawEllipse(QRectF(self.s * 0.7 - d + ex, y, d, d))


class Input(QLineEdit):
    nav, enter, esc = pyqtSignal(int), pyqtSignal(), pyqtSignal()
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down): self.nav.emit(-1 if e.key() == Qt.Key.Key_Up else 1)
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter): self.enter.emit()
        elif e.key() == Qt.Key.Key_Escape: self.esc.emit()
        else: super().keyPressEvent(e)
