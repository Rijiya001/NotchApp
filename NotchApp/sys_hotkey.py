import ctypes
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
