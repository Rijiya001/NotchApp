import os

with open(r'd:\QUICK TASKBAR\notch1.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. constants.py
constants_code = """BLUE, GRAY, DARK = "#0a84ff", "#8e8e93", "#1c1c1e"
G = dict(prev="\\uE892", next="\\uE893", pause="\\uE769", play="\\uE768", vol="\\uE767", mute="\\uE74F",
         timer="\\uE916", grid="\\uE80A", cog="\\uE713", mixer="\\uE9E9", music="\\uE8D6", x="\\uE711",
         lock="\\uE72E", web="\\uE774", search="\\uE721", back="\\uE72B")
"""

# 2. utils.py
utils_code = """import os, winreg, ctypes
from pathlib import Path
from PyQt6.QtGui import QFont, QPixmap, QPainter, QPainterPath
from PyQt6.QtCore import Qt

def icon_font(px):
    f = QFont(); f.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"]); f.setPixelSize(px); return f

def rounded(pm, size, r):
    pm = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size); out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath(); path.addRoundedRect(0, 0, size, size, r, r); p.setClipPath(path)
    p.drawPixmap((size - pm.width()) // 2, (size - pm.height()) // 2, pm); p.end(); return out

def mmss(s): s = max(int(s), 0); return f"{s // 60}:{s % 60:02d}"

def force_focus(hwnd):
    u = ctypes.windll.user32
    u.SystemParametersInfoW(0x2001, 0, 0, 2)
    u.SetForegroundWindow(hwnd)
    u.SystemParametersInfoW(0x2001, 200000, 0, 2)

def autostart(enable=None):
    import sys
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Run", 0, winreg.KEY_ALL_ACCESS)
    if enable is None:
        try: return winreg.QueryValueEx(k, "Notch")[0] != ""
        except FileNotFoundError: return False
    if enable: winreg.SetValueEx(k, "Notch", 0, winreg.REG_SZ, sys.executable + ' "' + os.path.abspath(sys.argv[0]) + '"')
    else:
        try: winreg.DeleteValue(k, "Notch")
        except FileNotFoundError: pass

def build_index():
    seen = {}
    for shell_folder in (r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders",
                         r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders"):
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                k = winreg.OpenKey(root, shell_folder)
                for v in ("Common Programs", "Programs"):
                    try:
                        p = Path(winreg.QueryValueEx(k, v)[0])
                        if p.exists():
                            for f in p.rglob("*.lnk"):
                                n = f.stem
                                if n.lower() not in seen: seen[n.lower()] = (n, str(f))
                    except Exception: pass
            except Exception: pass
    
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\\Classes")
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                n = winreg.EnumKey(k, i)
                if n.startswith("AppX"):
                    p = Path(winreg.QueryValueEx(winreg.OpenKey(k, f"{n}\\\\Application"), "ApplicationName")[0])
                    if p.name: seen[p.name.lower()] = (p.name, str(p))
            except Exception: pass
    except Exception: pass
    return list(seen.values())

SETTINGS = [("Wi-Fi", "ms-settings:network-wifi"), ("Bluetooth", "ms-settings:bluetooth"),
            ("Display", "ms-settings:display"), ("Sound", "ms-settings:sound"),
            ("Apps & features", "ms-settings:appsfeatures"), ("Windows Update", "ms-settings:windowsupdate"),
            ("Personalization", "ms-settings:personalization"), ("Battery", "ms-settings:batterysaver")]
"""

# 3. ui.py
ui_code = """from PyQt6.QtWidgets import QPushButton, QWidget, QLineEdit
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
        if self.live and e.buttons() & Qt.MouseButton.LeftButton and not self.ro: self.changed.emit(self.hov)
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.ro:
            self.hov = max(0, min(1, e.pos().x() / self.width()))
            if not self.live: self.set(self.hov); self.changed.emit(self.v)
            else: self.changed.emit(self.hov)
    def leaveEvent(self, e): self.hov = 0; self.update()
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#3a3a3c")); p.drawRoundedRect(0, (self.height() - 8) / 2, self.width(), 8, 4, 4)
        p.setBrush(QColor(self.c)); w = self.v * self.width()
        p.drawRoundedRect(0, (self.height() - 8) / 2, w, 8, 4, 4)
        if self.hov > 0 and not self.ro:
            p.setBrush(QColor("#fff"))
            p.drawEllipse(QRectF(self.hov * self.width() - self.r, 0, self.r * 2, self.r * 2))

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
        super().__init__(); self.setFixedSize(s, s)
        self.s = s
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#fff")); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, self.s, self.s)
        p.setBrush(QColor("#000")); y, d = self.s * 0.35, self.s * 0.15
        p.drawEllipse(QRectF(self.s * 0.3, y, d, d)); p.drawEllipse(QRectF(self.s * 0.7 - d, y, d, d))

class Input(QLineEdit):
    nav, enter, esc = pyqtSignal(int), pyqtSignal(), pyqtSignal()
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down): self.nav.emit(-1 if e.key() == Qt.Key.Key_Up else 1)
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter): self.enter.emit()
        elif e.key() == Qt.Key.Key_Escape: self.esc.emit()
        else: super().keyPressEvent(e)
"""

# 4. sys_media.py
sys_media_code = """import asyncio, threading
from PyQt6.QtCore import QObject, pyqtSignal
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SMTC
from winrt.windows.storage.streams import Buffer, InputStreamOptions, DataReader
from pycaw.pycaw import AudioUtilities

def get_volume():
    try:
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name().lower() == "audiodg.exe":
                return s.SimpleAudioVolume
    except: pass
    return None

class Media(QObject):
    updated = pyqtSignal(dict)
    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop(); self.session = None; self._key = None; self._tries = 0
        threading.Thread(target=self._run, daemon=True).start()
    def _run(self):
        asyncio.set_event_loop(self.loop); self.loop.run_until_complete(self._poll())
    async def _thumb(self, props):
        try:
            stream = await props.thumbnail.open_read_async()
            buf = Buffer(stream.size)
            await stream.read_async(buf, stream.size, InputStreamOptions.READ_AHEAD)
            data = bytearray(buf.length); DataReader.from_buffer(buf).read_bytes(data); return bytes(data)
        except Exception: return None
    async def _poll(self):
        mgr = await SMTC.request_async()
        while True:
            try:
                s = mgr.get_current_session(); self.session = s
                if s is None: self.updated.emit({"none": True}); self._key = None
                else:
                    props = await s.try_get_media_properties_async()
                    info, tl = s.get_playback_info(), s.get_timeline_properties()
                    d = dict(title=props.title, artist=props.artist, playing=int(info.playback_status) == 4,
                             pos=tl.position.total_seconds(), end=(tl.end_time - tl.start_time).total_seconds())
                    key = (props.title, props.artist)
                    if key != self._key:
                        th = await self._thumb(props); self._tries += 1
                        if th or self._tries > 3: d["thumb"] = th; self._key = key; self._tries = 0
                    self.updated.emit(d)
            except Exception: pass
            await asyncio.sleep(1)
    def cmd(self, name, arg=None):
        if self.session: asyncio.run_coroutine_threadsafe(self._cmd(name, arg), self.loop)
    async def _cmd(self, name, arg):
        s = self.session
        try:
            if name == "toggle": await s.try_toggle_play_pause_async()
            elif name == "next": await s.try_skip_next_async()
            elif name == "prev": await s.try_skip_previous_async()
            elif name == "seek": await s.try_change_playback_position_async(int(arg * 10000000))
        except Exception: pass
"""

# 5. sys_hotkey.py
sys_hotkey_code = """import ctypes
from ctypes import wintypes
from PyQt6.QtCore import QThread, pyqtSignal

class HotKey(QThread):
    fired_launcher = pyqtSignal()
    fired_notch = pyqtSignal()
    def run(self):
        u = ctypes.windll.user32
        u.RegisterHotKey(None, 1, 0x0002 | 0x0001 | 0x4000, 0x20)  # CTRL|ALT|NOREPEAT, SPACE
        u.RegisterHotKey(None, 2, 0x0002 | 0x0001 | 0x4000, 0x4E)  # CTRL|ALT|NOREPEAT, N
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312:
                if msg.wParam == 1: self.fired_launcher.emit()
                elif msg.wParam == 2: self.fired_notch.emit()
"""

# Extract Notch class
import re

start_idx = -1
for i, l in enumerate(text.splitlines()):
    if l.startswith("class Notch(QWidget):"):
        start_idx = i
        break

if start_idx != -1:
    notch_code = "\\n".join(text.splitlines()[start_idx:])
    
    # We will modify notch_code imports.
    main_code = """import sys, os, re, time, random, asyncio, threading, ctypes, subprocess, webbrowser, winsound
from collections import namedtuple
from ctypes import wintypes
from pathlib import Path
from urllib.parse import quote

from PyQt6.QtCore import (Qt, QTimer, QThread, QObject, pyqtSignal, QPropertyAnimation, QVariantAnimation,
                          QEasingCurve, QRect, QRectF, QSize, QFileInfo, QEvent)
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QPixmap, QFont, QFontMetrics, QRegion, QCursor
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QListWidget, QListWidgetItem, QMenu, QFileIconProvider,
                             QSizePolicy, QGraphicsOpacityEffect, QScrollArea)

from constants import BLUE, GRAY, DARK, G
from utils import icon_font, rounded, mmss, force_focus, autostart, build_index, SETTINGS
from ui import ibtn, chip, Bar, Eq, Mascot, Input
from sys_media import get_volume, Media
from sys_hotkey import HotKey

R = namedtuple("R", "title sub path glyph fn")

""" + f"\n{notch_code}\n"
    
    import os
    os.makedirs(r'd:\QUICK TASKBAR\NotchApp', exist_ok=True)
    
    with open(r'd:\QUICK TASKBAR\NotchApp\constants.py', 'w', encoding='utf-8') as f: f.write(constants_code)
    with open(r'd:\QUICK TASKBAR\NotchApp\utils.py', 'w', encoding='utf-8') as f: f.write(utils_code)
    with open(r'd:\QUICK TASKBAR\NotchApp\ui.py', 'w', encoding='utf-8') as f: f.write(ui_code)
    with open(r'd:\QUICK TASKBAR\NotchApp\sys_media.py', 'w', encoding='utf-8') as f: f.write(sys_media_code)
    with open(r'd:\QUICK TASKBAR\NotchApp\sys_hotkey.py', 'w', encoding='utf-8') as f: f.write(sys_hotkey_code)
    with open(r'd:\QUICK TASKBAR\NotchApp\main.py', 'w', encoding='utf-8') as f: f.write(main_code)
    
print("done")
