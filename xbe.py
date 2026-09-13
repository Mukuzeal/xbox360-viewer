"""Minimal default.xbe reader for original Xbox games.

Layout follows Iso2God's XbeHeader / XbeCertifcate: little-endian, the
certificate sits at (CertificateAddress - BaseAddress) in the file.
"""

import hashlib
import os

MAGIC = b"XBEH"
MAX_HEADER = 0x10000

REGIONS = [(0x00000001, "NTSC-U"), (0x00000002, "NTSC-J"),
           (0x00000004, "PAL"), (0x80000000, "Manufacturing")]


def _u32(buf, off):
    return int.from_bytes(buf[off:off + 4], "little")


def _wstr(buf, off, size):
    raw = buf[off:off + size]
    end = len(raw)
    for i in range(0, len(raw) - 1, 2):
        if raw[i] == 0 and raw[i + 1] == 0:
            end = i
            break
    try:
        return raw[:end].decode("utf-16-le").strip()
    except UnicodeDecodeError:
        return ""


def region_name(flags):
    names = [name for bit, name in REGIONS if flags & bit]
    return "/".join(names) if names else "Region %d" % flags


def file_md5(path, chunk=1 << 20):
    digest = hashlib.md5()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(chunk), b""):
                digest.update(block)
    except OSError:
        return ""
    return digest.hexdigest().upper()


def read_xbe(path, with_md5=True):
    """Parse a default.xbe. Returns a dict, or None if it isn't an XBE."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            head = fh.read(min(MAX_HEADER, size))
    except OSError:
        return None
    if head[:4] != MAGIC or len(head) < 0x180:
        return None

    base = _u32(head, 0x104)
    cert_off = _u32(head, 0x118) - base
    if not 0 <= cert_off <= len(head) - 0xB0:
        return None

    cert = head[cert_off:]
    return {
        "title_id": "%08X" % _u32(cert, 0x08),
        "title_name": _wstr(cert, 0x0C, 0x50),
        "region": region_name(_u32(cert, 0xA0)),
        "disc_number": _u32(cert, 0xA8),
        "version": _u32(cert, 0xAC),
        "xbe_size": size,
        "md5": file_md5(path) if with_md5 else "",
    }
