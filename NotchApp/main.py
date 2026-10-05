import sys, os, re, time, random, asyncio, threading, ctypes, subprocess, webbrowser, winsound
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


class Notch(QWidget):
    W, H = 660, 470                      # fixed canvas (never resized -> no OS-level resize jitter)
    SIZES = {"collapsed": (300, 36), "collapsed_v": (36, 300), "player": (620, 340), "timer": (620, 340), "launcher": (620, 70), "system": (620, 340), "clipboard": (620, 340), "mixer": (620, 340), "bookmarks": (620, 340)}

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("QLabel{background:transparent;color:#fff}")
        self.setFixedSize(self.W, self.H)
        scr = QApplication.primaryScreen().geometry()
        self.move(scr.x() + (scr.width() - self.W) // 2, scr.y())

        self.mode, self.m, self.m_ts, self.busy = "collapsed", None, 0, False
        self.edge = "top"
        self.apps, self.results, self.vol, self.icons = build_index(), [], get_volume(), QFileIconProvider()
        self.load_bookmarks()
        self.t_left = self.t_total = 0; self.t_run = False; self.t_label = "Timer"
        self.sw, self.sh = 300.0, 36.0; self.s0 = self.s1 = (300.0, 36.0); self.fades = {}
        self.media = Media(); self.media.updated.connect(self.on_media)
        self.clip_history = []
        QApplication.clipboard().dataChanged.connect(self.on_clipboard)

        self.content = QWidget(self); self.content.setGeometry(0, 0, self.W, self.H)
        self.pages = {"collapsed": self.page_collapsed(), "collapsed_v": self.page_collapsed_v(), "player": self.shell(self.page_player()),
                      "timer": self.shell(self.page_timer()), "launcher": self.page_launcher(),
                      "system": self.shell(self.page_system()), "clipboard": self.shell(self.page_clipboard()),
                      "mixer": self.shell(self.page_mixer()), "bookmarks": self.shell(self.page_bookmarks())}
        for name, p in self.pages.items():
            p.setParent(self.content); w, h = self.SIZES[name]
            p.setFixedSize(w, h); p.move((self.W - w) // 2, 0); p.hide()
        self.pages["collapsed"].show()

        self.sanim = QVariantAnimation(self); self.sanim.valueChanged.connect(self.step)
        self.sanim.finished.connect(self.settle)
        self.leave_t = QTimer(self, singleShot=True, interval=3000); self.leave_t.timeout.connect(self.auto_collapse)
        for fn, ms in ((self.tick_ui, 250), (self.tick_timer, 1000), (self.sync_volume, 1000)):
            t = QTimer(self); t.timeout.connect(fn); t.start(ms)
        self.hot = HotKey()
        self.hot.fired_launcher.connect(self.hotkey_launcher)
        self.hot.fired_notch.connect(self.hotkey_notch)
        self.hot.start()
        self.settle()

    # ----- animation engine -----
    def shape_rect(self):
        w, h = int(round(self.sw)), int(round(self.sh))
        if self.edge == "top": return QRect((self.W - w) // 2, 0, w, h)
        if self.edge == "bottom": return QRect((self.W - w) // 2, self.H - h, w, h)
        if self.edge == "left": return QRect(0, (self.H - h) // 2, w, h)
        return QRect(self.W - w, (self.H - h) // 2, w, h)

    def step(self, t):
        t = float(t)
        self.sw = min(max(self.s0[0] + (self.s1[0] - self.s0[0]) * t, 1), self.W - 2)
        self.sh = min(max(self.s0[1] + (self.s1[1] - self.s0[1]) * t, 1), self.H - 1)
        self.content.setMask(QRegion(self.shape_rect())); self.update()

    def settle(self):                    # animation done: clip content + make transparent area click-through
        self.content.setMask(QRegion(self.shape_rect())); self.setMask(QRegion(self.shape_rect())); self.update()

    def animate(self, tw, th, spring):
        self.sanim.stop(); self.clearMask()
        self.s0, self.s1 = (self.sw, self.sh), (float(tw), float(th))
        c = QEasingCurve(QEasingCurve.Type.OutBack if spring else QEasingCurve.Type.OutCubic)
        if spring: c.setOvershoot(0.9)
        self.sanim.setEasingCurve(c); self.sanim.setDuration(430 if spring else 280)
        self.sanim.setStartValue(0.0); self.sanim.setEndValue(1.0); self.sanim.start()

    def fade(self, page, a, b, ms, delay=0, then=None):
        old = self.fades.get(page)
        if old: old.stop()
        eff = QGraphicsOpacityEffect(page); eff.setOpacity(a); page.setGraphicsEffect(eff)
        an = QPropertyAnimation(eff, b"opacity", self); an.setDuration(ms)
        an.setStartValue(a); an.setEndValue(b); an.setEasingCurve(QEasingCurve.Type.OutQuad)
        def done():
            if b >= 1: page.setGraphicsEffect(None)
            if then: then()
        an.finished.connect(done); self.fades[page] = an
        if delay: QTimer.singleShot(delay, lambda: self.fades.get(page) is an and an.start())
        else: an.start()

    def go(self, mode, h=None):
        if mode == "mixer" and self.mode != "mixer": self.refresh_mixer()
        if mode == "bookmarks" and self.mode != "bookmarks": self.refresh_bookmarks_ui()
        is_vert = (mode == "collapsed" and self.edge in ("left", "right"))
        m_key = mode + "_v" if is_vert else mode
        w, hh = self.SIZES[m_key]; hh = h or hh
        prev_key = getattr(self, 'active_key', 'collapsed')
        prev, page, changed = self.pages[prev_key], self.pages[m_key], m_key != prev_key
        self.mode = mode; self.active_key = m_key
        
        if self.edge == "top": tx, ty = (self.W - w) // 2, 0
        elif self.edge == "bottom": tx, ty = (self.W - w) // 2, self.H - hh
        elif self.edge == "left": tx, ty = 0, (self.H - hh) // 2
        else: tx, ty = self.W - w, (self.H - hh) // 2
        
        page.setFixedSize(w, hh); page.move(tx, ty)
        grow = w * hh >= self.sw * self.sh
        if changed:
            prev.setEnabled(False)
            self.fade(prev, 1, 0, 90, then=lambda p=prev: None if self.pages.get(getattr(self, 'active_key', 'collapsed')) is p else p.hide())
            page.setEnabled(True); page.show(); self.fade(page, 0, 1, 200, delay=80 if grow else 40)
        self.animate(w, hh, grow and changed)
        if mode == "launcher":
            self.raise_(); force_focus(int(self.winId())); self.input.setFocus()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#000")); r = min(30.0, min(self.sw, self.sh) / 2)
        sr = self.shape_rect()
        p.drawRoundedRect(QRectF(sr), r, r)
        if self.edge == "top": p.drawRect(sr.x(), sr.y(), sr.width(), int(r))
        elif self.edge == "bottom": p.drawRect(sr.x(), sr.bottom() - int(r) + 1, sr.width(), int(r))
        elif self.edge == "left": p.drawRect(sr.x(), sr.y(), int(r), sr.height())
        elif self.edge == "right": p.drawRect(sr.right() - int(r) + 1, sr.y(), int(r), sr.height())

    # ----- pages -----
    def rail(self, btns):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(14)
        [v.addWidget(b) for b in btns]; v.addStretch(); w.setFixedWidth(56); return w

    def shell(self, inner):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(18, 16, 18, 20); h.setSpacing(14)
        h.addWidget(self.rail([ibtn(G["grid"], cb=lambda: self.open_launcher(True)),
                               ibtn(G["timer"], cb=lambda: self.go("player" if self.mode == "timer" else "timer"))]))
        h.addWidget(inner, 1)
        h.addWidget(self.rail([ibtn(G["cog"], cb=self.settings_menu), ibtn(G["mixer"], cb=lambda: self.go("mixer" if self.mode != "mixer" else "player"))]))
        return w

    def page_collapsed(self):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(14, 0, 14, 0)
        h.addWidget(Mascot()); h.addStretch()
        self.mini = QLabel(""); self.mini.setStyleSheet("color:#fff;font-weight:600;font-size:13px")
        self.eq = Eq(); h.addWidget(self.mini); h.addWidget(self.eq); return w

    def page_collapsed_v(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 14, 0, 14)
        v.addWidget(Mascot(), 0, Qt.AlignmentFlag.AlignHCenter); v.addStretch()
        self.mini_v = QLabel(""); self.mini_v.setStyleSheet("color:#fff;font-weight:600;font-size:13px")
        self.mini_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.mini_v, 0, Qt.AlignmentFlag.AlignHCenter); return w

    def page_player(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        hd = QLabel("Now Playing"); hd.setStyleSheet("font-size:22px;font-weight:700"); v.addWidget(hd)
        mid = QHBoxLayout(); mid.setSpacing(20)
        self.art = QLabel(); self.art.setFixedSize(150, 150); mid.addWidget(self.art, 0, Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout(); info.setSpacing(2)
        self.title = QLabel("Nothing playing"); self.title.setStyleSheet("font-size:24px;font-weight:700")
        self.artist = QLabel("Play something in any app"); self.artist.setStyleSheet(f"font-size:16px;color:{GRAY}")
        for l in (self.title, self.artist): l.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(self.title); info.addWidget(self.artist); info.addSpacing(8)
        self.prog = Bar(BLUE, 8); self.prog.changed.connect(lambda f: self.m and self.media.cmd("seek", f * self.m["end"]))
        info.addWidget(self.prog)
        tr = QHBoxLayout(); self.t0, self.t1 = QLabel("0:00"), QLabel("-0:00")
        for l in (self.t0, self.t1): l.setStyleSheet(f"color:{GRAY};font-size:12px;font-weight:600")
        tr.addWidget(self.t0); tr.addStretch(); tr.addWidget(self.t1); info.addLayout(tr)
        ct = QHBoxLayout(); ct.addStretch()
        ct.addWidget(ibtn(G["prev"], 48, 22, "transparent", cb=lambda: self.media.cmd("prev")))
        self.playb = ibtn(G["play"], 66, 26, "#fff", "#000", cb=lambda: self.media.cmd("toggle")); ct.addWidget(self.playb)
        ct.addWidget(ibtn(G["next"], 48, 22, "transparent", cb=lambda: self.media.cmd("next"))); ct.addStretch()
        info.addLayout(ct); mid.addLayout(info, 1); v.addLayout(mid, 1)
        vr = QHBoxLayout(); self.vicon = QLabel(G["vol"]); self.vicon.setFont(icon_font(18)); vr.addWidget(self.vicon)
        self.vbar = Bar("#e5e5ea", 22, live=True); self.vbar.changed.connect(self.set_volume); vr.addWidget(self.vbar, 1)
        v.addLayout(vr); self.set_art(None); return w

    def page_timer(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        self.t_title = QLabel("Timer"); self.t_title.setStyleSheet("font-size:22px;font-weight:700"); v.addWidget(self.t_title)
        v.addStretch()
        self.t_big = QLabel("10:00"); self.t_big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.t_big.setStyleSheet("font-size:64px;font-weight:700"); v.addWidget(self.t_big)
        r = QHBoxLayout(); r.addStretch()
        for m in (5, 10, 25, 45): r.addWidget(chip(f"{m} min", lambda _, m=m: self.set_timer(m * 60)))
        r.addStretch(); v.addLayout(r); v.addSpacing(10)
        r = QHBoxLayout(); r.addStretch()
        r.addWidget(ibtn("\uE738", 44, 16, cb=lambda: self.adjust(-60)))
        self.t_btn = ibtn(G["play"], 66, 26, "#fff", "#000", cb=self.timer_toggle); r.addWidget(self.t_btn)
        r.addWidget(ibtn("\uE710", 44, 16, cb=lambda: self.adjust(60)))
        r.addWidget(ibtn("\uE72C", 44, 16, cb=lambda: self.set_timer(self.t_total or 600)))
        r.addStretch(); v.addLayout(r); v.addStretch(); self.set_timer(600); return w

    def page_launcher(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(18, 0, 18, 0); v.setSpacing(0)
        hd = QHBoxLayout(); hd.setContentsMargins(4, 0, 4, 0); hd.addWidget(Mascot(30))
        self.input = Input(); self.input.setPlaceholderText("Type what you want to do")
        self.input.setStyleSheet("QLineEdit{background:transparent;border:none;color:#fff;font-size:24px;padding:0 10px;"
                                 "selection-background-color:#0a84ff}")
        self.input.textChanged.connect(lambda t: self.populate(t)); self.input.nav.connect(self.nav)
        self.input.enter.connect(self.run_sel); self.input.esc.connect(lambda: self.go("collapsed"))
        hd.addWidget(self.input, 1)
        self.hint = QLabel("↓ Suggestions     Esc"); self.hint.setStyleSheet(f"color:{GRAY};font-size:14px;font-weight:600")
        hd.addWidget(self.hint); hd.setSpacing(8)
        hw = QWidget(); hw.setFixedHeight(70); hw.setLayout(hd); v.addWidget(hw)
        self.list = QListWidget(); self.list.setFrameShape(QListWidget.Shape.NoFrame)
        self.list.setStyleSheet("QListWidget{background:transparent;border:none;border-top:1px solid #2c2c2e;outline:none}"
                                "QListWidget::item{border-radius:12px}QListWidget::item:selected{background:#06121f}")
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(lambda _: self.run_sel()); self.list.currentRowChanged.connect(self.mark_sel)
        v.addWidget(self.list, 1)
        self.foot = QLabel("↑↓ Navigate     ↵ Open     Esc"); self.foot.setFixedHeight(34)
        self.foot.setStyleSheet(f"color:{GRAY};font-size:12px;font-weight:600;border-top:1px solid #2c2c2e")
        self.foot.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); v.addWidget(self.foot)
        self.list.hide(); self.foot.hide(); return w

    def page_system(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        hd = QLabel("System Monitor"); hd.setStyleSheet("font-size:22px;font-weight:700"); v.addWidget(hd)
        v.addSpacing(30)
        
        def make_stat(title, color):
            row = QWidget(); hl = QHBoxLayout(row); hl.setContentsMargins(0,0,0,0)
            lbl = QLabel(title); lbl.setFixedWidth(80); lbl.setStyleSheet("font-size:16px;font-weight:600;color:#8e8e93")
            bar = Bar(color, 12, live=False, ro=True); bar.setFixedHeight(24)
            val = QLabel("0%"); val.setFixedWidth(60); val.setAlignment(Qt.AlignmentFlag.AlignRight); val.setStyleSheet("font-size:16px;font-weight:600")
            hl.addWidget(lbl); hl.addWidget(bar, 1); hl.addWidget(val)
            return row, bar, val
            
        self.sys_cpu_row, self.sys_cpu_bar, self.sys_cpu_val = make_stat("CPU", "#ff3b30")
        self.sys_ram_row, self.sys_ram_bar, self.sys_ram_val = make_stat("Memory", "#0a84ff")
        self.sys_bat_row, self.sys_bat_bar, self.sys_bat_val = make_stat("Battery", "#34c759")
        
        v.addWidget(self.sys_cpu_row)
        v.addWidget(self.sys_ram_row)
        v.addWidget(self.sys_bat_row)
        v.addStretch()
        return w

    def page_clipboard(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        hd = QLabel("Clipboard History"); hd.setStyleSheet("font-size:22px;font-weight:700"); v.addWidget(hd)
        self.clip_list = QListWidget(); self.clip_list.setFrameShape(QListWidget.Shape.NoFrame)
        self.clip_list.setStyleSheet("QListWidget{background:transparent;border:none;outline:none}"
                                     "QListWidget::item{border-radius:8px;padding:8px}QListWidget::item:selected{background:#06121f}")
        self.clip_list.itemClicked.connect(self.paste_clip)
        v.addWidget(self.clip_list)
        return w

    def page_mixer(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        r = QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton(G["back"]); btn.setFixedSize(32, 32); btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("QPushButton{background:transparent;border:none;font-family:'Segoe MDL2 Assets';font-size:20px}")
        btn.clicked.connect(lambda: self.go("player"))
        hd = QLabel("Control Center"); hd.setStyleSheet("font-size:22px;font-weight:700")
        r.addWidget(btn); r.addWidget(hd); r.addStretch()
        v.addLayout(r)
        
        def chip(text, cb):
            b = QPushButton(text); b.setFixedHeight(30); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:#2c2c2e;border-radius:15px;padding:0 15px;font-weight:600}}QPushButton:hover{{background:#3a3a3c}}")
            b.clicked.connect(cb); return b
            
        togs = QHBoxLayout(); togs.setSpacing(10)
        togs.addWidget(chip("Mute All", self.toggle_mute))
        togs.addWidget(chip("WiFi", lambda _: os.startfile("ms-settings:network-wifi")))
        togs.addWidget(chip("Bluetooth", lambda _: os.startfile("ms-settings:bluetooth")))
        togs.addWidget(chip("Bookmarks", lambda _: self.go("bookmarks")))
        togs.addStretch(); v.addLayout(togs)
        
        self.mix_scroll = QScrollArea()
        self.mix_scroll.setWidgetResizable(True)
        self.mix_scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        self.mix_content = QWidget(); self.mix_content.setStyleSheet("background:transparent")
        self.mix_v = QVBoxLayout(self.mix_content); self.mix_v.setContentsMargins(0, 10, 0, 0)
        self.mix_scroll.setWidget(self.mix_content)
        v.addWidget(self.mix_scroll, 1)
        return w
        
    def load_bookmarks(self):
        try:
            import json
            if os.path.exists(str(Path.home() / ".notch_bookmarks.json")):
                with open(str(Path.home() / ".notch_bookmarks.json"), "r") as f: self.bmarks = json.load(f)
            else:
                self.bmarks = {
                    "yt": {"name": "YouTube", "url": "https://youtube.com", "app": "Default"},
                    "gm": {"name": "Gmail", "url": "https://mail.google.com", "app": "Default"}
                }
                self.save_bookmarks()
        except Exception: self.bmarks = {}
        
    def save_bookmarks(self):
        import json
        with open(str(Path.home() / ".notch_bookmarks.json"), "w") as f: json.dump(self.bmarks, f, indent=4)

    def page_bookmarks(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        r = QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton(G["back"]); btn.setFixedSize(32, 32); btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("QPushButton{background:transparent;border:none;font-family:'Segoe MDL2 Assets';font-size:20px}")
        btn.clicked.connect(lambda: self.go("mixer"))
        hd = QLabel("Bookmarks"); hd.setStyleSheet("font-size:22px;font-weight:700")
        r.addWidget(btn); r.addWidget(hd); r.addStretch()
        v.addLayout(r)
        
        self.bm_scroll = QScrollArea(); self.bm_scroll.setWidgetResizable(True)
        self.bm_scroll.setStyleSheet("QScrollArea{background:transparent;border:none}")
        self.bm_content = QWidget(); self.bm_content.setStyleSheet("background:transparent")
        self.bm_v = QVBoxLayout(self.bm_content); self.bm_v.setContentsMargins(0, 10, 0, 0)
        self.bm_scroll.setWidget(self.bm_content)
        v.addWidget(self.bm_scroll, 1)
        return w
        
    def refresh_bookmarks_ui(self):
        while self.bm_v.count():
            item = self.bm_v.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        form = QWidget(); fh = QHBoxLayout(form); fh.setContentsMargins(0, 0, 0, 10)
        sc = QLineEdit(); sc.setPlaceholderText("Shortcut"); sc.setFixedWidth(80)
        nm = QLineEdit(); nm.setPlaceholderText("Name")
        ur = QLineEdit(); ur.setPlaceholderText("URL")
        ap = QLineEdit(); ap.setPlaceholderText("App (or Default)")
        for lw in (sc, nm, ur, ap): lw.setStyleSheet("background:#2c2c2e;border:none;padding:5px;border-radius:5px")
        
        save = QPushButton(G["play"]); save.setFixedSize(30, 30); save.setFont(icon_font(12))
        save.setStyleSheet("background:#34c759;border-radius:15px;color:#000")
        def do_save():
            if sc.text().strip() and ur.text().strip():
                self.bmarks[sc.text().strip()] = {
                    "name": nm.text().strip() or sc.text().strip(),
                    "url": ur.text().strip(),
                    "app": ap.text().strip() or "Default"
                }
                self.save_bookmarks(); self.refresh_bookmarks_ui()
        save.clicked.connect(do_save)
        
        for lw in (sc, nm, ur, ap, save): fh.addWidget(lw)
        self.bm_v.addWidget(form)
        
        for sc_key, bm in list(self.bmarks.items()):
            row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0, 5, 0, 5)
            pill = QLabel(sc_key); pill.setFixedWidth(40); pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setStyleSheet("background:#0a84ff;border-radius:8px;font-weight:600;padding:2px;color:#fff")
            lbl = QLabel(f"{bm['name']} - {bm['app']}\n{bm['url']}"); lbl.setStyleSheet("font-size:13px;color:#fff")
            lbl.setWordWrap(True)
            delb = QPushButton(G["x"]); delb.setFixedSize(24, 24); delb.setFont(icon_font(12))
            delb.setStyleSheet("background:#ff3b30;border-radius:12px;color:#fff")
            delb.clicked.connect(lambda _, k=sc_key: self.delete_bookmark(k))
            h.addWidget(pill); h.addWidget(lbl, 1); h.addWidget(delb)
            self.bm_v.addWidget(row)
        self.bm_v.addStretch()
        
    def delete_bookmark(self, key):
        if key in self.bmarks:
            del self.bmarks[key]; self.save_bookmarks(); self.refresh_bookmarks_ui()

    def refresh_mixer(self):
        while self.mix_v.count():
            item = self.mix_v.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        try:
            from pycaw.pycaw import AudioUtilities
            for s in AudioUtilities.GetAllSessions():
                if s.Process:
                    name = s.Process.name()
                    vol = s.SimpleAudioVolume
                    row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
                    lbl = QLabel(name[:15]); lbl.setFixedWidth(120); lbl.setStyleSheet("font-size:16px;font-weight:600")
                    bar = Bar("#0a84ff", 16, live=True)
                    bar.set(vol.GetMasterVolume())
                    def make_cb(b=bar, v=vol): return lambda f: (v.SetMasterVolume(float(f), None), b.set(f))
                    bar.changed.connect(make_cb())
                    h.addWidget(lbl); h.addWidget(bar, 1)
                    self.mix_v.addWidget(row)
        except Exception: pass
        self.mix_v.addStretch()

    def on_clipboard(self):
        txt = QApplication.clipboard().text()
        if txt and txt.strip() and (not self.clip_history or self.clip_history[0] != txt):
            self.clip_history.insert(0, txt)
            if len(self.clip_history) > 20: self.clip_history.pop()
            self.clip_list.clear()
            for c in self.clip_history:
                it = QListWidgetItem(c.replace('\n', ' ')[:100] + ('...' if len(c) > 100 else ''))
                it.setData(Qt.ItemDataRole.UserRole, c)
                self.clip_list.addItem(it)

    def paste_clip(self, item):
        txt = item.data(Qt.ItemDataRole.UserRole)
        if txt:
            QApplication.clipboard().blockSignals(True)
            QApplication.clipboard().setText(txt)
            QApplication.clipboard().blockSignals(False)
            self.collapse()

    # ----- window behaviour -----
    def collapse(self): self.go("collapsed")
    def auto_collapse(self):
        if self.mode in ("player", "timer") and not self.busy and not self.underMouse(): self.collapse()
    def enterEvent(self, e): self.leave_t.stop()
    def leaveEvent(self, e):
        if self.mode in ("player", "timer"): self.leave_t.start()
    def mousePressEvent(self, e):
        if self.mode == "collapsed":
            self.drag_start = e.globalPosition().toPoint()
            self.drag_pos0 = self.pos()
            self.dragged = False
    def mouseMoveEvent(self, e):
        if self.mode == "collapsed" and hasattr(self, 'drag_start') and self.drag_start is not None:
            diff = e.globalPosition().toPoint() - self.drag_start
            if diff.manhattanLength() > 5:
                self.dragged = True
                self.move(self.drag_pos0 + diff)
    def mouseReleaseEvent(self, e):
        if self.mode == "collapsed":
            if not getattr(self, 'dragged', False):
                self.go("timer" if self.t_run else "player")
            else:
                scr = QApplication.primaryScreen().geometry()
                cx, cy = self.x() + self.W // 2, self.y() + self.H // 2
                d_top, d_bottom = cy - scr.top(), scr.bottom() - cy
                d_left, d_right = cx - scr.left(), scr.right() - cx
                min_d = min(d_top, d_bottom, d_left, d_right)
                
                if min_d == d_top:
                    self.edge, nx, ny = "top", max(scr.left(), min(self.x(), scr.right() - self.W)), scr.top()
                elif min_d == d_bottom:
                    self.edge, nx, ny = "bottom", max(scr.left(), min(self.x(), scr.right() - self.W)), scr.bottom() - self.H + 1
                elif min_d == d_left:
                    self.edge, nx, ny = "left", scr.left(), max(scr.top(), min(self.y(), scr.bottom() - self.H))
                else:
                    self.edge, nx, ny = "right", scr.right() - self.W + 1, max(scr.top(), min(self.y(), scr.bottom() - self.H))
                self.move(nx, ny)
                self.go("collapsed")
            self.drag_start = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape: self.collapse()
    def event(self, e):
        if e.type() == QEvent.Type.WindowDeactivate and self.mode != "collapsed" and not self.busy:
            QTimer.singleShot(0, self.collapse)
        return super().event(e)

    def hotkey_launcher(self):
        if self.mode == "launcher": self.collapse()
        else: self.open_launcher()

    def hotkey_notch(self):
        if self.mode in ("player", "timer", "system", "clipboard", "mixer"): self.collapse()
        else: self.go("timer" if self.t_run else "player")

    # ----- launcher -----
    def open_launcher(self, suggest=False):
        self.input.clear(); self.populate("", suggest, force_go=True)

    def copy_and_collapse(self, text):
        QApplication.clipboard().setText(text)
        self.collapse()

    def results_for(self, q):
        ql = q.strip().lower(); out = []
        if not ql:
            return [R("System Monitor", "System", None, G["grid"], lambda: self.go("system")),
                    R("Control Center", "Utilities", None, G["mixer"], lambda: self.go("mixer")),
                    R("Clipboard History", "Utilities", None, G["grid"], lambda: self.go("clipboard")),
                    R("Start 25 min focus", "Timer", None, G["timer"], lambda: self.start_timer(1500, "Focus")),
                    R("Lock PC", "System", None, G["lock"], lambda: subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])),
                    R("Sound settings", "System Settings", None, G["cog"], lambda: os.startfile("ms-settings:sound"))]
                    
        try:
            if re.match(r'^[\d\.\+\-\*\/\(\)\s\%\^]+$', ql) and any(op in ql for op in "+-*/%^"):
                res = eval(ql.replace('^', '**'))
                val = f"{res:g}" if isinstance(res, float) else str(res)
                out.append(R(f"= {val}", "Calculator", None, "\uE8EF", lambda v=val: self.copy_and_collapse(v)))
        except Exception: pass
        
        m = re.match(r'^([\d\.]+)\s*(kg|lbs|c|f|km|mi|m|cm|in|ft)\s*(?:to|in)\s*(kg|lbs|c|f|km|mi|m|cm|in|ft)$', ql)
        if m:
            v, u1, u2 = float(m.group(1)), m.group(2), m.group(3)
            c_key = f"{u1}-{u2}"
            convs = {
                'kg-lbs': lambda x: x * 2.20462, 'lbs-kg': lambda x: x / 2.20462,
                'c-f': lambda x: (x * 9/5) + 32, 'f-c': lambda x: (x - 32) * 5/9,
                'km-mi': lambda x: x * 0.621371, 'mi-km': lambda x: x / 0.621371,
                'm-ft': lambda x: x * 3.28084, 'ft-m': lambda x: x / 3.28084,
                'cm-in': lambda x: x / 2.54, 'in-cm': lambda x: x * 2.54
            }
            if c_key in convs:
                ans = convs[c_key](v)
                val = f"{ans:.2f} {u2}"
                out.append(R(f"= {val}", "Unit Conversion", None, "\uE8EF", lambda v=val: self.copy_and_collapse(v)))

        if ql in getattr(self, "bmarks", {}):
            bm = self.bmarks[ql]
            name, url, app = bm["name"], bm["url"], bm["app"]
            def open_bm(u=url, a=app):
                if a.lower() == "default": webbrowser.open(u)
                else:
                    try: subprocess.Popen(f'start {a} "{u}"', shell=True)
                    except Exception: webbrowser.open(u)
            out.append(R(f"Open {name}", f"Bookmark ({app})", None, G["web"], open_bm))

        m = re.match(r"^(timer|focus)\s*(\d+)?", ql)
        if m:
            n = int(m.group(2) or (25 if m.group(1) == "focus" else 10))
            out.append(R(f"Start {n} min {m.group(1)}", "Timer", None, G["timer"],
                         lambda n=n, l=m.group(1).title(): self.start_timer(n * 60, l)))
        if "bookmark" in ql:
            out.append(R("Bookmarks Manager", "Utilities", None, G["grid"], lambda: self.go("bookmarks")))
        if ql in ("mute", "unmute", "volume", "mixer", "control"):
            out.append(R("Control Center", "Utilities", None, G["mixer"], lambda: self.go("mixer")))
        if "clip" in ql or "hist" in ql:
            out.append(R("Clipboard History", "Utilities", None, G["grid"], lambda: self.go("clipboard")))
        if "sys" in ql or "cpu" in ql or "ram" in ql or "bat" in ql:
            out.append(R("System Monitor", "System", None, G["grid"], lambda: self.go("system")))
            
        cands = [(n, p, None) for n, p in self.apps] + [(n, None, u) for n, u in SETTINGS]
        ranked = []
        for n, p, u in cands:
            nl = n.lower()
            s = 0 if nl.startswith(ql) else 1 if any(x.startswith(ql) for x in re.split(r"\W+", nl)) else 2 if ql in nl else None
            if s is not None: ranked.append((s, len(n), n, p, u))
        ranked.sort()
        for s, _, n, p, u in ranked[:max(5 - len(out), 0)]:
            if p: out.append(R(n, "App", p, None, lambda p=p: os.startfile(p)))
            else: out.append(R(n, "System Settings", None, G["cog"], lambda u=u: os.startfile(u)))
            
        if len(ql) >= 3 and len(out) < 6:
            try:
                home = Path.home()
                for d in (home / 'Desktop', home / 'Documents'):
                    if not d.exists(): continue
                    for f in d.iterdir():
                        if ql in f.name.lower() and len(out) < 7:
                            out.append(R(f.name, f"File - {d.name}", str(f), None, lambda f=str(f): os.startfile(f)))
            except Exception: pass

        if not out or not any(r.sub in ("App", "Calculator", "Unit Conversion", "Bookmark", "System Settings") or r.sub.startswith("File") for r in out):
            if re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", ql):
                out.append(R(f"Open {q.strip()}", "Website", None, G["web"], lambda: webbrowser.open("https://" + q.strip())))
            out.append(R(f"Search Google for '{q.strip()}'", "Web Search", None, G["search"],
                         lambda: webbrowser.open("https://www.google.com/search?q=" + quote(q.strip()))))
        return out

    def populate(self, q, force=False, force_go=False):
        self.results = self.results_for(q) if (q.strip() or force) else []
        self.list.blockSignals(True); self.list.clear()
        for r in self.results:
            it = QListWidgetItem(); it.setSizeHint(QSize(0, 56)); self.list.addItem(it)
            self.list.setItemWidget(it, self.row(r))
        self.list.blockSignals(False)
        n = len(self.results); self.list.setVisible(n > 0); self.foot.setVisible(n > 0)
        self.hint.setVisible(not q.strip() and n == 0)
        if n: self.list.setCurrentRow(0); self.mark_sel(0)
        if self.mode == "launcher" or force_go: self.go("launcher", 70 + (n * 56 + 14 + 34 if n else 0))

    def row(self, r):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(12, 4, 12, 4); h.setSpacing(14)
        ic = QLabel(); ic.setFixedSize(38, 38); ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if r.path: ic.setPixmap(self.icons.icon(QFileInfo(r.path)).pixmap(32, 32))
        else:
            ic.setText(r.glyph); ic.setFont(icon_font(18)); ic.setStyleSheet(f"background:{DARK};border-radius:9px;color:#fff")
        v = QVBoxLayout(); v.setSpacing(0); w.t = QLabel(r.title); w.t.setStyleSheet("font-size:16px;font-weight:600")
        s = QLabel(r.sub); s.setStyleSheet(f"color:{GRAY};font-size:12px")
        v.addWidget(w.t); v.addWidget(s); h.addWidget(ic); h.addLayout(v, 1); return w

    def mark_sel(self, row):
        for i in range(self.list.count()):
            w = self.list.itemWidget(self.list.item(i))
            if w: w.t.setStyleSheet(f"font-size:16px;font-weight:600;color:{BLUE if i == row else '#fff'}")

    def nav(self, d):
        if not self.results:
            if d > 0 and not self.input.text().strip(): self.populate("", True)
            return
        self.list.setCurrentRow((self.list.currentRow() + d) % len(self.results))

    def run_sel(self):
        i = self.list.currentRow()
        if 0 <= i < len(self.results):
            fn = self.results[i].fn; self.collapse()
            try: fn()
            except Exception: pass

    # ----- media / volume -----
    def on_media(self, d):
        if d.get("none"):
            self.m = None; self.title.setText("Nothing playing"); self.artist.setText("Play something in any app")
            self.eq.playing = False; self.playb.setText(G["play"]); self.set_art(None); return
        if not self.m or self.m["title"] != d["title"] or self.m["playing"] != d["playing"] or abs(self.m["pos"] - d["pos"]) > 3:
            self.m = d; self.m_ts = time.time()
        else:
            self.m["title"] = d["title"]; self.m["artist"] = d["artist"]
            if "thumb" in d: self.m["thumb"] = d["thumb"]
        fm = QFontMetrics(self.title.font())
        self.title.setText(fm.elidedText(self.m["title"] or "Unknown", Qt.TextElideMode.ElideRight, 330))
        self.artist.setText(self.m["artist"] or ""); self.eq.playing = self.m["playing"]
        self.playb.setText(G["pause"] if self.m["playing"] else G["play"])
        if "thumb" in d: self.set_art(d["thumb"])

    def set_art(self, data):
        pm = QPixmap()
        if data and pm.loadFromData(data): self.art.setPixmap(rounded(pm, 150, 22)); self.art.setStyleSheet(""); return
        self.art.setPixmap(QPixmap()); self.art.setText(G["music"]); self.art.setFont(icon_font(48))
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setStyleSheet(f"background:{DARK};border-radius:22px;color:{GRAY}")

    def tick_ui(self):
        if self.mode == "system":
            try:
                import psutil
                cpu = psutil.cpu_percent()
                mem = psutil.virtual_memory().percent
                bat = psutil.sensors_battery()
                self.sys_cpu_val.setText(f"{cpu}%"); self.sys_cpu_bar.set(cpu / 100.0)
                self.sys_ram_val.setText(f"{mem}%"); self.sys_ram_bar.set(mem / 100.0)
                if bat:
                    self.sys_bat_val.setText(f"{bat.percent}%"); self.sys_bat_bar.set(bat.percent / 100.0)
                else:
                    self.sys_bat_val.setText("N/A"); self.sys_bat_bar.set(0)
            except Exception: pass
            return
        if self.mode != "player" and self.mode != "collapsed": return
        if self.m and self.m["end"] > 0:
            pos = self.m["pos"] + ((time.time() - self.m_ts) if self.m["playing"] else 0); pos = min(pos, self.m["end"])
            self.prog.set(pos / self.m["end"]); self.t0.setText(mmss(pos)); self.t1.setText("-" + mmss(self.m["end"] - pos))
        else: self.prog.set(0); self.t0.setText("0:00"); self.t1.setText("-0:00")

    def sync_volume(self):
        try:
            if not self.vol: self.vol = get_volume()
            if self.vol:
                self.vbar.set(self.vol.GetMasterVolumeLevelScalar())
                self.vicon.setText(G["mute"] if self.vol.GetMute() else G["vol"])
        except Exception: 
            self.vol = None

    def set_volume(self, f):
        try: 
            if not self.vol: self.vol = get_volume()
            if self.vol: self.vol.SetMasterVolumeLevelScalar(float(f), None)
        except Exception: 
            self.vol = None

    def toggle_mute(self):
        try: self.vol.SetMute(not self.vol.GetMute(), None)
        except Exception: pass

    # ----- timer -----
    def set_timer(self, secs):
        self.t_total = self.t_left = secs; self.t_run = False; self.refresh_timer()
    def adjust(self, d):
        if not self.t_run: self.t_total = self.t_left = max(60, self.t_left + d); self.refresh_timer()
    def timer_toggle(self):
        if self.t_left <= 0: self.t_left = self.t_total
        self.t_run = not self.t_run; self.refresh_timer()
    def start_timer(self, secs, label="Timer"):
        self.t_label = label; self.t_total = self.t_left = secs; self.t_run = True; self.refresh_timer(); self.go("timer")
    def tick_timer(self):
        if self.t_run:
            self.t_left -= 1
            if self.t_left <= 0:
                self.t_left, self.t_run = 0, False
                try:
                    for f in (880, 1175, 1480): winsound.Beep(f, 180)
                except Exception: pass
                self.go("timer")
            self.refresh_timer()
    def refresh_timer(self):
        self.t_big.setText(f"{self.t_left // 60:02d}:{self.t_left % 60:02d}"); self.t_title.setText(self.t_label)
        self.t_btn.setText(G["pause"] if self.t_run else G["play"])
        t = f"{self.t_left // 60:02d}:{self.t_left % 60:02d}" if self.t_run else ""
        self.mini.setText(t)
        if hasattr(self, "mini_v"): self.mini_v.setText(t.replace(":", "\n"))

    # ----- settings -----
    def settings_menu(self):
        self.busy = True
        m = QMenu(self); m.setStyleSheet("QMenu{background:#1c1c1e;color:#fff;border:1px solid #2c2c2e;padding:6px}"
                                         "QMenu::item{padding:8px 22px;border-radius:6px}QMenu::item:selected{background:#2c2c2e}")
        a = m.addAction("Start with Windows"); a.setCheckable(True); a.setChecked(autostart())
        a.toggled.connect(lambda on: autostart(on)); m.addSeparator()
        m.addAction("Quit Notch").triggered.connect(QApplication.quit)
        m.exec(QCursor.pos()); self.busy = False


if __name__ == "__main__":
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False); app.setFont(QFont("Segoe UI", 10))
    w = Notch(); w.show(); sys.exit(app.exec())
