import struct
from dataclasses import dataclass

from rnc.constants import HEADER_SIZE, RNC_SIGNATURE


@dataclass(frozen=True)
class RncHeader:
    method: int
    unpacked_size: int
    packed_size: int
    unpacked_crc: int
    packed_crc: int
    leeway: int
    chunk_count: int


def parse_header(data: bytes | bytearray) -> RncHeader:
    if len(data) < HEADER_SIZE:
        raise ValueError(f"data too short for RNC header: {len(data)} < {HEADER_SIZE}")

    sig, method, unpacked_size, packed_size, unpacked_crc, packed_crc, leeway, chunk_count = struct.unpack_from(
        ">3sBIIHHBB", data
    )

    if sig != RNC_SIGNATURE:
        raise ValueError(f"invalid RNC signature: {sig!r}")

    if method not in (1, 2):
        raise ValueError(f"unsupported RNC method: {method}")

    if len(data) < HEADER_SIZE + packed_size:
        raise ValueError(f"data too short: {len(data)} < {HEADER_SIZE + packed_size}")

    return RncHeader(
        method=method,
        unpacked_size=unpacked_size,
        packed_size=packed_size,
        unpacked_crc=unpacked_crc,
        packed_crc=packed_crc,
        leeway=leeway,
        chunk_count=chunk_count,
    )
