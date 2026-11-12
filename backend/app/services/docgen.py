"""Tiny generators for FICTIONAL sample files (seeded invoices, demo uploads). Pure Python, no dependencies.

make_pdf builds a one-page PDF with correct cross-reference offsets; make_png builds an RGB image.
They exist so the demo has real, valid files to upload and download.
"""
from __future__ import annotations

import struct
import zlib


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(title: str, lines: list[str]) -> bytes:
    text = [f"BT /F1 20 Tf 60 780 Td ({_esc(title)}) Tj ET"]
    y = 740
    for ln in lines:
        text.append(f"BT /F1 12 Tf 60 {y} Td ({_esc(ln)}) Tj ET")
        y -= 22
    text.append("BT /F1 9 Tf 60 40 Td (FICTIONAL DOCUMENT - generated for the FlowGuard hackathon demo. Not a real invoice.) Tj ET")
    stream = "\n".join(text).encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def make_png(width: int = 480, height: int = 300, label_seed: int = 7) -> bytes:
    """A placeholder 'delivery photograph': sky, ground, a truck-like block and a signature scribble."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)                                           # filter type 0
        for x in range(width):
            if y < height * 0.55:                                # sky gradient
                r, g, b = 150 + y // 6, 190 + y // 10, 235
            else:                                                # ground
                r, g, b = 96, 104, 112
            if 70 < x < 330 and 120 < y < 210:                   # trailer
                r, g, b = 235, 240, 245
            if 330 <= x < 410 and 150 < y < 210:                 # cab
                r, g, b = 24, 48, 90
            if (x - 130) ** 2 + (y - 215) ** 2 < 400 or (x - 360) ** 2 + (y - 215) ** 2 < 400:   # wheels
                r, g, b = 20, 20, 24
            if y > 250 and abs((x * (label_seed + 3)) % 60 - 30) < 3 + (y - 250) // 8:            # "signature"
                r, g, b = 10, 30, 120
            rows += bytes((r, g, b))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")
