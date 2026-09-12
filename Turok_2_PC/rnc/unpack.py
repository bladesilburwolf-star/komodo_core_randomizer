from rnc.bitreader import BitReader
from rnc.bits import inverse_bits, ror16
from rnc.constants import HEADER_SIZE
from rnc.crc import crc16
from rnc.header import RncHeader, parse_header


def _unpack_m2(reader: BitReader, header: RncHeader, key: int) -> bytearray:
    """Decompress method 2 data."""
    output = bytearray()
    processed = 0
    initial_key = key

    while processed < header.unpacked_size:
        key = initial_key
        while True:
            if not reader.read_bits_m2(1):
                # literal byte
                b = (key ^ reader.read_byte()) & 0xFF
                output.append(b)
                key = ror16(key)
                processed += 1
            else:
                if reader.read_bits_m2(1):
                    if reader.read_bits_m2(1):
                        if reader.read_bits_m2(1):
                            # long match: count from stream
                            match_count = reader.read_byte() + 8
                            if match_count == 8:
                                # end of chunk marker
                                reader.read_bits_m2(1)
                                break
                        else:
                            match_count = 3

                        # decode match offset (full)
                        match_offset = _decode_match_offset(reader)
                    else:
                        # short match: 2 bytes, 1-byte offset
                        match_count = 2
                        match_offset = reader.read_byte() + 1

                    processed += match_count
                    for _ in range(match_count):
                        output.append(output[-match_offset])
                else:
                    # medium match or raw literal run
                    match_count = _decode_match_count(reader)

                    if match_count != 9:
                        match_offset = _decode_match_offset(reader)
                        processed += match_count
                        for _ in range(match_count):
                            output.append(output[-match_offset])
                    else:
                        # raw literal run
                        data_length = (reader.read_bits_m2(4) << 2) + 12
                        processed += data_length
                        for _ in range(data_length):
                            b = (key ^ reader.read_byte()) & 0xFF
                            output.append(b)
                        key = ror16(key)

    return output


def _decode_match_count(reader: BitReader) -> int:
    """Decode match count for method 2."""
    count = reader.read_bits_m2(1) + 4

    if reader.read_bits_m2(1):
        count = ((count - 1) << 1) + reader.read_bits_m2(1)

    return count


def _decode_match_offset(reader: BitReader) -> int:
    """Decode match offset for method 2."""
    offset = 0

    if reader.read_bits_m2(1):
        offset = reader.read_bits_m2(1)

        if reader.read_bits_m2(1):
            offset = ((offset << 1) | reader.read_bits_m2(1)) | 4

            if not reader.read_bits_m2(1):
                offset = (offset << 1) | reader.read_bits_m2(1)
        elif not offset:
            offset = reader.read_bits_m2(1) + 2

    return ((offset << 8) | reader.read_byte()) + 1


def _make_huftable(reader: BitReader) -> list[tuple[int, int]]:
    """Read a huffman table from the stream. Returns list of (bit_depth, code)."""
    leaf_nodes = reader.read_bits_m1(5)

    if not leaf_nodes:
        return []

    if leaf_nodes > 16:
        leaf_nodes = 16

    bit_depths = [reader.read_bits_m1(4) for _ in range(leaf_nodes)]

    # assign canonical codes (proc_20)
    codes = [0] * leaf_nodes
    val = 0
    div = 0x80000000

    for bits_count in range(1, 17):
        for i in range(leaf_nodes):
            if bit_depths[i] == bits_count:
                codes[i] = inverse_bits(val // div, bits_count)
                val += div
        div >>= 1

    return [(bit_depths[i], codes[i]) for i in range(leaf_nodes)]


def _decode_table_data(reader: BitReader, table: list[tuple[int, int]]) -> int:
    """Decode a value from a huffman table."""
    for i, (depth, code) in enumerate(table):
        if depth and code == (reader.bit_buffer & ((1 << depth) - 1)):
            reader.read_bits_m1(depth)
            if i < 2:
                return i
            return reader.read_bits_m1(i - 1) | (1 << (i - 1))

    raise ValueError("failed to decode huffman value")


def _unpack_m1(reader: BitReader, header: RncHeader, key: int) -> bytearray:
    """Decompress method 1 data."""
    output = bytearray()
    processed = 0
    initial_key = key

    while processed < header.unpacked_size:
        key = initial_key
        raw_table = _make_huftable(reader)
        len_table = _make_huftable(reader)
        pos_table = _make_huftable(reader)

        subchunks = reader.read_bits_m1(16)

        for sc in range(subchunks):
            data_length = _decode_table_data(reader, raw_table)
            processed += data_length

            if data_length:
                for _ in range(data_length):
                    b = (key ^ reader.read_byte()) & 0xFF
                    output.append(b)

                key = ror16(key)

                # reload lookahead into bit buffer after reading raw bytes
                if reader.pos + 2 < reader.end:
                    hi = reader.data[reader.pos + 2]
                else:
                    hi = 0
                if reader.pos + 1 < reader.end:
                    mid = reader.data[reader.pos + 1]
                else:
                    mid = 0
                if reader.pos < reader.end:
                    lo = reader.data[reader.pos]
                else:
                    lo = 0

                reader.bit_buffer = (((hi << 16) | (mid << 8) | lo) << reader.bit_count) | (
                    reader.bit_buffer & ((1 << reader.bit_count) - 1)
                )

            if sc < subchunks - 1:
                match_offset = _decode_table_data(reader, len_table) + 1
                match_count = _decode_table_data(reader, pos_table) + 2
                processed += match_count

                for _ in range(match_count):
                    output.append(output[-match_offset])

    return output


def unpack(data: bytes | bytearray, key: int = 0, verify_crc: bool = True) -> bytes:
    """Decompress RNC ProPack compressed data.

    Args:
        data: raw file data starting with RNC header
        key: encryption key (0 for unencrypted files)
        verify_crc: if False, skip packed/unpacked CRC checks

    Returns:
        decompressed data as bytes

    Raises:
        ValueError: on invalid header, CRC mismatch, or corrupt data
    """
    header = parse_header(data)

    # verify packed CRC
    if verify_crc:
        packed_crc = crc16(data, HEADER_SIZE, header.packed_size)
        if packed_crc != header.packed_crc:
            raise ValueError(f"packed CRC mismatch: expected 0x{header.packed_crc:04X}, " f"got 0x{packed_crc:04X}")

    reader = BitReader(data, HEADER_SIZE, HEADER_SIZE + header.packed_size)

    # first bit: lock flag (must be 0 for unpacking)
    lock_flag = reader.read_bits_m1(1) if header.method == 1 else reader.read_bits_m2(1)
    if lock_flag:
        raise ValueError("file is locked and cannot be unpacked")

    # second bit: encryption flag
    enc_flag = reader.read_bits_m1(1) if header.method == 1 else reader.read_bits_m2(1)
    if enc_flag and not key:
        raise ValueError("file is encrypted but no key provided")

    if header.method == 1:
        output = _unpack_m1(reader, header, key)
    else:
        output = _unpack_m2(reader, header, key)

    # verify unpacked CRC
    if verify_crc:
        unpacked_crc = crc16(output)
        if unpacked_crc != header.unpacked_crc:
            raise ValueError(f"unpacked CRC mismatch: expected 0x{header.unpacked_crc:04X}, " f"got 0x{unpacked_crc:04X}")

    return bytes(output)
