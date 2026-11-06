"""Reading small satellite previews by code: a minimal PNG decoder (8-bit RGB or RGBA,
not interlaced) and a cloud measure. No image library is needed for 80-pixel previews."""

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {2: 3, 6: 4}  # colour type → bytes per pixel (RGB, RGBA)
MIN_VISIBLE = 0.2  # below this share of pixels with data, the image counts as missing


def pixels(png: bytes) -> tuple[int, int, list[tuple[int, int, int, int]]] | None:
    """Width, height and RGBA pixels of a simple PNG, or None for anything else."""
    if not png.startswith(SIGNATURE):
        return None
    position, header, data = 8, b"", bytearray()
    while position + 8 <= len(png):
        length, kind = struct.unpack(">I4s", png[position : position + 8])
        chunk = png[position + 8 : position + 8 + length]
        position += 12 + length
        if kind == b"IHDR":
            header = chunk
        elif kind == b"IDAT":
            data += chunk
        elif kind == b"IEND":
            break
    if len(header) < 13:
        return None
    width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", header[:13])
    step = CHANNELS.get(colour)
    if depth != 8 or step is None or interlace or not 0 < width * height <= 1_000_000:
        return None
    try:
        raw = zlib.decompress(bytes(data))
    except zlib.error:
        return None
    stride = width * step
    if len(raw) < height * (stride + 1):
        return None
    rows: list[bytearray] = []
    previous = bytearray(stride)
    for y in range(height):
        kind = raw[y * (stride + 1)]
        row = bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        _unfilter(kind, row, previous, step)
        rows.append(row)
        previous = row
    found = []
    for row in rows:
        for x in range(width):
            value = row[x * step : x * step + step]
            found.append((value[0], value[1], value[2], value[3] if step == 4 else 255))
    return width, height, found


def _unfilter(kind: int, row: bytearray, above: bytearray, step: int) -> None:
    """Undo one PNG scanline filter in place (none, sub, up, average, Paeth)."""
    for i in range(len(row)):
        left = row[i - step] if i >= step else 0
        up = above[i]
        corner = above[i - step] if i >= step else 0
        if kind == 1:
            row[i] = (row[i] + left) & 0xFF
        elif kind == 2:
            row[i] = (row[i] + up) & 0xFF
        elif kind == 3:
            row[i] = (row[i] + (left + up) // 2) & 0xFF
        elif kind == 4:
            guess = left + up - corner
            near = min(
                (abs(guess - left), 0, left),
                (abs(guess - up), 1, up),
                (abs(guess - corner), 2, corner),
            )
            row[i] = (row[i] + near[2]) & 0xFF


def survey(png: bytes) -> tuple[float, float] | None:
    """How much of the area the image covers, and how much of what it covers looks like
    cloud (bright and grey). None when it cannot be read or covers too little to judge (the
    gap between satellite passes, or no pass that day)."""
    decoded = pixels(png)
    if decoded is None:
        return None
    total = len(decoded[2])
    visible = [(r, g, b) for r, g, b, a in decoded[2] if a > 0 and (r, g, b) != (0, 0, 0)]
    if len(visible) < MIN_VISIBLE * total:
        return None
    cloudy = sum(
        1 for r, g, b in visible if min(r, g, b) > 170 and max(r, g, b) - min(r, g, b) < 35
    )
    return len(visible) / total, cloudy / len(visible)


def clear_share(covered: float, cloud: float) -> float:
    """The share of the whole area where the ground can be seen."""
    return covered * (1 - cloud)
