from rnc.constants import CRC_TABLE


def crc16(data: bytes | bytearray, offset: int = 0, size: int | None = None) -> int:
    if size is None:
        size = len(data) - offset
    crc = 0
    for i in range(offset, offset + size):
        crc ^= data[i]
        crc = (crc >> 8) ^ CRC_TABLE[crc & 0xFF]
    return crc
