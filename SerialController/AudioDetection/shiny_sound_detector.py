"""
Async shiny sound detector.

Runs audio capture and spectrogram matching in a background thread,
calling a callback when the shiny sparkle sound is detected.
Does not block the main poke-controller thread.
"""

import threading
import time
from logging import getLogger, DEBUG, NullHandler
from typing import Callable, Optional

import numpy as np

from .spectrogram_matcher import (
    SpectrogramMatcher,
    NUM_FFT_SAMPLES,
    FFT_SLIDING_WINDOW_STEP,
    NUM_FREQUENCIES,
    _compute_fft_magnitude,
)

logger = getLogger(__name__)
logger.addHandler(NullHandler())
logger.setLevel(DEBUG)


class ShinySoundDetector:
    """
    Background audio listener that detects shiny sparkle sounds.

    Usage:
        def on_shiny(score):
            print(f"Shiny detected! score={score:.4f}")

        detector = ShinySoundDetector(
            template_path="path/to/ShinySound-48000.wav",
            on_detected=on_shiny,
            device_index=1,
        )
        detector.start()
        # ... do other stuff ...
        detector.stop()
    """

    def __init__(
        self,
        template_path: str,
        on_detected: Callable[[float], None],
        device_index: int = 1,
        sample_rate: int = 48000,
        threshold: float = 0.95,
        low_frequency_filter: float = 1000.0,
        debounce_sec: float = 1.0,
    ):
        self._template_path = template_path
        self._on_detected = on_detected
        self._device_index = device_index
        self._sample_rate = sample_rate
        self._threshold = threshold
        self._low_frequency_filter = low_frequency_filter
        self._debounce_sec = debounce_sec

        self._thread: Optional[threading.Thread] = None
        self._alive = False
        self._lock = threading.Lock()

        self._lowest_score = float("inf")
        self._last_detection_time = 0.0
        self._total_samples_processed = 0

    @property
    def lowest_score(self) -> float:
        return self._lowest_score

    @property
    def is_running(self) -> bool:
        return self._alive and self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            logger.warning("ShinySoundDetector is already running")
            return
        self._alive = True
        self._lowest_score = float("inf")
        self._total_samples_processed = 0
        self._thread = threading.Thread(target=self._run, daemon=True, name="ShinySoundDetector")
        self._thread.start()
        logger.info("ShinySoundDetector started (device=%d, sr=%d, threshold=%.2f)",
                     self._device_index, self._sample_rate, self._threshold)

    def stop(self):
        self._alive = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("ShinySoundDetector stopped (lowest_score=%.4f, samples=%d)",
                     self._lowest_score, self._total_samples_processed)

    def _run(self):
        try:
            import pyaudio
        except ImportError:
            logger.error("pyaudio is not installed. Cannot capture audio.")
            self._alive = False
            return

        matcher = SpectrogramMatcher(
            template_path=self._template_path,
            sample_rate=self._sample_rate,
            low_frequency_filter=self._low_frequency_filter,
        )

        pa = pyaudio.PyAudio()
        stream = None
        try:
            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self._sample_rate,
                input=True,
                input_device_index=self._device_index,
                frames_per_buffer=FFT_SLIDING_WINDOW_STEP,
            )
            logger.info("Audio stream opened: %s", pa.get_device_info_by_index(self._device_index).get("name", "?"))

            ring_buffer = np.zeros(NUM_FFT_SAMPLES, dtype=np.float32)

            while self._alive and stream.is_active():
                raw = stream.read(FFT_SLIDING_WINDOW_STEP, exception_on_overflow=False)
                new_samples = np.frombuffer(raw, dtype=np.float32)

                ring_buffer = np.roll(ring_buffer, -FFT_SLIDING_WINDOW_STEP)
                ring_buffer[-FFT_SLIDING_WINDOW_STEP:] = new_samples
                self._total_samples_processed += FFT_SLIDING_WINDOW_STEP

                if self._total_samples_processed < NUM_FFT_SAMPLES:
                    continue

                magnitudes = _compute_fft_magnitude(ring_buffer)
                score = matcher.feed_and_match(magnitudes)

                if score < self._lowest_score:
                    self._lowest_score = score

                if score <= self._threshold:
                    now = time.monotonic()
                    if now - self._last_detection_time >= self._debounce_sec:
                        self._last_detection_time = now
                        logger.info("SHINY DETECTED! score=%.4f (threshold=%.2f)", score, self._threshold)
                        try:
                            self._on_detected(score)
                        except Exception as e:
                            logger.error("on_detected callback error: %s", e)

        except Exception as e:
            logger.error("ShinySoundDetector error: %s", e)
            import traceback
            traceback.print_exc()
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            pa.terminate()
            self._alive = False
