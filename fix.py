import os
from pathlib import Path
path = r'd:\QUICK TASKBAR\NotchApp\main.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(r'\n', '\n')
text = text.replace('"bookmarks.json"', 'str(Path.home() / ".notch_bookmarks.json")')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
