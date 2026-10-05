import asyncio, threading
from PyQt6.QtCore import QObject, pyqtSignal
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SMTC
from winrt.windows.storage.streams import Buffer, InputStreamOptions, DataReader
from pycaw.pycaw import AudioUtilities

def get_volume():
    try:
        return AudioUtilities.GetSpeakers().EndpointVolume
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
