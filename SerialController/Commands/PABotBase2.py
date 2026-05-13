#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import random
import struct
import threading
import time
from collections import deque
from enum import IntEnum
from logging import DEBUG, NullHandler, getLogger
from typing import Any


class PABotBase2Error(RuntimeError):
    pass


class ControllerMode(IntEnum):
    NONE = 0x0000
    NINTENDO_SWITCH_WIRED_CONTROLLER = 0x1000
    NINTENDO_SWITCH2_WIRED_CONTROLLER = 0x1010
    NINTENDO_SWITCH_WIRELESS_PRO_CONTROLLER = 0x1180
    NINTENDO_SWITCH_WIRELESS_LEFT_JOYCON = 0x1181
    NINTENDO_SWITCH_WIRELESS_RIGHT_JOYCON = 0x1182
    NINTENDO_SWITCH_WIRED_PRO_CONTROLLER = 0x1100
    NINTENDO_SWITCH_WIRED_LEFT_JOYCON = 0x1101
    NINTENDO_SWITCH_WIRED_RIGHT_JOYCON = 0x1102


PABOTBASE2_CONTROLLER_MODE_NAMES = (
    "Wireless Pro Controller",
    "Wireless Left Joy-Con",
    "Wireless Right Joy-Con",
    "Wired Controller",
    "Switch 2 Wired Controller",
    "Wired Pro Controller",
    "Wired Left Joy-Con",
    "Wired Right Joy-Con",
)

PABOTBASE2_CONTROLLER_MODE_BY_NAME = {
    "Wireless Pro Controller": ControllerMode.NINTENDO_SWITCH_WIRELESS_PRO_CONTROLLER,
    "Wireless Left Joy-Con": ControllerMode.NINTENDO_SWITCH_WIRELESS_LEFT_JOYCON,
    "Wireless Right Joy-Con": ControllerMode.NINTENDO_SWITCH_WIRELESS_RIGHT_JOYCON,
    "Wired Controller": ControllerMode.NINTENDO_SWITCH_WIRED_CONTROLLER,
    "Switch 2 Wired Controller": ControllerMode.NINTENDO_SWITCH2_WIRED_CONTROLLER,
    "Wired Pro Controller": ControllerMode.NINTENDO_SWITCH_WIRED_PRO_CONTROLLER,
    "Wired Left Joy-Con": ControllerMode.NINTENDO_SWITCH_WIRED_LEFT_JOYCON,
    "Wired Right Joy-Con": ControllerMode.NINTENDO_SWITCH_WIRED_RIGHT_JOYCON,
}

PABOTBASE2_CONTROLLER_MODE_NAME_BY_MODE = {
    mode: name for name, mode in PABOTBASE2_CONTROLLER_MODE_BY_NAME.items()
}

PABOTBASE2_LEFT_JOYCON_MODES = frozenset(
    {
        ControllerMode.NINTENDO_SWITCH_WIRELESS_LEFT_JOYCON,
        ControllerMode.NINTENDO_SWITCH_WIRED_LEFT_JOYCON,
    }
)
PABOTBASE2_RIGHT_JOYCON_MODES = frozenset(
    {
        ControllerMode.NINTENDO_SWITCH_WIRELESS_RIGHT_JOYCON,
        ControllerMode.NINTENDO_SWITCH_WIRED_RIGHT_JOYCON,
    }
)
PABOTBASE2_WIRED_CONTROLLER_MODES = frozenset(
    {
        ControllerMode.NINTENDO_SWITCH_WIRED_CONTROLLER,
        ControllerMode.NINTENDO_SWITCH2_WIRED_CONTROLLER,
    }
)
PABOTBASE2_OEM_CONTROLLER_MODES = frozenset(
    {
        ControllerMode.NINTENDO_SWITCH_WIRELESS_PRO_CONTROLLER,
        ControllerMode.NINTENDO_SWITCH_WIRELESS_LEFT_JOYCON,
        ControllerMode.NINTENDO_SWITCH_WIRELESS_RIGHT_JOYCON,
        ControllerMode.NINTENDO_SWITCH_WIRED_PRO_CONTROLLER,
        ControllerMode.NINTENDO_SWITCH_WIRED_LEFT_JOYCON,
        ControllerMode.NINTENDO_SWITCH_WIRED_RIGHT_JOYCON,
    }
)


def controller_mode_from_name(mode_name: str) -> ControllerMode:
    try:
        return PABOTBASE2_CONTROLLER_MODE_BY_NAME[mode_name]
    except KeyError as e:
        raise PABotBase2Error(f"Unsupported PABotBase2 controller mode: {mode_name}") from e


def controller_mode_name(mode: ControllerMode | int) -> str:
    mode = ControllerMode(mode)
    return PABOTBASE2_CONTROLLER_MODE_NAME_BY_MODE.get(mode, f"0x{int(mode):04x}")


def controller_mode_is_left_joycon(mode_name: str) -> bool:
    return controller_mode_from_name(mode_name) in PABOTBASE2_LEFT_JOYCON_MODES


def controller_mode_is_right_joycon(mode_name: str) -> bool:
    return controller_mode_from_name(mode_name) in PABOTBASE2_RIGHT_JOYCON_MODES


PABB2_CONNECTION_MAGIC_NUMBER = 0x81
PABB2_CONNECTION_PROTOCOL_VERSION = 2026041102
PABB2_CONNECTION_RESET_SESSION_ID = 0xFFFFFFFF
PABB2_MESSAGE_PROTOCOL_VERSION = 2026050901
PABB2_MIN_FIRMWARE_VERSION = 2026051001
PABB2_DEVICE_LOGGING_FLAG = 0

PABB2_CONNECTION_RETRANSMIT_FLAG = 0x80
PABB2_CONNECTION_OPCODE_MASK = 0x7F

PABB2_CONNECTION_OPCODE_ASK_RESET = 0x01
PABB2_CONNECTION_OPCODE_RET_RESET = 0x41
PABB2_CONNECTION_OPCODE_ASK_VERSION = 0x02
PABB2_CONNECTION_OPCODE_RET_VERSION = 0x42
PABB2_CONNECTION_OPCODE_ASK_PACKET_SIZE = 0x03
PABB2_CONNECTION_OPCODE_RET_PACKET_SIZE = 0x43
PABB2_CONNECTION_OPCODE_ASK_BUFFER_SLOTS = 0x04
PABB2_CONNECTION_OPCODE_RET_BUFFER_SLOTS = 0x44
PABB2_CONNECTION_OPCODE_ASK_BUFFER_BYTES = 0x05
PABB2_CONNECTION_OPCODE_RET_BUFFER_BYTES = 0x45
PABB2_CONNECTION_OPCODE_ASK_STREAM_DATA = 0x12
PABB2_CONNECTION_OPCODE_RET_STREAM_DATA = 0x52

PABB2_CONNECTION_OPCODE_INFO_STREAM_DEAD = 0x10
PABB2_CONNECTION_OPCODE_INFO_STREAM_NOT_READY = 0x11
PABB2_CONNECTION_OPCODE_INFO_STREAM_SEND_FULL = 0x18
PABB2_CONNECTION_OPCODE_INFO_STREAM_RECV_FULL = 0x19
PABB2_CONNECTION_OPCODE_UNKNOWN_OPCODE = 0x32

PABB2_MESSAGE_OPCODE_RET = 0x11
PABB2_MESSAGE_OPCODE_RET_U32 = 0x12
PABB2_MESSAGE_OPCODE_RET_DATA = 0x13
PABB2_MESSAGE_OPCODE_RET_U32_DATA = 0x14
PABB2_MESSAGE_OPCODE_PROTOCOL_VERSION = 0x20
PABB2_MESSAGE_OPCODE_FIRMWARE_VERSION = 0x21
PABB2_MESSAGE_OPCODE_DEVICE_IDENTIFIER = 0x22
PABB2_MESSAGE_OPCODE_DEVICE_NAME = 0x23
PABB2_MESSAGE_OPCODE_CONTROLLER_LIST = 0x24
PABB2_MESSAGE_OPCODE_SET_LOGGING_FLAG = 0x25
PABB2_MESSAGE_OPCODE_CQ_CAPACITY = 0x28
PABB2_MESSAGE_OPCODE_READ_CONTROLLER_MODE = 0x30
PABB2_MESSAGE_OPCODE_CHANGE_CONTROLLER_MODE = 0x31
PABB2_MESSAGE_OPCODE_RESET_TO_CONTROLLER = 0x32
PABB2_MESSAGE_OPCODE_REQUEST_STATUS = 0x35
PABB2_MESSAGE_OPCODE_CQ_CANCEL = 0x41
PABB2_MESSAGE_OPCODE_CQ_COMMAND_FINISHED = 0x43

PABB2_MESSAGE_CMD_NS_WIRED_CONTROLLER_STATE = 0x90
PABB2_MESSAGE_CMD_NS1_OEM_CONTROLLER_BUTTONS = 0x97

MESSAGE_HEADER_SIZE = 4
PACKET_HEADER_SIZE = 4
PACKET_DATA_HEADER_SIZE = 6
CRC_SIZE = 4
DEFAULT_PACKET_SIZE = 24
DEFAULT_REMOTE_SLOTS = 1
CONNECT_BAUD_RATES = (921600, 115200)
PABOTBASE2_STATE_HOLD_MS = 65535

RETRANSMIT_INTERVAL_S = 0.2
RETRANSMIT_THREAD_POLL_S = 0.1


def _make_crc32c_table() -> list[int]:
    table: list[int] = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x82F63B78
            else:
                crc >>= 1
        table.append(crc & 0xFFFFFFFF)
    return table


CRC32C_TABLE = _make_crc32c_table()


def pabb_crc32(seed: int, data: bytes) -> int:
    crc = seed & 0xFFFFFFFF
    for byte in data:
        crc = CRC32C_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc & 0xFFFFFFFF


def packet_with_crc(seed: int, body: bytes) -> bytes:
    return body + struct.pack("<I", pabb_crc32(seed, body))


_COALESCER_SLOTS = 128
_COALESCER_SLOTS_MASK = _COALESCER_SLOTS - 1
_COALESCER_BUFFER_SIZE = 16384
_COALESCER_BUFFER_MASK = _COALESCER_BUFFER_SIZE - 1


class StreamCoalescer:
    """Reorder and coalesce incoming stream packets that may arrive out of order.

    Port of pokemon-automation's PABotBase2_StreamCoalescer.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.slot_head: int = 0
        self.slot_tail: int = 0
        self.stream_free: int = 0
        self.stream_head: int = 0
        self.stream_tail: int = 0
        self.lengths: list[int] = [0] * _COALESCER_SLOTS
        self.end_offsets: list[int] = [0] * _COALESCER_SLOTS
        self.buffer: bytearray = bytearray(_COALESCER_BUFFER_SIZE)

    def free_bytes(self) -> int:
        if self.slot_head == self.slot_tail:
            return _COALESCER_BUFFER_SIZE
        return (self.stream_free - self.stream_tail) & _COALESCER_BUFFER_MASK

    def push_stream(self, seqnum: int, stream_offset: int, payload: bytes) -> bool:
        self._advance_slot_head()

        stream_size = len(payload)
        if stream_size == 0:
            self._push_packet(seqnum)
            return True

        if stream_size > _COALESCER_BUFFER_SIZE:
            return False

        diff = (seqnum - self.slot_head) & 0xFF
        if diff >= _COALESCER_SLOTS:
            return bool(diff & 0x80)

        stream_offset_e = (stream_offset + stream_size) & 0xFFFF
        if ((stream_offset_e - self.stream_free) & 0xFFFF) > _COALESCER_BUFFER_SIZE:
            return False

        slot_tail = self.slot_tail
        if ((seqnum - slot_tail) & 0xFF) < _COALESCER_SLOTS:
            self.slot_tail = (seqnum + 1) & 0xFF

        stream_tail = self.stream_tail
        if ((stream_offset_e - stream_tail) & 0xFFFF) < _COALESCER_BUFFER_SIZE:
            self.stream_tail = stream_offset_e

        index = seqnum & _COALESCER_SLOTS_MASK
        self.lengths[index] = stream_size
        self.end_offsets[index] = stream_offset_e
        self._write_buffer(payload, stream_offset)
        return True

    def read(self, max_bytes: int = 4096) -> bytes:
        self._advance_slot_head()
        available = (self.stream_head - self.stream_free) & 0xFFFF
        to_read = min(available, max_bytes)
        if to_read == 0:
            return b""
        data = self._read_buffer(self.stream_free, to_read)
        self.stream_free = (self.stream_free + to_read) & 0xFFFF
        return data

    def _push_packet(self, seqnum: int) -> None:
        diff = (seqnum - self.slot_head) & 0xFF
        if diff >= _COALESCER_SLOTS:
            return

        slot_tail = self.slot_tail
        if ((seqnum - slot_tail) & 0xFF) < _COALESCER_SLOTS:
            self.slot_tail = (seqnum + 1) & 0xFF

        self.lengths[seqnum & _COALESCER_SLOTS_MASK] = 0xFF
        self._advance_slot_head()

    def _advance_slot_head(self) -> None:
        while self.slot_head != self.slot_tail:
            index = self.slot_head & _COALESCER_SLOTS_MASK
            length = self.lengths[index]
            if length == 0:
                break
            if length != 0xFF:
                self.stream_head = self.end_offsets[index]
            self.lengths[index] = 0
            self.slot_head = (self.slot_head + 1) & 0xFF

    def _write_buffer(self, data: bytes, stream_offset: int) -> None:
        if not data:
            return
        start = stream_offset & _COALESCER_BUFFER_MASK
        end = (stream_offset + len(data)) & _COALESCER_BUFFER_MASK
        if start < end:
            self.buffer[start:end] = data
        else:
            first = _COALESCER_BUFFER_SIZE - start
            self.buffer[start:_COALESCER_BUFFER_SIZE] = data[:first]
            self.buffer[:end] = data[first:]

    def _read_buffer(self, stream_offset: int, length: int) -> bytes:
        if length == 0:
            return b""
        start = stream_offset & _COALESCER_BUFFER_MASK
        end = (stream_offset + length) & _COALESCER_BUFFER_MASK
        if start < end:
            return bytes(self.buffer[start:end])
        first = _COALESCER_BUFFER_SIZE - start
        return bytes(self.buffer[start:_COALESCER_BUFFER_SIZE]) + bytes(self.buffer[:end])


class PABotBase2Connection:
    def __init__(self, serial_port: Any, controller_mode: ControllerMode | int = ControllerMode.NINTENDO_SWITCH_WIRELESS_PRO_CONTROLLER):
        self.serial = serial_port
        self.controller_mode = ControllerMode(controller_mode)
        self.session_id = 0
        self.max_packet_size = DEFAULT_PACKET_SIZE
        self.remote_slot_capacity = DEFAULT_REMOTE_SLOTS
        self.seqnum = 0
        self.pending_packets: dict[int, tuple[bytes, float]] = {}
        self.stream_offset = 0
        self._recv_coalescer = StreamCoalescer()
        self.packet_buffer = bytearray()
        self.stream_buffer = bytearray()
        self.responses: dict[int, bytes] = {}
        self.request_id = 0
        self.command_id = 0
        self.command_queue_capacity = 4
        self.connected = False
        self.device_name = ""
        self.device_firmware_version = 0
        self.device_protocol = 0
        self.device_id = 0
        self.supported_controller_modes: set[ControllerMode] = set()
        self.bad_crc_packets = 0

        self._retransmit_stop = threading.Event()
        self._retransmit_thread: threading.Thread | None = None

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

    def connect(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self.serial.baudrate = 921600
                self._reset_input_buffer()
                self._reset(random_session_id=False, timeout=0.1)
                self._finish_connect()
                self._start_retransmit_thread()
                return
            except Exception as e:
                if self._is_fatal_connect_error(e):
                    raise
                last_error = e
                self._reset_runtime_state()
            for baudrate in CONNECT_BAUD_RATES:
                if time.monotonic() >= deadline:
                    break
                try:
                    self.serial.baudrate = baudrate
                    self._reset_input_buffer()
                    self._reset(random_session_id=True, timeout=0.1)
                    self._finish_connect()
                    self._start_retransmit_thread()
                    return
                except Exception as e:
                    if self._is_fatal_connect_error(e):
                        raise
                    last_error = e
                    self._reset_runtime_state()

        if last_error is not None:
            raise PABotBase2Error(f"Unable to connect to PABotBase2 device: {last_error}") from last_error
        raise PABotBase2Error("Unable to connect to PABotBase2 device.")

    @staticmethod
    def _is_fatal_connect_error(error: Exception) -> bool:
        if not isinstance(error, PABotBase2Error):
            return False
        message = str(error)
        return (
            "does not support selected controller mode" in message
            or "Incompatible PABotBase2 message protocol" in message
            or "Incompatible PABotBase2 firmware version" in message
        )

    def _finish_connect(self) -> None:
        self._send_connection_request(PABB2_CONNECTION_OPCODE_ASK_VERSION, timeout=0.5)
        if self.remote_connection_protocol_major != PABB2_CONNECTION_PROTOCOL_VERSION // 100:
            raise PABotBase2Error(
                f"Incompatible PABotBase2 connection protocol: {self.remote_connection_protocol}"
            )
        self._send_connection_request(PABB2_CONNECTION_OPCODE_ASK_PACKET_SIZE, timeout=0.5)
        self._send_connection_request(PABB2_CONNECTION_OPCODE_ASK_BUFFER_SLOTS, timeout=0.5)
        self._connect_device()
        self._set_controller_mode(self.controller_mode)
        self.connected = True

    @property
    def remote_connection_protocol(self) -> int:
        return getattr(self, "_remote_connection_protocol", 0)

    @property
    def remote_connection_protocol_major(self) -> int:
        return self.remote_connection_protocol // 100

    def close(self) -> None:
        self.connected = False
        self._stop_retransmit_thread()

    def _start_retransmit_thread(self) -> None:
        self._retransmit_stop.clear()
        self._retransmit_thread = threading.Thread(
            target=self._retransmit_thread_func, daemon=True
        )
        self._retransmit_thread.start()

    def _stop_retransmit_thread(self) -> None:
        self._retransmit_stop.set()
        t = self._retransmit_thread
        if t is not None:
            t.join(timeout=1.0)
            self._retransmit_thread = None

    def _retransmit_thread_func(self) -> None:
        while not self._retransmit_stop.wait(RETRANSMIT_THREAD_POLL_S):
            if not self.connected:
                continue
            if not self.pending_packets:
                continue
            try:
                self._maybe_retransmit()
            except Exception:
                pass

    def send_controller_state(self, send_format: Any) -> None:
        if not self.connected:
            raise PABotBase2Error("PABotBase2 connection is not open.")
        self._drain_input(0)
        self._send_message_no_response(bytes([MESSAGE_HEADER_SIZE, 0, PABB2_MESSAGE_OPCODE_CQ_CANCEL, 0]))
        message = self._build_controller_state(send_format, PABOTBASE2_STATE_HOLD_MS)
        self._send_command_message(message)

    def neutral(self) -> None:
        class NeutralFormat:
            format = {
                "btn": 0,
                "hat": 8,
                "lx": 128,
                "ly": 128,
                "rx": 128,
                "ry": 128,
            }

        self.send_controller_state(NeutralFormat())

    def _reset_runtime_state(self) -> None:
        self.session_id = 0
        self.max_packet_size = DEFAULT_PACKET_SIZE
        self.remote_slot_capacity = DEFAULT_REMOTE_SLOTS
        self.seqnum = 0
        self.pending_packets.clear()
        self.stream_offset = 0
        self._recv_coalescer.reset()
        self.packet_buffer.clear()
        self.stream_buffer.clear()
        self.responses.clear()
        self.connected = False
        self.supported_controller_modes.clear()

    def _reset_input_buffer(self) -> None:
        if hasattr(self.serial, "reset_input_buffer"):
            self.serial.reset_input_buffer()

    def _reset(self, random_session_id: bool, timeout: float) -> None:
        self._reset_runtime_state()
        if random_session_id:
            self.session_id = random.getrandbits(32)
            if self.session_id == PABB2_CONNECTION_RESET_SESSION_ID:
                self.session_id = PABB2_CONNECTION_RESET_SESSION_ID - 1
            body = struct.pack(
                "<BBBBI",
                PABB2_CONNECTION_MAGIC_NUMBER,
                self.seqnum,
                PACKET_HEADER_SIZE + 4 + CRC_SIZE,
                PABB2_CONNECTION_OPCODE_ASK_RESET,
                self.session_id,
            )
            self._send_packet_body(body, seed=PABB2_CONNECTION_RESET_SESSION_ID)
        else:
            self.session_id = PABB2_CONNECTION_RESET_SESSION_ID
            body = struct.pack(
                "<BBBB",
                PABB2_CONNECTION_MAGIC_NUMBER,
                self.seqnum,
                PACKET_HEADER_SIZE + CRC_SIZE,
                PABB2_CONNECTION_OPCODE_ASK_RESET,
            )
            self._send_packet_body(body, seed=self.session_id)
        self.seqnum = (self.seqnum + 1) & 0xFF
        self._wait_for_pending(timeout)

    def _send_connection_request(self, opcode: int, timeout: float) -> None:
        body = struct.pack(
            "<BBBB",
            PABB2_CONNECTION_MAGIC_NUMBER,
            self.seqnum,
            PACKET_HEADER_SIZE + CRC_SIZE,
            opcode,
        )
        self._send_packet_body(body, seed=self.session_id)
        self.seqnum = (self.seqnum + 1) & 0xFF
        self._wait_for_pending(timeout)

    def _send_stream(self, data: bytes, timeout: float = 2.0) -> None:
        payload_capacity = self.max_packet_size - PACKET_DATA_HEADER_SIZE - CRC_SIZE
        if payload_capacity <= 0:
            raise PABotBase2Error(f"Invalid PABotBase2 packet size: {self.max_packet_size}")

        pending = 0
        offset = 0
        while offset < len(data):
            while len(self.pending_packets) >= self.remote_slot_capacity:
                self._wait_for_pending(timeout)
            chunk = data[offset : offset + payload_capacity]
            packet_bytes = PACKET_DATA_HEADER_SIZE + len(chunk) + CRC_SIZE
            body = struct.pack(
                "<BBBBH",
                PABB2_CONNECTION_MAGIC_NUMBER,
                self.seqnum,
                packet_bytes & 0xFF,
                PABB2_CONNECTION_OPCODE_ASK_STREAM_DATA,
                self.stream_offset & 0xFFFF,
            ) + chunk
            self._send_packet_body(body, seed=self.session_id)
            self.seqnum = (self.seqnum + 1) & 0xFF
            self.stream_offset = (self.stream_offset + len(chunk)) & 0xFFFF
            offset += len(chunk)
            pending += 1

        if pending:
            self._wait_for_pending(timeout)

    def _send_packet_body(self, body: bytes, seed: int) -> None:
        seq = body[1]
        packet = packet_with_crc(seed, body)
        self.pending_packets[seq] = (packet, time.monotonic())
        self.serial.write(packet)

    def _wait_for_pending(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while self.pending_packets:
            self._drain_input(max(0.0, min(0.05, deadline - time.monotonic())))
            if not self.pending_packets:
                return
            if time.monotonic() >= deadline:
                raise PABotBase2Error(f"Timed out waiting for packet ack(s): {sorted(self.pending_packets)}")
            self._maybe_retransmit()

    def _maybe_retransmit(self) -> None:
        now = time.monotonic()
        for seq, (packet_data, sent_time) in list(self.pending_packets.items()):
            if now - sent_time < RETRANSMIT_INTERVAL_S:
                continue
            retransmit_body = bytearray(packet_data[:-CRC_SIZE])
            retransmit_body[3] |= PABB2_CONNECTION_RETRANSMIT_FLAG
            retransmit_packet = packet_with_crc(self.session_id, bytes(retransmit_body))
            self.serial.write(retransmit_packet)
            self.pending_packets[seq] = (retransmit_packet, now)
            break

    def _drain_input(self, timeout: float) -> None:
        end = time.monotonic() + timeout
        while True:
            waiting = getattr(self.serial, "in_waiting", 0)
            if waiting:
                data = self.serial.read(waiting)
            elif time.monotonic() < end:
                data = self.serial.read(1)
            else:
                return
            if not data:
                return
            self._push_packet_bytes(data)

    def _push_packet_bytes(self, data: bytes) -> None:
        self.packet_buffer.extend(data)
        while True:
            while self.packet_buffer and self.packet_buffer[0] != PABB2_CONNECTION_MAGIC_NUMBER:
                del self.packet_buffer[0]
            if len(self.packet_buffer) < PACKET_HEADER_SIZE + CRC_SIZE:
                return
            packet_bytes = self.packet_buffer[2] or 256
            if packet_bytes < PACKET_HEADER_SIZE + CRC_SIZE:
                raise PABotBase2Error(f"Invalid packet length from PABotBase2: {packet_bytes}")
            if len(self.packet_buffer) < packet_bytes:
                return
            packet = bytes(self.packet_buffer[:packet_bytes])
            del self.packet_buffer[:packet_bytes]
            self._process_packet(packet)

    def _process_packet(self, packet: bytes) -> None:
        expected = struct.unpack_from("<I", packet, len(packet) - CRC_SIZE)[0]
        actual = pabb_crc32(self.session_id, packet[:-CRC_SIZE])
        if (
            expected != actual
            and not self._matches_reset_handshake_crc(expected, packet)
        ):
            if self._matches_stale_reset_session_info_crc(expected, packet):
                return
            self.bad_crc_packets += 1
            self._logger.warning(
                "Discarding PABotBase2 packet with CRC mismatch: "
                "seq=%d opcode=0x%02x bytes=%d expected=0x%08x actual=0x%08x",
                packet[1],
                packet[3] if len(packet) > 3 else 0,
                len(packet),
                expected,
                actual,
            )
            return

        _, seq, _, raw_opcode = struct.unpack_from("<BBBB", packet)
        opcode = raw_opcode & PABB2_CONNECTION_OPCODE_MASK
        if opcode in (
            PABB2_CONNECTION_OPCODE_RET_RESET,
            PABB2_CONNECTION_OPCODE_RET_STREAM_DATA,
        ):
            self.pending_packets.pop(seq, None)
            return
        if opcode == PABB2_CONNECTION_OPCODE_RET_VERSION:
            self._remote_connection_protocol = struct.unpack_from("<I", packet, PACKET_HEADER_SIZE)[0]
            self.pending_packets.pop(seq, None)
            return
        if opcode == PABB2_CONNECTION_OPCODE_RET_PACKET_SIZE:
            self.max_packet_size = struct.unpack_from("<H", packet, PACKET_HEADER_SIZE)[0]
            if self.max_packet_size == 0:
                self.max_packet_size = 256
            self.pending_packets.pop(seq, None)
            return
        if opcode == PABB2_CONNECTION_OPCODE_RET_BUFFER_SLOTS:
            self.remote_slot_capacity = max(1, packet[PACKET_HEADER_SIZE])
            self.pending_packets.pop(seq, None)
            return
        if opcode == PABB2_CONNECTION_OPCODE_ASK_STREAM_DATA:
            self._process_incoming_stream_packet(seq, packet)
            return
        if opcode == PABB2_CONNECTION_OPCODE_INFO_STREAM_DEAD:
            raise PABotBase2Error(f"PABotBase2 device reported stream error opcode: 0x{opcode:02x}")
        if opcode in (PABB2_CONNECTION_OPCODE_INFO_STREAM_NOT_READY, PABB2_CONNECTION_OPCODE_INFO_STREAM_SEND_FULL):
            self._logger.debug("Ignoring PABotBase2 stream info opcode: 0x%02x", opcode)
            return
        if opcode == PABB2_CONNECTION_OPCODE_INFO_STREAM_RECV_FULL:
            self._logger.debug("Ignoring PABotBase2 stream receive-full info opcode: 0x%02x", opcode)
            return
        if opcode == PABB2_CONNECTION_OPCODE_UNKNOWN_OPCODE:
            raise PABotBase2Error(f"PABotBase2 device reported unknown opcode: {packet[PACKET_HEADER_SIZE]}")

    def _matches_reset_handshake_crc(self, expected: int, packet: bytes) -> bool:
        if packet[3] & PABB2_CONNECTION_OPCODE_MASK != PABB2_CONNECTION_OPCODE_RET_RESET:
            return False
        pending = self.pending_packets.get(packet[1])
        if pending is None:
            return False
        packet_data, _ = pending
        if packet_data[3] & PABB2_CONNECTION_OPCODE_MASK != PABB2_CONNECTION_OPCODE_ASK_RESET:
            return False
        return expected == pabb_crc32(PABB2_CONNECTION_RESET_SESSION_ID, packet[:-CRC_SIZE])

    def _matches_stale_reset_session_info_crc(self, expected: int, packet: bytes) -> bool:
        opcode = packet[3] & PABB2_CONNECTION_OPCODE_MASK
        if opcode not in (
            PABB2_CONNECTION_OPCODE_INFO_STREAM_NOT_READY,
            PABB2_CONNECTION_OPCODE_INFO_STREAM_SEND_FULL,
            PABB2_CONNECTION_OPCODE_INFO_STREAM_RECV_FULL,
        ):
            return False
        return expected == pabb_crc32(PABB2_CONNECTION_RESET_SESSION_ID, packet[:-CRC_SIZE])

    def _process_incoming_stream_packet(self, seq: int, packet: bytes) -> None:
        stream_offset = struct.unpack_from("<H", packet, PACKET_HEADER_SIZE)[0]
        payload = packet[PACKET_DATA_HEADER_SIZE:-CRC_SIZE]

        if not self._recv_coalescer.push_stream(seq, stream_offset, payload):
            return

        self._send_oob_u16(
            seq,
            PABB2_CONNECTION_OPCODE_RET_STREAM_DATA,
            self._recv_coalescer.free_bytes(),
        )

        data = self._recv_coalescer.read()
        if data:
            self.stream_buffer.extend(data)
            self._parse_messages()

    def _send_oob_u16(self, seq: int, opcode: int, data: int) -> None:
        body = struct.pack("<BBBBH", PABB2_CONNECTION_MAGIC_NUMBER, seq, 10, opcode, data & 0xFFFF)
        self.serial.write(packet_with_crc(self.session_id, body))

    def _parse_messages(self) -> None:
        while len(self.stream_buffer) >= MESSAGE_HEADER_SIZE:
            message_size = struct.unpack_from("<H", self.stream_buffer)[0]
            if message_size < MESSAGE_HEADER_SIZE:
                raise PABotBase2Error(f"Corrupt PABotBase2 message size: {message_size}")
            if len(self.stream_buffer) < message_size:
                return
            message = bytes(self.stream_buffer[:message_size])
            del self.stream_buffer[:message_size]
            _, opcode, request_id = struct.unpack_from("<HBB", message)
            if opcode in (
                PABB2_MESSAGE_OPCODE_RET,
                PABB2_MESSAGE_OPCODE_RET_U32,
                PABB2_MESSAGE_OPCODE_RET_DATA,
                PABB2_MESSAGE_OPCODE_RET_U32_DATA,
            ):
                self.responses[request_id] = message
            elif opcode == PABB2_MESSAGE_OPCODE_CQ_COMMAND_FINISHED:
                continue

    def _connect_device(self) -> None:
        self.device_protocol = self._query_u32(PABB2_MESSAGE_OPCODE_PROTOCOL_VERSION)
        if self.device_protocol != PABB2_MESSAGE_PROTOCOL_VERSION:
            raise PABotBase2Error(f"Incompatible PABotBase2 message protocol: {self.device_protocol}")
        self.device_firmware_version = self._query_u32(PABB2_MESSAGE_OPCODE_FIRMWARE_VERSION)
        if self.device_firmware_version < PABB2_MIN_FIRMWARE_VERSION:
            raise PABotBase2Error(f"Incompatible PABotBase2 firmware version: {self.device_firmware_version}")
        self._set_logging_flag(PABB2_DEVICE_LOGGING_FLAG)
        self.device_id = self._query_u32(PABB2_MESSAGE_OPCODE_DEVICE_IDENTIFIER)
        self.device_name = self._query_data(PABB2_MESSAGE_OPCODE_DEVICE_NAME).decode("utf-8", errors="replace")
        self.supported_controller_modes = self._parse_controller_list(
            self._query_data(PABB2_MESSAGE_OPCODE_CONTROLLER_LIST)
        )
        self.command_queue_capacity = max(1, min(255, self._query_u32(PABB2_MESSAGE_OPCODE_CQ_CAPACITY)))

    @staticmethod
    def _parse_controller_list(raw: bytes) -> set[ControllerMode]:
        if len(raw) % 4 != 0:
            raise PABotBase2Error(f"Invalid PABotBase2 controller list length: {len(raw)}")

        modes: set[ControllerMode] = set()
        for offset in range(0, len(raw), 4):
            mode_id = struct.unpack_from("<I", raw, offset)[0]
            try:
                modes.add(ControllerMode(mode_id))
            except ValueError:
                continue
        return modes

    def _query_u32(self, opcode: int) -> int:
        response = self._send_message_with_response(struct.pack("<HBB", MESSAGE_HEADER_SIZE, opcode, 0))
        response_size, response_opcode, _ = struct.unpack_from("<HBB", response)
        if response_opcode != PABB2_MESSAGE_OPCODE_RET_U32 or response_size != 8:
            raise PABotBase2Error(f"Expected u32 response for opcode 0x{opcode:02x}.")
        return struct.unpack_from("<I", response, MESSAGE_HEADER_SIZE)[0]

    def _query_data(self, opcode: int) -> bytes:
        response = self._send_message_with_response(struct.pack("<HBB", MESSAGE_HEADER_SIZE, opcode, 0))
        response_size, response_opcode, _ = struct.unpack_from("<HBB", response)
        if response_opcode != PABB2_MESSAGE_OPCODE_RET_DATA or response_size < MESSAGE_HEADER_SIZE:
            raise PABotBase2Error(f"Expected data response for opcode 0x{opcode:02x}.")
        return response[MESSAGE_HEADER_SIZE:response_size]

    def _set_logging_flag(self, flag: int) -> None:
        message = struct.pack("<HBBI", 8, PABB2_MESSAGE_OPCODE_SET_LOGGING_FLAG, 0, flag & 0xFFFFFFFF)
        self._send_message_no_response(message)

    def _set_controller_mode(self, mode: ControllerMode) -> None:
        self._validate_supported_controller_mode(mode)
        current = self._query_u32(PABB2_MESSAGE_OPCODE_READ_CONTROLLER_MODE)
        if current == int(mode):
            return
        self._send_controller_mode_request(PABB2_MESSAGE_OPCODE_CHANGE_CONTROLLER_MODE, mode, timeout=2.0)

    def reset_to_controller(self, mode: ControllerMode | int | None = None) -> None:
        if not self.connected:
            raise PABotBase2Error("PABotBase2 connection is not open.")
        mode = self.controller_mode if mode is None else ControllerMode(mode)
        self._validate_supported_controller_mode(mode)
        self._send_controller_mode_request(PABB2_MESSAGE_OPCODE_RESET_TO_CONTROLLER, mode, timeout=2.0)
        self.controller_mode = mode

    def _validate_supported_controller_mode(self, mode: ControllerMode) -> None:
        if self.supported_controller_modes and mode not in self.supported_controller_modes:
            supported = ", ".join(
                controller_mode_name(supported_mode)
                for supported_mode in PABOTBASE2_CONTROLLER_MODE_BY_NAME.values()
                if supported_mode in self.supported_controller_modes
            )
            if not supported:
                supported = ", ".join(f"0x{int(mode):04x}" for mode in sorted(self.supported_controller_modes))
            raise PABotBase2Error(
                "PABotBase2 firmware does not support selected controller mode: "
                f"{controller_mode_name(mode)}. Supported: {supported}"
            )

    def _send_controller_mode_request(self, opcode: int, mode: ControllerMode, timeout: float) -> None:
        message = struct.pack("<HBBI", 8, opcode, 0, int(mode))
        self._send_message_with_response(message, timeout=timeout)

    def _send_message_with_response(self, message: bytes, timeout: float = 2.0) -> bytes:
        message = bytearray(message)
        message[3] = self.request_id
        request_id = self.request_id
        self.request_id = (self.request_id + 1) & 0xFF
        self._send_stream(bytes(message), timeout=timeout)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._drain_input(max(0.0, min(0.05, deadline - time.monotonic())))
            if request_id in self.responses:
                return self.responses.pop(request_id)
            self._maybe_retransmit()
        raise PABotBase2Error(f"Timed out waiting for PABotBase2 message response id {request_id}.")

    def _send_message_no_response(self, message: bytes, timeout: float = 1.0) -> None:
        self._send_stream(message, timeout=timeout)

    def _send_command_message(self, message: bytes) -> None:
        message = bytearray(message)
        message[3] = self.command_id
        self.command_id = (self.command_id + 1) & 0xFF
        self._send_stream(bytes(message), timeout=1.0)

    def _build_controller_state(self, send_format: Any, milliseconds: int) -> bytes:
        if self.controller_mode in PABOTBASE2_WIRED_CONTROLLER_MODES:
            return self._build_wired_controller_state(send_format, milliseconds)
        if self.controller_mode in PABOTBASE2_OEM_CONTROLLER_MODES:
            return self._build_oem_controller_buttons(send_format, milliseconds)
        raise PABotBase2Error(f"Unsupported PABotBase2 controller mode: {controller_mode_name(self.controller_mode)}")

    def _build_wired_controller_state(self, send_format: Any, milliseconds: int) -> bytes:
        fmt = send_format.format
        buttons = int(fmt["btn"])
        hat = int(fmt["hat"])
        lx = int(fmt["lx"])
        ly = int(fmt["ly"])
        rx = int(fmt["rx"])
        ry = int(fmt["ry"])
        self._validate_wired_controller_state(buttons, hat)
        dpad_byte = hat & 0x0F
        if self.controller_mode == ControllerMode.NINTENDO_SWITCH2_WIRED_CONTROLLER and buttons & (1 << 24):
            dpad_byte |= 0x80
        report = bytes(
            [
                buttons & 0xFF,
                (buttons >> 8) & 0xFF,
                dpad_byte,
                self._clamp_u8(lx),
                self._clamp_u8(ly),
                self._clamp_u8(rx),
                self._clamp_u8(ry),
            ]
        )
        return struct.pack(
            "<HBBH",
            MESSAGE_HEADER_SIZE + 2 + len(report),
            PABB2_MESSAGE_CMD_NS_WIRED_CONTROLLER_STATE,
            0,
            milliseconds & 0xFFFF,
        ) + report

    def _build_oem_controller_buttons(self, send_format: Any, milliseconds: int) -> bytes:
        fmt = send_format.format
        buttons = int(fmt["btn"])
        hat = int(fmt["hat"])
        lx = int(fmt["lx"])
        ly = int(fmt["ly"])
        rx = int(fmt["rx"])
        ry = int(fmt["ry"])
        self._validate_controller_state(buttons, hat, lx, ly, rx, ry)
        button3, button4, button5 = self._encode_buttons(buttons, hat)
        left = self._pack_oem_stick(lx, ly)
        right = self._pack_oem_stick(rx, ry)
        buttons = bytes([button3, button4, button5]) + left + right + bytes([0])
        return struct.pack(
            "<HBBH",
            MESSAGE_HEADER_SIZE + 2 + len(buttons),
            PABB2_MESSAGE_CMD_NS1_OEM_CONTROLLER_BUTTONS,
            0,
            milliseconds & 0xFFFF,
        ) + buttons

    def _validate_controller_state(self, buttons: int, hat: int, lx: int, ly: int, rx: int, ry: int) -> None:
        if self.controller_mode in PABOTBASE2_LEFT_JOYCON_MODES:
            self._raise_on_unsupported_buttons(
                buttons,
                unsupported_bits={
                    0: "Y",
                    1: "B",
                    2: "A",
                    3: "X",
                    5: "R",
                    7: "ZR",
                    9: "PLUS",
                    11: "RCLICK",
                    12: "HOME",
                    22: "RIGHT_SL",
                    23: "RIGHT_SR",
                },
            )
            if (rx, ry) != (128, 128):
                raise PABotBase2Error("Right stick input is unsupported in Left Joy-Con mode.")
            return

        if self.controller_mode in PABOTBASE2_RIGHT_JOYCON_MODES:
            self._raise_on_unsupported_buttons(
                buttons,
                unsupported_bits={
                    4: "L",
                    6: "ZL",
                    8: "MINUS",
                    10: "LCLICK",
                    13: "CAPTURE",
                    20: "LEFT_SL",
                    21: "LEFT_SR",
                },
            )
            if hat != 8:
                raise PABotBase2Error("D-pad/Hat input is unsupported in Right Joy-Con mode.")
            if (lx, ly) != (128, 128):
                raise PABotBase2Error("Left stick input is unsupported in Right Joy-Con mode.")

    def _validate_wired_controller_state(self, buttons: int, hat: int) -> None:
        self._raise_on_unsupported_buttons(
            buttons,
            unsupported_bits={
                20: "LEFT_SL",
                21: "LEFT_SR",
                22: "RIGHT_SL",
                23: "RIGHT_SR",
            },
        )
        supported_mask = 0x3FFF
        if self.controller_mode == ControllerMode.NINTENDO_SWITCH2_WIRED_CONTROLLER:
            supported_mask = 0x0100FFFF
        unsupported_mask = buttons & ~supported_mask
        if unsupported_mask:
            raise PABotBase2Error(
                f"Unsupported button bits for Wired Controller mode: 0x{unsupported_mask:x}"
            )
        if hat < 0 or hat > 8:
            raise PABotBase2Error(f"Unsupported D-pad/Hat value for Wired Controller mode: {hat}")

    @staticmethod
    def _raise_on_unsupported_buttons(buttons: int, unsupported_bits: dict[int, str]) -> None:
        pressed = [name for bit, name in unsupported_bits.items() if buttons & (1 << bit)]
        if pressed:
            raise PABotBase2Error(f"Unsupported button(s) for selected PABotBase2 controller mode: {', '.join(pressed)}")

    @staticmethod
    def _encode_buttons(buttons: int, hat: int) -> tuple[int, int, int]:
        button3 = 0
        button4 = 0
        button5 = 0
        if buttons & (1 << 0):  # Y
            button3 |= 1 << 0
        if buttons & (1 << 3):  # X
            button3 |= 1 << 1
        if buttons & (1 << 1):  # B
            button3 |= 1 << 2
        if buttons & (1 << 2):  # A
            button3 |= 1 << 3
        if buttons & (1 << 23):  # RIGHT_SR
            button3 |= 1 << 4
        if buttons & (1 << 22):  # RIGHT_SL
            button3 |= 1 << 5
        if buttons & (1 << 5):  # R
            button3 |= 1 << 6
        if buttons & (1 << 7):  # ZR
            button3 |= 1 << 7
        if buttons & (1 << 8):  # MINUS
            button4 |= 1 << 0
        if buttons & (1 << 9):  # PLUS
            button4 |= 1 << 1
        if buttons & (1 << 11):  # RCLICK
            button4 |= 1 << 2
        if buttons & (1 << 10):  # LCLICK
            button4 |= 1 << 3
        if buttons & (1 << 12):  # HOME
            button4 |= 1 << 4
        if buttons & (1 << 13):  # CAPTURE
            button4 |= 1 << 5
        if buttons & (1 << 21):  # LEFT_SR
            button5 |= 1 << 4
        if buttons & (1 << 20):  # LEFT_SL
            button5 |= 1 << 5
        if buttons & (1 << 4):  # L
            button5 |= 1 << 6
        if buttons & (1 << 6):  # ZL
            button5 |= 1 << 7

        dpad_bits = {
            0: (False, True, False, False),   # up
            1: (False, True, True, False),    # up-right
            2: (False, False, True, False),   # right
            3: (True, False, True, False),    # down-right
            4: (True, False, False, False),   # down
            5: (True, False, False, True),    # down-left
            6: (False, False, False, True),   # left
            7: (False, True, False, True),    # up-left
        }
        down, up, right, left = dpad_bits.get(hat, (False, False, False, False))
        button5 |= (1 if down else 0) << 0
        button5 |= (1 if up else 0) << 1
        button5 |= (1 if right else 0) << 2
        button5 |= (1 if left else 0) << 3
        return button3, button4, button5

    @staticmethod
    def _pack_oem_stick(x: int, y: int) -> bytes:
        x = PABotBase2Connection._clamp_u8(x)
        y = PABotBase2Connection._clamp_u8(y)
        wx = round(x * 4095 / 255)
        wy = round((255 - y) * 4095 / 255)
        return bytes([
            wx & 0xFF,
            ((wx >> 8) | ((wy & 0x0F) << 4)) & 0xFF,
            (wy >> 4) & 0xFF,
        ])

    @staticmethod
    def _clamp_u8(value: int) -> int:
        return max(0, min(255, value))


class NullPABotBase2Connection:
    def connect(self, timeout: float = 5.0) -> None:
        raise PABotBase2Error("PABotBase2 connection is not open.")
