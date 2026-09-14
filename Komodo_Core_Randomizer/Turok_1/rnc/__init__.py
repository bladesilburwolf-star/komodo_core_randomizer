"""Self-contained RNC ProPack (vendored). Supports Turok LE headers."""
from __future__ import annotations
import struct
from rnc.unpack import unpack as unpack_be
from rnc.pack import pack as pack_be

HEADER_SIZE = 18


def unpack_le(data: bytes, start: int = 0) -> bytes | None:
    """Decompress RNC with little-endian size/CRC fields (Turok 2)."""
    if start + HEADER_SIZE > len(data) or data[start : start + 3] != b"RNC":
        return None
    method = data[start + 3]
    if method not in (1, 2):
        return None
    u_le = struct.unpack_from("<I", data, start + 4)[0]
    p_le = struct.unpack_from("<I", data, start + 8)[0]
    if u_le == 0 or u_le > 8_000_000 or p_le > 8_000_000:
        return None
    if start + HEADER_SIZE + p_le > len(data):
        return None
    ucrc = struct.unpack_from("<H", data, start + 12)[0]
    pcrc = struct.unpack_from("<H", data, start + 14)[0]
    packs = data[start + 16]
    leeway = data[start + 17]
    be = (
        b"RNC"
        + bytes([method])
        + struct.pack(">I", u_le)
        + struct.pack(">I", p_le)
        + struct.pack(">H", ucrc)
        + struct.pack(">H", pcrc)
        + bytes([packs, leeway])
        + data[start + HEADER_SIZE : start + HEADER_SIZE + p_le]
    )
    try:
        return bytes(unpack_be(be, verify_crc=False))
    except Exception:
        return None


def pack(data: bytes, method: int = 2) -> bytes:
    """Pack with standard big-endian RNC header."""
    return bytes(pack_be(data, method=method))


def pack_le(data: bytes, method: int = 2) -> bytes:
    """Pack and emit Turok-style little-endian RNC header."""
    be = bytes(pack_be(data, method=method))
    # BE header: RNC m uuuu pppp ucrc pcrc leeway chunks
    method_b = be[3]
    u = struct.unpack_from(">I", be, 4)[0]
    p = struct.unpack_from(">I", be, 8)[0]
    ucrc = struct.unpack_from(">H", be, 12)[0]
    pcrc = struct.unpack_from(">H", be, 14)[0]
    leeway = be[16]
    chunks = be[17]
    payload = be[HEADER_SIZE:]
    le_hdr = (
        b"RNC"
        + bytes([method_b])
        + struct.pack("<I", u)
        + struct.pack("<I", p)
        + struct.pack("<H", ucrc)
        + struct.pack("<H", pcrc)
        + bytes([leeway, chunks])
    )
    return le_hdr + payload


def unpack(data: bytes) -> bytes:
    return bytes(unpack_be(data))
