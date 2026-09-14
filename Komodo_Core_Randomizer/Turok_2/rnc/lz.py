"""LZ77 match finding for RNC ProPack compression.

Works directly on the input data array. Match offsets are distances
back from the current position (1 = previous byte).
"""

from rnc.constants import MAX_MATCHES, PACK_BLOCK_SIZE


def scan_block(
    data,
    offset,
    size,
    block_size=PACK_BLOCK_SIZE,
    max_matches=MAX_MATCHES,
    max_offset=0xFFFF,
    raw_freq=None,
    pos_freq=None,
    len_freq=None,
):
    """Scan data for LZ77 matches, return match records.

    Each record is (data_length, match_count_minus2, match_offset_minus1).

    If freq lists are provided, frequency counts are accumulated
    for Huffman table building (method 1).

    Returns list of tuples and the number of bytes consumed.
    """
    end = min(offset + block_size, size)
    records = []
    pos = offset
    data_length = 0
    match_total = 0

    while pos < end - 1 and match_total < 0xFFFE:
        count, m_offset = _find_best_match(data, pos, end, offset, max_matches, max_offset)

        if count >= 2 and pos + count <= end:
            records.append((data_length, count - 2, m_offset - 1))

            if raw_freq is not None:
                _update_freq(raw_freq, data_length)
            if pos_freq is not None:
                _update_freq(pos_freq, count - 2)
            if len_freq is not None:
                _update_freq(len_freq, m_offset - 1)

            pos += count
            match_total += 1
            data_length = 0
        else:
            pos += 1
            data_length += 1

    # remaining bytes
    data_length += end - pos

    # final record: remaining literals, no match
    records.append((data_length, 0, 0))

    if raw_freq is not None:
        _update_freq(raw_freq, data_length)

    return records, end - offset


def _find_best_match(data, pos, end, start, max_matches, max_offset=0xFFFF):
    """Find best match at data[pos] looking back to data[start].

    Uses simple scanning (no hash chains). Returns (count, offset).
    Offset is distance back (1 = previous byte).
    """
    if pos <= start:
        return 1, 0

    best_count = 1
    best_offset = 0
    avail = end - pos
    lookback = pos - start

    if lookback > max_offset:
        lookback = max_offset

    b0 = data[pos]
    b1 = data[pos + 1] if pos + 1 < end else -1

    dist = 1
    while dist <= lookback:
        # quick 2-byte check
        if data[pos - dist] == b0 and (b1 < 0 or data[pos - dist + 1] == b1):
            # extend match
            count = 0
            max_count = min(avail, max_matches)
            while count < max_count and data[pos + count] == data[pos - dist + count]:
                count += 1

            if count >= best_count:
                best_count = count
                best_offset = dist

                if best_count >= max_matches:
                    break

        dist += 1

    # reject 2-byte matches with large offsets (not worth encoding)
    if best_count == 2 and best_offset > 0x100:
        return 1, 0

    return best_count, best_offset


def _find_match_with_lookahead(data, pos, end, start, max_matches):
    """Find match with lookahead validation.

    If next position has a better match, emit current as literal.
    """
    count, offset = _find_best_match(data, pos, end, start, max_matches)

    if count >= 2 and end - pos >= 3:
        next_count, _ = _find_best_match(data, pos + 1, end, start, max_matches)
        if count < next_count:
            return 1, 0

    return count, offset


def _update_freq(freq, value):
    """Update frequency table for a value (bits_count-based indexing)."""
    if value <= 1:
        idx = value
    else:
        idx = value.bit_length()
    if idx < len(freq):
        freq[idx] += 1
