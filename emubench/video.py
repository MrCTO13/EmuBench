"""Decode the untimed software frame captured by the native worker."""
import hashlib
from struct import iter_unpack


def rgb_frame(blob):
    header, raw = blob.split(b"\n", 1)
    w, h, fmt = map(int, header.split())
    if fmt not in (0, 1, 2) or not 0 < w <= 512 or not 0 < h <= 512 or len(raw) != w*h*(4 if fmt == 1 else 2):
        raise ValueError("Invalid checkpoint framebuffer")
    rgb = bytearray()
    for (v,) in iter_unpack("<I" if fmt == 1 else "<H", raw):
        if fmt == 1:
            r, g, b = v >> 19 & 31, v >> 11 & 31, v >> 3 & 31
        elif fmt == 2:
            r, g, b = v >> 11 & 31, v >> 6 & 31, v & 31
        else:
            r, g, b = v >> 10 & 31, v >> 5 & 31, v & 31
        rgb.extend((r << 3, g << 3, b << 3))
    return w, h, rgb


def fingerprint(blob):
    w, h, rgb = rgb_frame(blob)
    return hashlib.sha256(w.to_bytes(2,"big") + h.to_bytes(2,"big") + rgb).hexdigest()
