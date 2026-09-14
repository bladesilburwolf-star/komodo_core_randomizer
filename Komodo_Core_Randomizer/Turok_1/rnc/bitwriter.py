class BitWriterM2:
    """Write bits MSB-first into 8-bit tokens, with interleaved byte queue."""

    def __init__(self):
        self.output = bytearray()
        self.pack_token = 0
        self.bit_count = 0
        self.pending = bytearray()
        self.processed = 0
        self.packed = 0
        self.leeway = 0

    def _write_out(self, b: int):
        self.output.append(b & 0xFF)
        self.packed += 1

    def write_bits(self, value: int, count: int):
        mask = 1 << (count - 1)
        for _ in range(count):
            self.pack_token <<= 1
            if value & mask:
                self.pack_token += 1
            mask >>= 1
            self.bit_count += 1

            if self.bit_count == 8:
                self._write_out(self.pack_token)
                for b in self.pending:
                    self._write_out(b)
                self.pending.clear()
                if self.processed > self.packed and self.processed - self.packed > self.leeway:
                    self.leeway = self.processed - self.packed
                self.bit_count = 0
                self.pack_token = 0

    def queue_byte(self, b: int):
        if self.bit_count:
            self.pending.append(b & 0xFF)
        else:
            self._write_out(b)

    def flush_pending(self):
        """Flush pending bytes directly if no bits are buffered."""
        if not self.bit_count:
            for b in self.pending:
                self._write_out(b)
            self.pending.clear()

    def finalize(self) -> bytes:
        if self.bit_count or self.pending:
            self.pack_token <<= 8 - self.bit_count
            self._write_out(self.pack_token)
        for b in self.pending:
            self._write_out(b)
        self.pending.clear()
        return bytes(self.output)


class BitWriterM1:
    """Write bits LSB-first into 16-bit tokens, with interleaved byte queue."""

    def __init__(self):
        self.output = bytearray()
        self.pack_token = 0
        self.bit_count = 0
        self.pending = bytearray()
        self.processed = 0
        self.packed = 0
        self.leeway = 0

    def _write_out(self, b: int):
        self.output.append(b & 0xFF)
        self.packed += 1

    def write_bits(self, value: int, count: int):
        for _ in range(count):
            self.pack_token >>= 1
            if value & 1:
                self.pack_token |= 0x8000
            value >>= 1
            self.bit_count += 1

            if self.bit_count == 16:
                self._write_out(self.pack_token & 0xFF)
                self._write_out((self.pack_token >> 8) & 0xFF)
                for b in self.pending:
                    self._write_out(b)
                self.pending.clear()
                if self.processed > self.packed and self.processed - self.packed > self.leeway:
                    self.leeway = self.processed - self.packed
                self.bit_count = 0
                self.pack_token = 0

    def queue_byte(self, b: int):
        if self.bit_count:
            self.pending.append(b & 0xFF)
        else:
            self._write_out(b)

    def finalize(self) -> bytes:
        # flush remaining bits as partial token
        if self.bit_count or self.pending:
            # pad remaining bits
            self.pack_token >>= 16 - self.bit_count
            self._write_out(self.pack_token & 0xFF)
            self._write_out((self.pack_token >> 8) & 0xFF)
        for b in self.pending:
            self._write_out(b)
        self.pending.clear()
        return bytes(self.output)
