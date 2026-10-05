import os, winreg, ctypes
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
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
    if enable is None:
        try: return winreg.QueryValueEx(k, "Notch")[0] != ""
        except FileNotFoundError: return False
    if enable: winreg.SetValueEx(k, "Notch", 0, winreg.REG_SZ, sys.executable + ' "' + os.path.abspath(sys.argv[0]) + '"')
    else:
        try: winreg.DeleteValue(k, "Notch")
        except FileNotFoundError: pass

def build_index():
    seen = {}
    for shell_folder in (r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"):
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
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes")
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                n = winreg.EnumKey(k, i)
                if n.startswith("AppX"):
                    p = Path(winreg.QueryValueEx(winreg.OpenKey(k, f"{n}\\Application"), "ApplicationName")[0])
                    if p.name: seen[p.name.lower()] = (p.name, str(p))
            except Exception: pass
    except Exception: pass
    return list(seen.values())

SETTINGS = [("Wi-Fi", "ms-settings:network-wifi"), ("Bluetooth", "ms-settings:bluetooth"),
            ("Display", "ms-settings:display"), ("Sound", "ms-settings:sound"),
            ("Apps & features", "ms-settings:appsfeatures"), ("Windows Update", "ms-settings:windowsupdate"),
            ("Personalization", "ms-settings:personalization"), ("Battery", "ms-settings:batterysaver")]
