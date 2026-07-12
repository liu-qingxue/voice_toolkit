import queue
import time as time_module
import numpy as np
import sounddevice as sd
from config.config import CFG


class LiveRecorder:
    """录音器。run() 在子线程运行，stop() 在主线程调用取回音频。"""

    def __init__(self, max_duration: int | None = None):
        if max_duration is None:
            max_duration = CFG.max_duration or 60   # # 最长录音秒数
        self.sr = CFG.sample_rate
        self.max_duration = max_duration
        self._buffer: queue.Queue[np.ndarray] = queue.Queue()
        self._running = False
        self._stream: sd.InputStream | None = None
        self._start_time: float = 0.0

    def run(self):
        """在子线程中运行：启动音频流，不断采集到 buffer"""
        self._running = True
        self._buffer = queue.Queue()
        self._start_time = time_module.time()

        def callback(indata, frames, time_info, status):
            if self._running:
                self._buffer.put_nowait(indata.copy())

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
            if elapsed >= self.max_duration:
                break
            sd.sleep(100)

    def stop(self) -> np.ndarray | None:
        """停止录音，拼接所有音频块并返回归一化 float32 数组"""
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        chunks = []
        while True:
            try:
                chunks.append(self._buffer.get_nowait())
            except queue.Empty:
                break

        if not chunks:
            return None

        audio = np.concatenate(chunks)
        return audio.astype(np.float32) / 32768.0
