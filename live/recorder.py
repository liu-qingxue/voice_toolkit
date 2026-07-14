import queue
import time as time_module
import numpy as np
import sounddevice as sd
from config import CFG
import sys
import logging

# sound--声音
logger = logging.getLogger("live/recorder.py")
class LiveRecorder:
    """录音器。run() 在子线程运行，stop() 在主线程调用取回音频。"""

    def __init__(self, max_duration: int | None = None):
        if max_duration is None:
            max_duration = CFG.max_duration or 60   # # 最长录音秒数
        self.sample_rate = CFG.sample_rate
        self.dtype = CFG.dtype
        self.cannels = CFG.channels
        self.max_duration = max_duration

        self._running = False
        self._buffer: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None

        self._start_time: float = 0.0   # 记录开始时间,用于录音超时

    def run(self):
        """在子线程中运行：启动音频流，不断采集到 buffer"""
        self._running = True
        self._buffer = queue.Queue()   # 重置了队列,防止队列残留
        self._start_time = time_module.time()   # 记录开始时间

        def callback(indata, frames, time_info, status):   # 位置约定!!!第一个参数被 sounddevice.InputStream的数组传入
            if self._running:
                self._buffer.put_nowait(indata.copy())   # 注意要用copy

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.cannels,
                dtype=self.dtype,
                callback=callback,
            )
            self._stream.start()   # 开始录音
            logger.info("录音开始!")
        except Exception as e:
            logger.error(f"麦克风启动失败: {e}")
            self._running = False
            return

        while self._running:
            elapsed = time_module.time() - self._start_time
            if elapsed >= self.max_duration:
                logger.info(f"录音超时,当前阈值为: {self.max_duration}")
                
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
                chunks.append(self._buffer.get_nowait())  # 一直处理队列,然后到报错(queue.Empty是空的报错)
            except queue.Empty:
                break

        if not chunks:
            logger.warning("最终的录音结果数组(chunks)为空!")
            return None

        audio = np.concatenate(chunks)  # concatenate-连接/串联 ,返回一个大的数组
        return audio.astype(np.float32) / 32768.0
