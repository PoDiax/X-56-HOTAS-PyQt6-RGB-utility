from __future__ import annotations

VENDOR_ID = 0x0738
SUPPORTED_PRODUCTS: dict[int, str] = {
    0x2221: "X-56 Joystick",
    0xA221: "X-56 Throttle",
}

USB_TIMEOUT_MS = 4000
REQUEST_TYPE_SET_REPORT = 0x21
REQUEST_SET_REPORT = 0x09

WVALUE_RGB = 0x0309
WVALUE_APPLY = 0x0300
WINDEX_INTERFACE_2 = 2 << 8

PACKET_SIZE = 64


def build_rgb_packet(red: int, green: int, blue: int) -> bytearray:
    packet = bytearray(PACKET_SIZE)
    packet[0] = 0x09
    packet[1] = 0x00
    packet[2] = 0x03
    packet[3] = red
    packet[4] = green
    packet[5] = blue
    return packet


def build_apply_packet() -> bytearray:
    packet = bytearray(PACKET_SIZE)
    packet[0] = 0x01
    packet[1] = 0x01
    return packet
