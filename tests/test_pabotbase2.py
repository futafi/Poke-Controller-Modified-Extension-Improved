import os
import struct
import sys
import types
import unittest


ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "SerialController"))
sys.modules.setdefault(
    "serial",
    types.SimpleNamespace(
        Serial=lambda *args, **kwargs: None,
        serialutil=types.SimpleNamespace(SerialException=Exception),
    ),
)

from Commands.PABotBase2 import (  # noqa: E402
    CRC_SIZE,
    MESSAGE_HEADER_SIZE,
    PACKET_DATA_HEADER_SIZE,
    PACKET_HEADER_SIZE,
    ControllerMode,
    PABotBase2Error,
    PABotBase2Connection,
    PABOTBASE2_CONTROLLER_MODE_BY_NAME,
    PABB2_CONNECTION_MAGIC_NUMBER,
    PABB2_CONNECTION_OPCODE_ASK_RESET,
    PABB2_CONNECTION_OPCODE_ASK_STREAM_DATA,
    PABB2_CONNECTION_OPCODE_ASK_VERSION,
    PABB2_CONNECTION_OPCODE_RET_BUFFER_SLOTS,
    PABB2_CONNECTION_OPCODE_RET_PACKET_SIZE,
    PABB2_CONNECTION_OPCODE_RET_RESET,
    PABB2_CONNECTION_OPCODE_RET_STREAM_DATA,
    PABB2_CONNECTION_OPCODE_RET_VERSION,
    PABB2_MESSAGE_CMD_NS1_OEM_CONTROLLER_BUTTONS,
    PABB2_MESSAGE_OPCODE_CHANGE_CONTROLLER_MODE,
    PABB2_MESSAGE_OPCODE_CONTROLLER_LIST,
    PABB2_MESSAGE_OPCODE_CQ_CANCEL,
    PABB2_MESSAGE_OPCODE_CQ_CAPACITY,
    PABB2_MESSAGE_OPCODE_DEVICE_IDENTIFIER,
    PABB2_MESSAGE_OPCODE_DEVICE_NAME,
    PABB2_MESSAGE_OPCODE_FIRMWARE_VERSION,
    PABB2_MESSAGE_OPCODE_PROTOCOL_VERSION,
    PABB2_MESSAGE_OPCODE_READ_CONTROLLER_MODE,
    PABB2_MESSAGE_OPCODE_RET,
    PABB2_MESSAGE_OPCODE_RET_DATA,
    PABB2_MESSAGE_OPCODE_RET_U32,
    pabb_crc32,
    packet_with_crc,
)
from Commands.Sender import Sender  # noqa: E402


class FakeSerial:
    def __init__(self):
        self.baudrate = 0
        self.incoming = bytearray()
        self.written = []
        self.session_id = 0
        self.stream = bytearray()
        self.host_stream_offset = 0
        self.device_seq = 0
        self.device_stream_offset = 0
        self.controller_mode = 0

    @property
    def in_waiting(self):
        return len(self.incoming)

    def reset_input_buffer(self):
        self.incoming.clear()

    def read(self, size=1):
        data = bytes(self.incoming[:size])
        del self.incoming[:size]
        return data

    def write(self, data):
        self.written.append(bytes(data))
        if len(data) >= PACKET_HEADER_SIZE + CRC_SIZE and data[0] == PABB2_CONNECTION_MAGIC_NUMBER:
            self._recv_packet(bytes(data))
        return len(data)

    def _recv_packet(self, packet):
        opcode = packet[3] & 0x7F
        seq = packet[1]
        if opcode == PABB2_CONNECTION_OPCODE_ASK_RESET:
            self.session_id = struct.unpack_from("<I", packet, PACKET_HEADER_SIZE)[0]
            self._send_packet(seq, PABB2_CONNECTION_OPCODE_RET_RESET)
        elif opcode == PABB2_CONNECTION_OPCODE_ASK_VERSION:
            self._send_packet(seq, PABB2_CONNECTION_OPCODE_RET_VERSION, struct.pack("<I", 2026041102))
        elif opcode == 0x03:
            self._send_packet(seq, PABB2_CONNECTION_OPCODE_RET_PACKET_SIZE, struct.pack("<H", 64))
        elif opcode == 0x04:
            self._send_packet(seq, PABB2_CONNECTION_OPCODE_RET_BUFFER_SLOTS, bytes([8]))
        elif opcode == PABB2_CONNECTION_OPCODE_ASK_STREAM_DATA:
            offset = struct.unpack_from("<H", packet, PACKET_HEADER_SIZE)[0]
            payload = packet[PACKET_DATA_HEADER_SIZE:-CRC_SIZE]
            if offset == self.host_stream_offset:
                self.host_stream_offset = (self.host_stream_offset + len(payload)) & 0xFFFF
                self.stream.extend(payload)
                self._parse_stream()
            self._send_packet(seq, PABB2_CONNECTION_OPCODE_RET_STREAM_DATA, struct.pack("<H", 4096))

    def _send_packet(self, seq, opcode, payload=b""):
        body = struct.pack(
            "<BBBB",
            PABB2_CONNECTION_MAGIC_NUMBER,
            seq,
            PACKET_HEADER_SIZE + len(payload) + CRC_SIZE,
            opcode,
        ) + payload
        self.incoming.extend(packet_with_crc(self.session_id, body))

    def _send_stream_message(self, message):
        body = struct.pack(
            "<BBBBH",
            PABB2_CONNECTION_MAGIC_NUMBER,
            self.device_seq,
            PACKET_DATA_HEADER_SIZE + len(message) + CRC_SIZE,
            PABB2_CONNECTION_OPCODE_ASK_STREAM_DATA,
            self.device_stream_offset,
        ) + message
        self.device_seq = (self.device_seq + 1) & 0xFF
        self.device_stream_offset = (self.device_stream_offset + len(message)) & 0xFFFF
        self.incoming.extend(packet_with_crc(self.session_id, body))

    def _parse_stream(self):
        while len(self.stream) >= MESSAGE_HEADER_SIZE:
            message_size, opcode, request_id = struct.unpack_from("<HBB", self.stream)
            if len(self.stream) < message_size:
                return
            message = bytes(self.stream[:message_size])
            del self.stream[:message_size]
            self._handle_message(opcode, request_id, message)

    def _handle_message(self, opcode, request_id, message):
        if opcode == PABB2_MESSAGE_OPCODE_CQ_CANCEL:
            return
        if opcode == PABB2_MESSAGE_CMD_NS1_OEM_CONTROLLER_BUTTONS:
            return
        if opcode == PABB2_MESSAGE_OPCODE_PROTOCOL_VERSION:
            self._ret_u32(request_id, 2026041105)
        elif opcode == PABB2_MESSAGE_OPCODE_FIRMWARE_VERSION:
            self._ret_u32(request_id, 2026050100)
        elif opcode == PABB2_MESSAGE_OPCODE_DEVICE_IDENTIFIER:
            self._ret_u32(request_id, 0x25)
        elif opcode == PABB2_MESSAGE_OPCODE_DEVICE_NAME:
            self._ret_data(request_id, b"Fake PABotBase2")
        elif opcode == PABB2_MESSAGE_OPCODE_CONTROLLER_LIST:
            self._ret_data(request_id, struct.pack("<I", int(ControllerMode.NINTENDO_SWITCH_WIRELESS_PRO_CONTROLLER)))
        elif opcode == PABB2_MESSAGE_OPCODE_CQ_CAPACITY:
            self._ret_u32(request_id, 8)
        elif opcode == PABB2_MESSAGE_OPCODE_READ_CONTROLLER_MODE:
            self._ret_u32(request_id, self.controller_mode)
        elif opcode == PABB2_MESSAGE_OPCODE_CHANGE_CONTROLLER_MODE:
            self.controller_mode = struct.unpack_from("<I", message, MESSAGE_HEADER_SIZE)[0]
            self._send_stream_message(struct.pack("<HBB", MESSAGE_HEADER_SIZE, PABB2_MESSAGE_OPCODE_RET, request_id))

    def _ret_u32(self, request_id, value):
        self._send_stream_message(struct.pack("<HBBI", 8, PABB2_MESSAGE_OPCODE_RET_U32, request_id, value))

    def _ret_data(self, request_id, data):
        self._send_stream_message(
            struct.pack("<HBB", MESSAGE_HEADER_SIZE + len(data), PABB2_MESSAGE_OPCODE_RET_DATA, request_id) + data
        )


class Format:
    def __init__(self, btn=(1 << 2) | (1 << 7), hat=0, lx=255, ly=128, rx=128, ry=0):
        self.format = {
            "btn": btn,
            "hat": hat,
            "lx": lx,
            "ly": ly,
            "rx": rx,
            "ry": ry,
        }


class PABotBase2Tests(unittest.TestCase):
    def test_crc32c_matches_pokemon_automation_table(self):
        self.assertEqual(pabb_crc32(0, b"\x01"), 0xF26B8303)

    def test_connect_and_send_controller_state(self):
        serial = FakeSerial()
        connection = PABotBase2Connection(serial)

        connection.connect(timeout=1.0)
        connection.send_controller_state(Format())

        self.assertTrue(connection.connected)
        self.assertEqual(connection.device_name, "Fake PABotBase2")
        self.assertEqual(serial.controller_mode, int(ControllerMode.NINTENDO_SWITCH_WIRELESS_PRO_CONTROLLER))
        self.assertTrue(
            any(
                len(packet) >= PACKET_DATA_HEADER_SIZE
                and packet[3] & 0x7F == PABB2_CONNECTION_OPCODE_ASK_STREAM_DATA
                for packet in serial.written
            )
        )

    def test_connect_uses_selected_controller_mode(self):
        for mode_name, mode in PABOTBASE2_CONTROLLER_MODE_BY_NAME.items():
            with self.subTest(mode=mode_name):
                serial = FakeSerial()
                connection = PABotBase2Connection(serial, mode)

                connection.connect(timeout=1.0)

                self.assertEqual(serial.controller_mode, int(mode))

    def test_sender_passes_selected_pabotbase2_controller_mode(self):
        class FalseVar:
            def get(self):
                return False

        sender = Sender(FalseVar())
        sender.set_serial_data_format("PABotBase2")
        sender.set_pabotbase2_controller_mode("Wireless Left Joy-Con")
        sender.ser = FakeSerial()

        sender._post_open_serial()

        self.assertEqual(sender.ser.controller_mode, int(ControllerMode.NINTENDO_SWITCH_WIRELESS_LEFT_JOYCON))

    def test_joycon_modes_fail_fast_on_unsupported_inputs(self):
        left = PABotBase2Connection(
            FakeSerial(),
            ControllerMode.NINTENDO_SWITCH_WIRELESS_LEFT_JOYCON,
        )
        right = PABotBase2Connection(
            FakeSerial(),
            ControllerMode.NINTENDO_SWITCH_WIRELESS_RIGHT_JOYCON,
        )

        left._build_oem_controller_buttons(Format(btn=1 << 4, hat=0, lx=255, ly=128, rx=128, ry=128), 100)
        right._build_oem_controller_buttons(Format(btn=1 << 2, hat=8, lx=128, ly=128, rx=128, ry=0), 100)

        with self.assertRaisesRegex(PABotBase2Error, "Y"):
            left._build_oem_controller_buttons(Format(btn=1 << 0, hat=8, lx=128, ly=128, rx=128, ry=128), 100)
        with self.assertRaisesRegex(PABotBase2Error, "Right stick"):
            left._build_oem_controller_buttons(Format(btn=0, hat=8, lx=128, ly=128, rx=128, ry=0), 100)
        with self.assertRaisesRegex(PABotBase2Error, "D-pad/Hat"):
            right._build_oem_controller_buttons(Format(btn=0, hat=0, lx=128, ly=128, rx=128, ry=128), 100)
        with self.assertRaisesRegex(PABotBase2Error, "Left stick"):
            right._build_oem_controller_buttons(Format(btn=0, hat=8, lx=255, ly=128, rx=128, ry=128), 100)

    def test_sender_converts_legacy_row_to_pabotbase2_state(self):
        class FalseVar:
            def get(self):
                return False

        class FakePABotBase2:
            def __init__(self):
                self.states = []

            def send_controller_state(self, send_format):
                self.states.append(dict(send_format.format))

        sender = Sender(FalseVar())
        sender.set_serial_data_format("PABotBase2")
        sender.pabotbase2 = FakePABotBase2()

        sender.writeRow_wo_perf_counter("0x0017 2 ff 80 80 00")

        self.assertEqual(
            sender.pabotbase2.states[-1],
            {
                "btn": 0x0017 >> 2,
                "hat": 2,
                "lx": 0xFF,
                "ly": 0x80,
                "rx": 0x80,
                "ry": 0x00,
            },
        )


if __name__ == "__main__":
    unittest.main()
