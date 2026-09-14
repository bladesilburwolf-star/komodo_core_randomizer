"""Shared bit manipulation utilities."""


def ror16(key):
    """Rotate right 16-bit value by 1."""
    if key & 1:
        return 0x8000 | (key >> 1)
    return key >> 1


def inverse_bits(value, count):
    """Reverse the bit order of value over count bits."""
    result = 0
    for _ in range(count):
        result <<= 1
        if value & 1:
            result |= 1
        value >>= 1
    return result
