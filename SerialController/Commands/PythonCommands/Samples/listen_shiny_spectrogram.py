#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
色違いの音をスペクトログラムマッチングで検出するサンプル

pokemon-automationのアルゴリズムをPythonに移植したものです。
事前に録音した色違いの音（WAVファイル）をテンプレートとして使い、
リアルタイム音声とスペクトログラム単位でスケール不変マッチングを行います。

=== 使い方 ===
1. 色違いの音のWAVファイルを用意し、TEMPLATE_PATH に設定
   - pokemon-automationの Resources/PokemonLGPE/ShinySound-48000.wav を使うか、
   - 自分で色違いの音を録音（48kHz, モノラル推奨）
2. DEVICE_INDEX を自分の環境の音声入力デバイスに合わせる
3. THRESHOLD を調整（低いほど厳密、デフォルト0.95はpokemon-automationと同じ）
"""

import os
import sys
from datetime import datetime

from Commands.Keys import Button
from Commands.PythonCommandBase import PythonCommand

# AudioDetection パッケージへのパスを通す
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from AudioDetection.shiny_sound_detector import ShinySoundDetector


# ====== 設定 ======
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "AudioDetection", "templates", "ShinySound-48000.wav")
DEVICE_INDEX = 1
SAMPLE_RATE = 48000
THRESHOLD = 0.95
LOW_FREQ_FILTER = 1000.0


class ListenShinySpectrogram(PythonCommand):
    NAME = "色違いの音検出(スペクトログラム版)"

    def __init__(self):
        super().__init__()
        self._shiny_found = False
        self._best_score = float("inf")

    def _on_shiny_detected(self, score: float):
        self._shiny_found = True
        self._best_score = min(self._best_score, score)
        t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"★ SHINY SOUND DETECTED! score={score:.4f} time={t}")
        self._logger.info(f"Shiny sound detected: score={score:.4f}")

    def do(self):
        if not os.path.exists(TEMPLATE_PATH):
            print(f"テンプレートファイルが見つかりません: {TEMPLATE_PATH}")
            print("色違いの音のWAVファイルを用意して TEMPLATE_PATH を設定してください")
            return

        print(f"テンプレート: {TEMPLATE_PATH}")
        print(f"デバイスIndex: {DEVICE_INDEX}")
        print(f"サンプルレート: {SAMPLE_RATE}")
        print(f"閾値: {THRESHOLD}")
        print("音声検出を開始します...")

        detector = ShinySoundDetector(
            template_path=TEMPLATE_PATH,
            on_detected=self._on_shiny_detected,
            device_index=DEVICE_INDEX,
            sample_rate=SAMPLE_RATE,
            threshold=THRESHOLD,
            low_frequency_filter=LOW_FREQ_FILTER,
        )
        detector.start()

        try:
            while True:
                if not self.checkIfAlive():
                    break
                self.wait(0.5)
        finally:
            detector.stop()
            print(f"検出終了 (最良スコア: {detector.lowest_score:.4f})")
