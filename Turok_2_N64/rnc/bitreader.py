class BitReader:
    """Reads bits from a byte buffer, used by both method 1 and method 2."""

    def __init__(self, data: bytes | bytearray, offset: int = 0, end: int | None = None):
        self.data = data
        self.pos = offset
        self.end = len(data) if end is None else end
        self.bit_buffer = 0
        self.bit_count = 0

    def _peek(self, offset: int) -> int:
        i = self.pos + offset
        return self.data[i] if i < self.end else 0

    def read_byte(self) -> int:
        if self.pos >= self.end:
            raise ValueError("unexpected end of packed data")
        b = self._peek(0)
        self.pos += 1
        return b

    def _read_m1_token_byte(self) -> int:
        # Method 1 streams may omit up to two zero padding bytes from the
        # final 16-bit token.
        if self.pos >= self.end + 2:
            raise ValueError("unexpected end of packed data")
        b = self._peek(0)
        self.pos += 1
        return b

    def read_bits_m1(self, count: int) -> int:
        """Read bits in method 1 style (LSB first, 16-bit token, lookahead)."""
        bits = 0
        prev_bits = 1

        for _ in range(count):
            if not self.bit_count:
                b1 = self._read_m1_token_byte()
                b2 = self._read_m1_token_byte()
                # lookahead: peek next 2 bytes without advancing
                lo = self._peek(0)
                hi = self._peek(1)
                self.bit_buffer = (hi << 24) | (lo << 16) | (b2 << 8) | b1
                self.bit_count = 16

            if self.bit_buffer & 1:
                bits |= prev_bits

            self.bit_buffer >>= 1
            prev_bits <<= 1
            self.bit_count -= 1

        return bits

    def read_bits_m2(self, count: int) -> int:
        """Read bits in method 2 style (MSB first, 8-bit token)."""
        bits = 0

        for _ in range(count):
            if not self.bit_count:
                self.bit_buffer = self.read_byte()
                self.bit_count = 8

            bits <<= 1

            if self.bit_buffer & 0x80:
                bits |= 1

            self.bit_buffer <<= 1
            self.bit_count -= 1

        return bits
