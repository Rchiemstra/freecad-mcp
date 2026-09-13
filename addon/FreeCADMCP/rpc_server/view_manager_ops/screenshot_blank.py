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
    bit_depth = 0
    color_type = 0
    compression = filter_method = interlace = 0
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        chunk_type = data[pos:pos + 4]
        pos += 4
        chunk_data = data[pos:pos + length]
        pos += length + 4
        if chunk_type == b"IHDR" and len(chunk_data) == 13:
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if (
        not idat
        or width == 0
        or height == 0
        or bit_depth != 8
        or compression != 0
        or filter_method != 0
        or interlace != 0
    ):
        return b"", 0
    # Palette PNGs require PLTE expansion.  Treat them as unsupported rather
    # than accidentally classifying an otherwise valid capture as blank.
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type, 0)
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
    previous = bytearray(row_bytes)
    pos = 0
    for _ in range(height):
        if pos + row_bytes + 1 > len(filtered):
            return b"", 0
        filter_type = filtered[pos]
        pos += 1
        row = bytearray(filtered[pos : pos + row_bytes])
        pos += row_bytes
        if filter_type == 1:  # Sub
            for index in range(row_bytes):
                left = row[index - bpp] if index >= bpp else 0
                row[index] = (row[index] + left) & 0xFF
        elif filter_type == 2:  # Up
            for index in range(row_bytes):
                row[index] = (row[index] + previous[index]) & 0xFF
        elif filter_type == 3:  # Average
            for index in range(row_bytes):
                left = row[index - bpp] if index >= bpp else 0
                row[index] = (row[index] + ((left + previous[index]) // 2)) & 0xFF
        elif filter_type == 4:  # Paeth
            for index in range(row_bytes):
                left = row[index - bpp] if index >= bpp else 0
                up = previous[index]
                up_left = previous[index - bpp] if index >= bpp else 0
                predictor = left + up - up_left
                distances = (
                    abs(predictor - left),
                    abs(predictor - up),
                    abs(predictor - up_left),
                )
                paeth = (
                    left
                    if distances[0] <= distances[1] and distances[0] <= distances[2]
                    else (up if distances[1] <= distances[2] else up_left)
                )
                row[index] = (row[index] + paeth) & 0xFF
        elif filter_type != 0:
            return b"", 0
        out.extend(row)
        previous = row
    return bytes(out), bpp
