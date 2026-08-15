"""Near-blank PNG detection for personal-view capture fallbacks."""

from __future__ import annotations

import struct
import zlib

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_BLANK_PIXEL_VARIANCE_THRESHOLD = 4.0


def is_near_blank_png(image: bytes | bytearray | memoryview) -> bool:
    """Return True when decoded pixels are nearly uniform (empty personal-view)."""
    if not isinstance(image, (bytes, bytearray, memoryview)):
        return False
    raw = bytes(image)
    if not raw.startswith(_PNG_SIGNATURE):
        return False
    pixels, bpp = _decode_png_sample_bytes(raw)
    if bpp <= 0 or len(pixels) < bpp * 4:
        return False
    pixel_count = len(pixels) // bpp
    first = pixels[:bpp]
    for index in range(1, pixel_count):
        start = index * bpp
        if pixels[start:start + bpp] != first:
            mean = sum(pixels) / len(pixels)
            variance = sum((value - mean) ** 2 for value in pixels) / len(pixels)
            return variance < _BLANK_PIXEL_VARIANCE_THRESHOLD
    return True


def _decode_png_sample_bytes(data: bytes) -> tuple[bytes, int]:  # noqa: C901
    pos = 8
    width = 0
    height = 0
    color_type = 0
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        chunk_type = data[pos:pos + 4]
        pos += 4
        chunk_data = data[pos:pos + length]
        pos += length + 4
        if chunk_type == b"IHDR" and len(chunk_data) >= 10:
            width, height, _bit_depth, color_type = struct.unpack(
                ">IIBB", chunk_data[:10]
            )
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if not idat or width == 0 or height == 0:
        return b"", 0
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 0)
    if bpp == 0:
        return b"", 0
    try:
        filtered = zlib.decompress(bytes(idat))
    except zlib.error:
        return b"", 0
    row_bytes = width * bpp
    if row_bytes == 0:
        return b"", 0
    out = bytearray()
    pos = 0
    for _ in range(height):
        if pos >= len(filtered):
            break
        pos += 1
        row = filtered[pos:pos + row_bytes]
        pos += row_bytes
        out.extend(row)
    return bytes(out), bpp
