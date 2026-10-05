import re

with open(r"d:\QUICK TASKBAR\NotchApp\main.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add self.edge
code = code.replace(
    'self.mode, self.m, self.m_ts, self.busy = "collapsed", None, 0, False',
    'self.mode, self.m, self.m_ts, self.busy = "collapsed", None, 0, False\n        self.edge = "top"'
)

# 2. Update SIZES
code = code.replace(
    '"collapsed": (300, 36),',
    '"collapsed": (300, 36), "collapsed_v": (36, 300),'
)

# 3. Add collapsed_v page and update self.pages
code = code.replace(
    '"collapsed": self.page_collapsed(),',
    '"collapsed": self.page_collapsed(), "collapsed_v": self.page_collapsed_v(),'
)

# 4. Add page_collapsed_v method
page_collapsed_code = """
    def page_collapsed_v(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 14, 0, 14)
        v.addWidget(Mascot(), 0, Qt.AlignmentFlag.AlignHCenter); v.addStretch()
        self.mini_v = QLabel(""); self.mini_v.setStyleSheet("color:#fff;font-weight:600;font-size:13px")
        self.mini_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.mini_v, 0, Qt.AlignmentFlag.AlignHCenter); return w
"""
code = code.replace(
    '    def page_player(self):',
    page_collapsed_code.strip('\n') + '\n\n    def page_player(self):'
)

# 5. Update refresh_timer
code = code.replace(
    'self.mini.setText(f"{self.t_left // 60:02d}:{self.t_left % 60:02d}" if self.t_run else "")',
    't = f"{self.t_left // 60:02d}:{self.t_left % 60:02d}" if self.t_run else ""\n        self.mini.setText(t)\n        if hasattr(self, "mini_v"): self.mini_v.setText(t.replace(":", "\\n"))'
)

# 6. Update shape_rect
new_shape_rect = """
    def shape_rect(self):
        w, h = int(round(self.sw)), int(round(self.sh))
        if self.edge == "top": return QRect((self.W - w) // 2, 0, w, h)
        if self.edge == "bottom": return QRect((self.W - w) // 2, self.H - h, w, h)
        if self.edge == "left": return QRect(0, (self.H - h) // 2, w, h)
        return QRect(self.W - w, (self.H - h) // 2, w, h)
"""
code = re.sub(
    r'    def shape_rect\(self\): return QRect\(\(self\.W - int\(round\(self\.sw\)\)\) // 2, 0, int\(round\(self\.sw\)\), int\(round\(self\.sh\)\)\)',
    new_shape_rect.strip('\n'),
    code
)

# 7. Update paintEvent
new_paint_event = """
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#000")); r = min(30.0, min(self.sw, self.sh) / 2)
        sr = self.shape_rect()
        p.drawRoundedRect(QRectF(sr), r, r)
        if self.edge == "top": p.drawRect(sr.x(), sr.y(), sr.width(), int(r))
        elif self.edge == "bottom": p.drawRect(sr.x(), sr.bottom() - int(r) + 1, sr.width(), int(r))
        elif self.edge == "left": p.drawRect(sr.x(), sr.y(), int(r), sr.height())
        elif self.edge == "right": p.drawRect(sr.right() - int(r) + 1, sr.y(), int(r), sr.height())
"""
code = re.sub(
    r'    def paintEvent\(self, e\):.*?(?=\n    # ----- pages -----)',
    new_paint_event.strip('\n') + '\n',
    code,
    flags=re.DOTALL
)

# 8. Update go()
new_go = """
    def go(self, mode, h=None):
        if mode == "mixer" and self.mode != "mixer": self.refresh_mixer()
        if mode == "bookmarks" and self.mode != "bookmarks": self.refresh_bookmarks_ui()
        is_vert = (mode == "collapsed" and self.edge in ("left", "right"))
        m_key = mode + "_v" if is_vert else mode
        w, hh = self.SIZES[m_key]; hh = h or hh
        prev_key = self.mode + "_v" if (self.mode == "collapsed" and self.edge in ("left", "right")) else self.mode
        prev, page, changed = self.pages[prev_key], self.pages[m_key], mode != self.mode
        self.mode = mode
        
        if self.edge == "top": tx, ty = (self.W - w) // 2, 0
        elif self.edge == "bottom": tx, ty = (self.W - w) // 2, self.H - hh
        elif self.edge == "left": tx, ty = 0, (self.H - hh) // 2
        else: tx, ty = self.W - w, (self.H - hh) // 2
        
        page.setFixedSize(w, hh); page.move(tx, ty)
        grow = w * hh >= self.sw * self.sh
        if changed:
            prev.setEnabled(False)
            self.fade(prev, 1, 0, 90, then=lambda p=prev: None if self.pages.get(self.mode + "_v" if (self.mode == "collapsed" and self.edge in ("left", "right")) else self.mode) is p else p.hide())
            page.setEnabled(True); page.show(); self.fade(page, 0, 1, 200, delay=80 if grow else 40)
        self.animate(w, hh, grow and changed)
        if mode == "launcher":
            self.raise_(); force_focus(int(self.winId())); self.input.setFocus()
"""
code = re.sub(
    r'    def go\(self, mode, h=None\):.*?(?=\n    def paintEvent)',
    new_go.strip('\n') + '\n',
    code,
    flags=re.DOTALL
)

# 9. Update mouseReleaseEvent
new_release = """
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
"""
code = re.sub(
    r'    def mouseReleaseEvent\(self, e\):.*?(?=\n    def keyPressEvent)',
    new_release.strip('\n') + '\n',
    code,
    flags=re.DOTALL
)

with open(r"d:\QUICK TASKBAR\NotchApp\main.py", "w", encoding="utf-8") as f:
    f.write(code)
