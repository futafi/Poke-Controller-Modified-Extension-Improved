#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import random
import struct
import time
from collections import deque
from enum import IntEnum
from logging import DEBUG, NullHandler, getLogger
from typing import Any


class PABotBase2Error(RuntimeError):
    pass


class ControllerMode(IntEnum):
    NONE = 0x0000
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
)

PABOTBASE2_CONTROLLER_MODE_BY_NAME = {
    "Wireless Pro Controller": ControllerMode.NINTENDO_SWITCH_WIRELESS_PRO_CONTROLLER,
    "Wireless Left Joy-Con": ControllerMode.NINTENDO_SWITCH_WIRELESS_LEFT_JOYCON,
    "Wireless Right Joy-Con": ControllerMode.NINTENDO_SWITCH_WIRELESS_RIGHT_JOYCON,
}

PABOTBASE2_CONTROLLER_MODE_NAME_BY_MODE = {
    mode: name for name, mode in PABOTBASE2_CONTROLLER_MODE_BY_NAME.items()
}


def controller_mode_from_name(mode_name: str) -> ControllerMode:
    try:
        return PABOTBASE2_CONTROLLER_MODE_BY_NAME[mode_name]
    except KeyError as e:
        raise PABotBase2Error(f"Unsupported PABotBase2 controller mode: {mode_name}") from e


PABB2_CONNECTION_MAGIC_NUMBER = 0x81
PABB2_CONNECTION_PROTOCOL_VERSION = 2026041102

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
PABB2_MESSAGE_OPCODE_PROTOCOL_VERSION = 0x20
PABB2_MESSAGE_OPCODE_FIRMWARE_VERSION = 0x21
PABB2_MESSAGE_OPCODE_DEVICE_IDENTIFIER = 0x22
PABB2_MESSAGE_OPCODE_DEVICE_NAME = 0x23
PABB2_MESSAGE_OPCODE_CONTROLLER_LIST = 0x24
PABB2_MESSAGE_OPCODE_CQ_CAPACITY = 0x28
PABB2_MESSAGE_OPCODE_READ_CONTROLLER_MODE = 0x30
PABB2_MESSAGE_OPCODE_CHANGE_CONTROLLER_MODE = 0x31
PABB2_MESSAGE_OPCODE_REQUEST_STATUS = 0x35
PABB2_MESSAGE_OPCODE_CQ_CANCEL = 0x41
PABB2_MESSAGE_OPCODE_CQ_COMMAND_FINISHED = 0x43

PABB2_MESSAGE_CMD_NS1_OEM_CONTROLLER_BUTTONS = 0x97

MESSAGE_HEADER_SIZE = 4
PACKET_HEADER_SIZE = 4
PACKET_DATA_HEADER_SIZE = 6
CRC_SIZE = 4
DEFAULT_PACKET_SIZE = 24
DEFAULT_REMOTE_SLOTS = 1
PABB2_PacketSender_RETRANSMIT_COUNTER = 2
PABOTBASE2_STATE_HOLD_MS = 65535


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


class PABotBase2Connection:
    def __init__(self, serial_port: Any, controller_mode: ControllerMode | int = ControllerMode.NINTENDO_SWITCH_WIRELESS_PRO_CONTROLLER):
        self.serial = serial_port
        self.controller_mode = ControllerMode(controller_mode)
        self.session_id = 0
        self.max_packet_size = DEFAULT_PACKET_SIZE
        self.remote_slot_capacity = DEFAULT_REMOTE_SLOTS
        self.seqnum = 0
        self.pending_packets: dict[int, bytes] = {}
        self.retransmit_counter = 0
        self.stream_offset = 0
        self.recv_stream_offset = 0
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
        self.bad_crc_packets = 0

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

    def connect(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        for baudrate in (921600, 115200):
            if time.monotonic() >= deadline:
                break
            try:
                self.serial.baudrate = baudrate
                self._reset_input_buffer()
                self._reset(random_session_id=True, timeout=0.5)
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
                return
            except Exception as e:
                last_error = e
                self._reset_runtime_state()

        if last_error is not None:
            raise PABotBase2Error(f"Unable to connect to PABotBase2 device: {last_error}") from last_error
        raise PABotBase2Error("Unable to connect to PABotBase2 device.")

    @property
    def remote_connection_protocol(self) -> int:
        return getattr(self, "_remote_connection_protocol", 0)

    @property
    def remote_connection_protocol_major(self) -> int:
        return self.remote_connection_protocol // 100

    def close(self) -> None:
        self.connected = False

    def send_controller_state(self, send_format: Any) -> None:
        if not self.connected:
            raise PABotBase2Error("PABotBase2 connection is not open.")
        self._drain_input(0)
        self._send_message_no_response(bytes([MESSAGE_HEADER_SIZE, 0, PABB2_MESSAGE_OPCODE_CQ_CANCEL, 0]))
        message = self._build_oem_controller_buttons(send_format, PABOTBASE2_STATE_HOLD_MS)
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
        self.retransmit_counter = 0
        self.stream_offset = 0
        self.recv_stream_offset = 0
        self.packet_buffer.clear()
        self.stream_buffer.clear()
        self.responses.clear()
        self.connected = False

    def _reset_input_buffer(self) -> None:
        if hasattr(self.serial, "reset_input_buffer"):
            self.serial.reset_input_buffer()

    def _reset(self, random_session_id: bool, timeout: float) -> None:
        self._reset_runtime_state()
        if random_session_id:
            self.session_id = random.getrandbits(32)
            if self.session_id == 0xFFFFFFFF:
                self.session_id = 0xFFFFFFFE
            body = struct.pack(
                "<BBBBI",
                PABB2_CONNECTION_MAGIC_NUMBER,
                self.seqnum,
                PACKET_HEADER_SIZE + 4 + CRC_SIZE,
                PABB2_CONNECTION_OPCODE_ASK_RESET,
                self.session_id,
            )
            self._send_packet_body(body, seed=0xFFFFFFFF)
        else:
            self.session_id = 0xFFFFFFFF
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
        self.pending_packets[seq] = packet
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
        self.retransmit_counter = (self.retransmit_counter + 1) & 0xFF
        if self.retransmit_counter % PABB2_PacketSender_RETRANSMIT_COUNTER:
            return
        for seq, packet in list(self.pending_packets.items())[:1]:
            packet = bytearray(packet)
            packet[3] |= PABB2_CONNECTION_RETRANSMIT_FLAG
            body = bytes(packet[:-CRC_SIZE])
            packet = bytearray(packet_with_crc(self.session_id, body))
            self.serial.write(packet)
            self.pending_packets[seq] = bytes(packet)

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
        if expected != actual:
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
        if opcode in (
            PABB2_CONNECTION_OPCODE_INFO_STREAM_DEAD,
            PABB2_CONNECTION_OPCODE_INFO_STREAM_NOT_READY,
            PABB2_CONNECTION_OPCODE_INFO_STREAM_SEND_FULL,
            PABB2_CONNECTION_OPCODE_INFO_STREAM_RECV_FULL,
        ):
            raise PABotBase2Error(f"PABotBase2 device reported stream error opcode: 0x{opcode:02x}")
        if opcode == PABB2_CONNECTION_OPCODE_UNKNOWN_OPCODE:
            raise PABotBase2Error(f"PABotBase2 device reported unknown opcode: {packet[PACKET_HEADER_SIZE]}")

    def _process_incoming_stream_packet(self, seq: int, packet: bytes) -> None:
        stream_offset = struct.unpack_from("<H", packet, PACKET_HEADER_SIZE)[0]
        payload = packet[PACKET_DATA_HEADER_SIZE:-CRC_SIZE]
        if stream_offset == self.recv_stream_offset:
            self.recv_stream_offset = (self.recv_stream_offset + len(payload)) & 0xFFFF
            self.stream_buffer.extend(payload)
            self._parse_messages()
        elif (stream_offset - self.recv_stream_offset) & 0xFFFF < 0x8000:
            raise PABotBase2Error(
                f"Out-of-order PABotBase2 stream packet: got {stream_offset}, expected {self.recv_stream_offset}"
            )
        self._send_oob_u16(seq, PABB2_CONNECTION_OPCODE_RET_STREAM_DATA, 4096)

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
            if opcode in (PABB2_MESSAGE_OPCODE_RET, PABB2_MESSAGE_OPCODE_RET_U32, PABB2_MESSAGE_OPCODE_RET_DATA):
                self.responses[request_id] = message
            elif opcode == PABB2_MESSAGE_OPCODE_CQ_COMMAND_FINISHED:
                continue

    def _connect_device(self) -> None:
        self.device_protocol = self._query_u32(PABB2_MESSAGE_OPCODE_PROTOCOL_VERSION)
        if self.device_protocol < 2026041103:
            raise PABotBase2Error(f"Incompatible PABotBase2 message protocol: {self.device_protocol}")
        self.device_firmware_version = self._query_u32(PABB2_MESSAGE_OPCODE_FIRMWARE_VERSION)
        self.device_id = self._query_u32(PABB2_MESSAGE_OPCODE_DEVICE_IDENTIFIER)
        self.device_name = self._query_data(PABB2_MESSAGE_OPCODE_DEVICE_NAME).decode("utf-8", errors="replace")
        self._query_data(PABB2_MESSAGE_OPCODE_CONTROLLER_LIST)
        self.command_queue_capacity = max(1, min(255, self._query_u32(PABB2_MESSAGE_OPCODE_CQ_CAPACITY)))

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

    def _set_controller_mode(self, mode: ControllerMode) -> None:
        current = self._query_u32(PABB2_MESSAGE_OPCODE_READ_CONTROLLER_MODE)
        if current == int(mode):
            return
        message = struct.pack("<HBBI", 8, PABB2_MESSAGE_OPCODE_CHANGE_CONTROLLER_MODE, 0, int(mode))
        self._send_message_with_response(message, timeout=2.0)

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
        if self.controller_mode == ControllerMode.NINTENDO_SWITCH_WIRELESS_LEFT_JOYCON:
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
                },
            )
            if (rx, ry) != (128, 128):
                raise PABotBase2Error("Right stick input is unsupported in Wireless Left Joy-Con mode.")
            return

        if self.controller_mode == ControllerMode.NINTENDO_SWITCH_WIRELESS_RIGHT_JOYCON:
            self._raise_on_unsupported_buttons(
                buttons,
                unsupported_bits={
                    4: "L",
                    6: "ZL",
                    8: "MINUS",
                    10: "LCLICK",
                    13: "CAPTURE",
                },
            )
            if hat != 8:
                raise PABotBase2Error("D-pad/Hat input is unsupported in Wireless Right Joy-Con mode.")
            if (lx, ly) != (128, 128):
                raise PABotBase2Error("Left stick input is unsupported in Wireless Right Joy-Con mode.")

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
        x = max(0, min(255, x))
        y = max(0, min(255, y))
        wx = round(x * 4095 / 255)
        wy = round((255 - y) * 4095 / 255)
        return bytes([
            wx & 0xFF,
            ((wx >> 8) | ((wy & 0x0F) << 4)) & 0xFF,
            (wy >> 4) & 0xFF,
        ])


class NullPABotBase2Connection:
    def connect(self, timeout: float = 5.0) -> None:
        raise PABotBase2Error("PABotBase2 connection is not open.")
