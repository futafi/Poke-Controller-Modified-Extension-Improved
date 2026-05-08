#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
色違いの音をスペクトログラムマッチングで検出するサンプル

pokemon-automationのアルゴリズムをPythonに移植したものです。
事前に録音した色違いの音をテンプレートとして使い、
リアルタイム音声とスペクトログラム単位でスケール不変マッチングを行います。

=== 使い方 ===
1. GAME_TITLE を対象ゲームに合わせて変更する
2. DEVICE_INDEX を自分の環境の音声入力デバイスに合わせる
3. THRESHOLD を調整（低いほど厳密、デフォルト0.95はpokemon-automationと同じ）

=== 対応タイトル ===
- LGPE  : Let's Go ピカチュウ / イーブイ
- BDSP  : ブリリアントダイヤモンド / シャイニングパール
- LA    : LEGENDS アルセウス
- SV    : スカーレット / バイオレット
- FRLG  : ファイアレッド / リーフグリーン
- RSE   : ルビー / サファイア / エメラルド
"""

import os
import sys
from datetime import datetime

from Commands.Keys import Button
from Commands.PythonCommandBase import PythonCommand

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from AudioDetection.shiny_sound_detector import ShinySoundDetector

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "AudioDetection", "templates")

GAME_TEMPLATES = {
    "LGPE": os.path.join(_TEMPLATES_DIR, "LGPE_ShinySound-48000.wav"),
    "BDSP": os.path.join(_TEMPLATES_DIR, "BDSP_ShinySound-48000.wav"),
    "LA":   os.path.join(_TEMPLATES_DIR, "LA_ShinySound-48000.wav"),
    "SV":   os.path.join(_TEMPLATES_DIR, "SV_ShinySound-48000.mp3"),
    "FRLG": os.path.join(_TEMPLATES_DIR, "FRLG_ShinySound-48000.wav"),
    "RSE":  os.path.join(_TEMPLATES_DIR, "RSE_ShinySound-48000.wav"),
}

# ====== 設定 ======
GAME_TITLE = "LGPE"
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
        if GAME_TITLE not in GAME_TEMPLATES:
            print(f"未対応のタイトル: {GAME_TITLE}")
            print(f"対応タイトル: {', '.join(GAME_TEMPLATES.keys())}")
            return

        template_path = GAME_TEMPLATES[GAME_TITLE]
        if not os.path.exists(template_path):
            print(f"テンプレートファイルが見つかりません: {template_path}")
            return

        print(f"対象タイトル: {GAME_TITLE}")
        print(f"テンプレート: {os.path.basename(template_path)}")
        print(f"デバイスIndex: {DEVICE_INDEX}")
        print(f"サンプルレート: {SAMPLE_RATE}")
        print(f"閾値: {THRESHOLD}")
        print("音声検出を開始します...")

        detector = ShinySoundDetector(
            template_path=template_path,
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
