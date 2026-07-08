import queue
import sys
import time as time_module
import numpy as np
import sounddevice as sd
from config.config import CONFIG


class LiveRecorder:
    def __init__(self, max_duration: int | None = None):
        if max_duration is None:
            max_duration = CONFIG.get("live", {}).get("max_duration", 60)
        self.sr = CONFIG["sample_rate"]
        self.max_duration = max_duration
        self._buffer: queue.Queue[np.ndarray] = queue.Queue()
        self._last_callback: float = 0.0
        self._normal_exit = False
        self._running = False
        self._stream: sd.InputStream | None = None
        self._start_time: float = 0.0

    def run(self):
        self._running = True
        self._normal_exit = False
        self._buffer = queue.Queue()
        self._start_time = time_module.time()
        self._last_callback = self._start_time
        def callback(indata, frames, time_info, status):
            if self._running:
                self._buffer.put_nowait(indata.copy())
                self._last_callback = time_module.time()
        try:
            self._stream = sd.InputStream(
                samplerate=self.sr,
                channels=1,
                dtype="int16",
                callback=callback,
            )
            self._stream.start()
        except Exception as e:
            print(f"[recorder] 麦克风启动失败: {e}", file=sys.stderr, flush=True)
            self._running = False
            return
        while self._running:
            elapsed = time_module.time() - self._start_time
            idle = time_module.time() - self._last_callback
            if elapsed >= self.max_duration:
                self._running = False
                self._normal_exit = True
                break
            if idle > 2.0 and elapsed > 2.0:
                print(f"[recorder] 警告: 回调已 {idle:.0f}s 无新数据",
                      file=sys.stderr, flush=True)
                self._running = False
                self._normal_exit = True
                break
            sd.sleep(100)

    def drain(self) -> list[np.ndarray]:
        chunks = []
        while True:
            try:
                chunks.append(self._buffer.get_nowait())
            except queue.Empty:
                break
        return chunks

    def stop(self) -> np.ndarray | None:
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        chunks = self.drain()
        if not chunks:
            return None
        frames = sum(len(c) for c in chunks)
        audio = np.concatenate(chunks)
        print(f"[recorder] 共 {len(chunks)} 块 {frames} 帧 ({frames/self.sr:.1f}s)",
              file=sys.stderr, flush=True)
        return audio.astype(np.float32) / 32768.0
