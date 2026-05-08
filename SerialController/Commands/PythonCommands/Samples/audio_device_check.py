#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
音声デバイス診断ツール

1. PCに接続されている音声入力デバイスの一覧を表示
2. 指定デバイスから実際に音声を取り込み、音量レベルを表示
3. Switchの音がPCに届いているか目視で確認できる

=== 使い方 ===
1. このスクリプトを実行する
2. デバイス一覧が表示されるので、Switchの音が入力されているデバイスのindexを確認
3. CHECK_DEVICE_INDEX をそのindexに変更して再実行
4. Switchで何か音を鳴らし、音量バーが反応すれば音声取り込み成功
"""

from Commands.PythonCommandBase import PythonCommand

try:
    import pyaudio
except ImportError:
    pyaudio = None

import numpy as np


CHECK_DEVICE_INDEX = 1
SAMPLE_RATE = 48000
DURATION_SEC = 15


class AudioDeviceCheck(PythonCommand):
    NAME = "音声デバイス診断"

    def __init__(self):
        super().__init__()

    def do(self):
        if pyaudio is None:
            print("エラー: pyaudioがインストールされていません")
            print("  pip install pyaudio でインストールしてください")
            return

        pa = pyaudio.PyAudio()

        print("=" * 50)
        print("音声入力デバイス一覧")
        print("=" * 50)
        input_devices = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                input_devices.append(i)
                marker = " <<<" if i == CHECK_DEVICE_INDEX else ""
                print(f"  index={i}: {info['name']}")
                print(f"           入力ch={info['maxInputChannels']}, "
                      f"デフォルトSR={int(info['defaultSampleRate'])}Hz{marker}")

        if not input_devices:
            print("入力デバイスが見つかりません！")
            pa.terminate()
            return

        print()
        print(f"チェック対象: index={CHECK_DEVICE_INDEX}")
        target_info = pa.get_device_info_by_index(CHECK_DEVICE_INDEX)
        print(f"  デバイス名: {target_info['name']}")
        print()

        try:
            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=CHECK_DEVICE_INDEX,
                frames_per_buffer=1024,
            )
        except Exception as e:
            print(f"デバイス index={CHECK_DEVICE_INDEX} を開けませんでした: {e}")
            print()
            print("paFloat32で失敗した場合、paInt16で再試行します...")
            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=SAMPLE_RATE,
                    input=True,
                    input_device_index=CHECK_DEVICE_INDEX,
                    frames_per_buffer=1024,
                )
                print("paInt16で成功しました。shiny_sound_detector.pyのフォーマット変更が必要です。")
            except Exception as e2:
                print(f"paInt16でも失敗: {e2}")
                pa.terminate()
                return

        print("=" * 50)
        print(f"音量モニター開始 ({DURATION_SEC}秒間)")
        print("Switchで音を鳴らしてバーが動けばOK")
        print("=" * 50)

        format_is_float = stream._format == pyaudio.paFloat32
        chunks_per_sec = SAMPLE_RATE // 1024
        total_chunks = chunks_per_sec * DURATION_SEC
        max_seen = 0.0

        try:
            for i in range(total_chunks):
                if not self.checkIfAlive():
                    break

                raw = stream.read(1024, exception_on_overflow=False)
                if format_is_float:
                    samples = np.frombuffer(raw, dtype=np.float32)
                else:
                    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

                rms = float(np.sqrt(np.mean(samples ** 2)))
                peak = float(np.max(np.abs(samples)))
                max_seen = max(max_seen, peak)

                bar_len = int(min(rms * 200, 40))
                bar = "#" * bar_len + " " * (40 - bar_len)

                if i % 4 == 0:
                    status = "無音" if rms < 0.001 else "検出中"
                    print(f"\r  [{bar}] RMS={rms:.4f} Peak={peak:.4f} {status}   ", end="", flush=True)

        except Exception as e:
            print(f"\nエラー: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

        print()
        print("=" * 50)
        print(f"最大ピーク値: {max_seen:.4f}")
        if max_seen < 0.001:
            print("結果: 音声が取れていません！")
            print("  - デバイスindexが正しいか確認してください")
            print("  - Switchの音がPCに入力されているか確認してください")
            print("  - AUXケーブル接続やOBS仮想デバイスの設定を確認してください")
        elif max_seen < 0.01:
            print("結果: 音声は検出されましたが非常に小さいです")
            print("  - 音量を上げてみてください")
        else:
            print("結果: 音声取り込み成功！この設定で色違い検出が使えます")
            print(f"  DEVICE_INDEX = {CHECK_DEVICE_INDEX} を使ってください")
        print("=" * 50)
