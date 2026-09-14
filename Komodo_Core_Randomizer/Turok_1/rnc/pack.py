"""RNC ProPack compression."""

import struct

from rnc.bits import inverse_bits, ror16
from rnc.bitwriter import BitWriterM1, BitWriterM2
from rnc.constants import (
    M2_COUNT_BITS,
    M2_COUNT_BITS_LEN,
    M2_OFFSET_BITS,
    M2_OFFSET_BITS_LEN,
    RNC_SIGNATURE,
)
from rnc.crc import crc16
from rnc.lz import scan_block


# --- Method 2 ---


def _encode_literals_m2(writer, data, offset, count, key):
    """Encode literal byte run for method 2. Returns (new_offset, new_key)."""
    remaining = count

    while remaining > 0:
        if remaining >= 12:
            if remaining & 3:
                writer.write_bits(0, 1)
                b = (key ^ data[offset]) & 0xFF
                writer.queue_byte(b)
                writer.processed += 1
                offset += 1
                remaining -= 1
                key = ror16(key)
            else:
                writer.write_bits(0x17, 5)

                if remaining >= 72:
                    writer.write_bits(0xF, 4)
                    batch = 72
                else:
                    writer.write_bits((remaining - 12) >> 2, 4)
                    batch = remaining

                for _ in range(batch):
                    b = (key ^ data[offset]) & 0xFF
                    writer.queue_byte(b)
                    writer.processed += 1
                    offset += 1

                remaining -= batch
                key = ror16(key)
        else:
            while remaining > 0:
                writer.write_bits(0, 1)
                b = (key ^ data[offset]) & 0xFF
                writer.queue_byte(b)
                writer.processed += 1
                offset += 1
                key = ror16(key)
                remaining -= 1

    return offset, key


# --- Method 1 Huffman ---


def _build_huffman(freq):
    """Build canonical Huffman codes from frequency table.

    Returns list of (bit_depth, code) tuples.
    """
    count = len(freq)
    l1 = list(freq)
    l2 = [0xFFFF] * count
    bit_depth = [0] * count

    non_zero = sum(1 for f in l1 if f)
    if non_zero == 0:
        return [(0, 0)] * count

    if non_zero == 1:
        for i in range(count):
            if l1[i]:
                bit_depth[i] = 1
                break
        codes = _assign_codes(bit_depth, count)
        return list(zip(bit_depth, codes))

    while True:
        d5 = 0xFFFFFFFF
        d6 = 0xFFFFFFFF
        v20 = -1
        v21 = -1

        for i in range(count):
            if l1[i]:
                if l1[i] < d5:
                    d6 = d5
                    v21 = v20
                    d5 = l1[i]
                    v20 = i
                elif l1[i] < d6:
                    d6 = l1[i]
                    v21 = i

        if d5 == 0xFFFFFFFF or d6 == 0xFFFFFFFF:
            break

        l1[v20] += l1[v21]
        l1[v21] = 0
        bit_depth[v20] += 1

        p = v20
        while l2[p] != 0xFFFF:
            p = l2[p]
            bit_depth[p] += 1

        l2[p] = v21
        bit_depth[v21] += 1

        while l2[v21] != 0xFFFF:
            v21 = l2[v21]
            bit_depth[v21] += 1

    codes = _assign_codes(bit_depth, count)
    return list(zip(bit_depth, codes))


def _assign_codes(bit_depth, count):
    codes = [0] * count
    val = 0
    div = 0x80000000

    for bc in range(1, 17):
        for i in range(count):
            if bit_depth[i] == bc:
                codes[i] = inverse_bits(val // div, bc)
                val += div
        div >>= 1

    return codes


def _write_huffman_header(writer, table):
    count = len(table)
    while count > 0 and table[count - 1][0] == 0:
        count -= 1

    writer.write_bits(count, 5)
    for i in range(count):
        writer.write_bits(table[i][0], 4)


def _write_huffman_value(writer, table, value):
    if value > 1:
        bits = value.bit_length()
    else:
        bits = value

    depth, code = table[bits]
    writer.write_bits(code, depth)

    if bits > 1:
        writer.write_bits(value - (1 << (bits - 1)), bits - 1)


# --- Public API ---


def pack(data: bytes | bytearray, method: int = 1, key: int = 0) -> bytes:
    """Compress data using RNC ProPack.

    Args:
        data: raw uncompressed data
        method: compression method (1 or 2)
        key: encryption key (0 for no encryption)

    Returns:
        compressed data with RNC header as bytes

    Raises:
        ValueError: if method is not 1 or 2, or data is empty
    """
    if method not in (1, 2):
        raise ValueError(f"unsupported method: {method}")
    if not data:
        raise ValueError("data is empty")

    total = len(data)
    unpacked_crc = crc16(data)

    if method == 2:
        writer = BitWriterM2()
    else:
        writer = BitWriterM1()

    # flag bits at start of bitstream
    writer.write_bits(0, 1)  # lock flag
    writer.write_bits(1 if key else 0, 1)  # encryption flag

    chunk_count = 0
    data_offset = 0

    while data_offset < total:
        if method == 1:
            raw_freq = [0] * 16
            len_freq = [0] * 16
            pos_freq = [0] * 16
            records, _ = scan_block(
                data,
                data_offset,
                total,
                raw_freq=raw_freq,
                pos_freq=pos_freq,
                len_freq=len_freq,
            )
        else:
            records, _ = scan_block(data, data_offset, total, max_matches=263, max_offset=0x1000)

        read_pos = data_offset
        enc_key = key

        if method == 1:
            raw_table = _build_huffman(raw_freq)
            len_table = _build_huffman(len_freq)
            pos_table = _build_huffman(pos_freq)

            _write_huffman_header(writer, raw_table)
            _write_huffman_header(writer, len_table)
            _write_huffman_header(writer, pos_table)

            writer.write_bits(len(records), 16)

        for i, (lit_count, match_count, match_offset) in enumerate(records):
            is_last = i == len(records) - 1

            if method == 2:
                read_pos, enc_key = _encode_literals_m2(
                    writer,
                    data,
                    read_pos,
                    lit_count,
                    enc_key,
                )
            else:
                _write_huffman_value(writer, raw_table, lit_count)
                if lit_count:
                    for _ in range(lit_count):
                        b = (enc_key ^ data[read_pos]) & 0xFF
                        writer.queue_byte(b)
                        writer.processed += 1
                        read_pos += 1
                    enc_key = ror16(enc_key)

            if not is_last:
                actual_count = match_count + 2

                if method == 2:
                    _encode_match_m2(writer, match_count, match_offset)
                else:
                    _write_huffman_value(writer, len_table, match_offset)
                    _write_huffman_value(writer, pos_table, match_count)

                writer.processed += actual_count
                read_pos += actual_count

        if method == 2:
            # end of chunk marker
            writer.write_bits(0xF, 4)
            writer.queue_byte(0)

            data_offset = read_pos
            if data_offset >= total:
                writer.write_bits(0, 1)
            else:
                writer.write_bits(1, 1)

            writer.flush_pending()
        else:
            data_offset = read_pos

        chunk_count += 1

    payload = writer.finalize()
    leeway = writer.leeway
    if method == 2:
        leeway += 2

    packed_crc = crc16(payload)

    header = struct.pack(
        ">3sBIIHHBB",
        RNC_SIGNATURE,
        method,
        total,
        len(payload),
        unpacked_crc,
        packed_crc,
        leeway & 0xFF,
        chunk_count & 0xFF,
    )

    return header + payload


def _encode_match_m2(writer, mc, mo):
    """Encode a match for method 2.

    The count_bits table entries already include the full bit prefix
    (e.g. mc=1 → 0x0E = 0b1110, mc=2 → 0x08 = 0b1000).
    """
    if mc == 0:
        # short match: 2 bytes, 1-byte offset
        writer.write_bits(0b110, 3)
        writer.queue_byte(mo & 0xFF)
    else:
        if mc >= 7:
            writer.write_bits(0xF, 4)
            writer.queue_byte((mc - 6) & 0xFF)
        else:
            writer.write_bits(M2_COUNT_BITS[mc], M2_COUNT_BITS_LEN[mc])

        hi = mo >> 8
        writer.write_bits(M2_OFFSET_BITS[hi], M2_OFFSET_BITS_LEN[hi])
        writer.queue_byte(mo & 0xFF)
