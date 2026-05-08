"""
Spectrogram-based audio template matcher.

Port of pokemon-automation's SpectrogramMatcher + ScaleInvariantMatrixMatch.
Detects sounds (e.g. shiny sparkle) by matching incoming audio spectrograms
against a pre-recorded template.
"""

import math
from collections import deque
from typing import Optional

import numpy as np
from scipy.io import wavfile
from scipy.fft import rfft

FFT_LENGTH_POWER = 12
NUM_FFT_SAMPLES = 1 << FFT_LENGTH_POWER  # 4096
FFT_SLIDING_WINDOW_STEP = NUM_FFT_SAMPLES // 4  # 1024
NUM_FREQUENCIES = NUM_FFT_SAMPLES // 2  # 2048


def _build_spike_kernel(num_frequencies: int, half_sample_rate: int) -> np.ndarray:
    num_kernel_intervals = int(199.21875 * num_frequencies / half_sample_rate + 0.5)
    slope_len = num_kernel_intervals // 2
    kernel = []
    for i in range(slope_len + 1):
        kernel.append(-4.0 + 8.0 * i / slope_len)
    for i in range((num_kernel_intervals + 1) % 2, slope_len + 1):
        kernel.append(-4.0 + 8.0 * (slope_len - i) / slope_len)
    return np.array(kernel, dtype=np.float32)


def _compute_fft_magnitude(samples: np.ndarray) -> np.ndarray:
    spectrum = rfft(samples)
    return np.abs(spectrum[:NUM_FREQUENCIES]).astype(np.float32)


def _load_audio_template(filepath: str, target_sample_rate: int) -> np.ndarray:
    """Load a WAV file and build its spectrogram matrix (windows x frequencies)."""
    sr, data = wavfile.read(filepath)

    if data.ndim > 1:
        data = data[:, 0]
    data = data.astype(np.float32)
    if data.dtype == np.int16:
        pass
    if np.max(np.abs(data)) > 2.0:
        data = data / 32768.0

    if sr != target_sample_rate:
        from scipy.signal import resample
        num_target = int(len(data) * target_sample_rate / sr)
        data = resample(data, num_target).astype(np.float32)

    num_samples = len(data)
    if num_samples < NUM_FFT_SAMPLES:
        padded = np.zeros(NUM_FFT_SAMPLES, dtype=np.float32)
        padded[:num_samples] = data
        mag = _compute_fft_magnitude(padded)
        return mag.reshape(1, -1)

    num_windows = (num_samples - NUM_FFT_SAMPLES) // FFT_SLIDING_WINDOW_STEP + 1
    spectrogram = np.zeros((num_windows, NUM_FREQUENCIES), dtype=np.float32)
    for i in range(num_windows):
        start = i * FFT_SLIDING_WINDOW_STEP
        chunk = data[start : start + NUM_FFT_SAMPLES]
        spectrogram[i] = _compute_fft_magnitude(chunk)
    return spectrogram


def _spike_conv(spectrum: np.ndarray, kernel: np.ndarray, freq_start: int, freq_end: int) -> np.ndarray:
    segment = spectrum[freq_start:freq_end]
    return np.convolve(segment, kernel, mode="valid").astype(np.float32)


class SpectrogramMatcher:
    """
    Scale-invariant spectrogram template matcher.

    Ported from pokemon-automation's SpectrogramMatcher (SPIKE_CONV mode).
    """

    def __init__(
        self,
        template_path: str,
        sample_rate: int = 48000,
        low_frequency_filter: float = 1000.0,
    ):
        self._sample_rate = sample_rate
        half_sr = sample_rate // 2

        raw_template = _load_audio_template(template_path, sample_rate)
        num_orig_freq = raw_template.shape[1]

        self._orig_freq_start = int(low_frequency_filter * num_orig_freq / half_sr + 0.5)
        self._orig_freq_end = min(20000 * num_orig_freq // half_sr + 1, num_orig_freq)

        self._kernel = _build_spike_kernel(num_orig_freq, half_sr)

        num_windows = raw_template.shape[0]
        conv_len = (self._orig_freq_end - self._orig_freq_start) - len(self._kernel) + 1
        if conv_len <= 0:
            raise ValueError("Template frequency range too narrow for spike convolution kernel")

        conv_template = np.zeros((num_windows, conv_len), dtype=np.float32)
        for i in range(num_windows):
            conv_template[i] = _spike_conv(
                raw_template[i], self._kernel, self._orig_freq_start, self._orig_freq_end
            )

        self._template = conv_template
        self._num_freqs = conv_len
        self._num_windows_needed = num_windows
        self._template_norm = float(np.sqrt(np.sum(conv_template ** 2)))

        self._spectrums: deque = deque(maxlen=num_windows)
        self._last_stamp = -1
        self._stamp_counter = 0

    @property
    def num_windows_needed(self) -> int:
        return self._num_windows_needed

    def clear(self):
        self._spectrums.clear()
        self._stamp_counter = 0
        self._last_stamp = -1

    def _process_spectrum(self, raw_magnitudes: np.ndarray) -> np.ndarray:
        return _spike_conv(raw_magnitudes, self._kernel, self._orig_freq_start, self._orig_freq_end)

    def feed_and_match(self, raw_magnitudes: np.ndarray) -> float:
        """
        Feed one FFT magnitude spectrum and attempt matching.

        Returns the match score (0 = perfect match, 1 = no match).
        Returns float('inf') if not enough windows accumulated yet.
        """
        if len(raw_magnitudes) < self._orig_freq_end:
            return float("inf")

        conv_spectrum = self._process_spectrum(raw_magnitudes)
        self._stamp_counter += 1
        self._spectrums.appendleft(conv_spectrum)

        if len(self._spectrums) < self._num_windows_needed:
            return float("inf")

        # Build matrices A (input) and T (template)
        windows = self._num_windows_needed
        A = np.array([self._spectrums[i] for i in range(windows)], dtype=np.float32)
        T = np.array([self._template[windows - 1 - i] for i in range(windows)], dtype=np.float32)

        # Scale-invariant matching: s = sum(A*T) / sum(A*A)
        sum_at = float(np.sum(A * T))
        sum_a2 = float(np.sum(A * A))
        scale = sum_at / sum_a2 if sum_a2 > 1e-6 else 1.0
        scale = min(scale, 1_000_000.0)

        # Error: sqrt(sum((s*A - T)^2)) / ||T||
        diff = scale * A - T
        error = math.sqrt(float(np.sum(diff ** 2)))
        score = error / self._template_norm if self._template_norm > 0 else 1.0
        return min(score, 1.0)
