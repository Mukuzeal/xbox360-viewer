"""Minimal STFS (CON/LIVE/PIRS) header reader for Xbox 360 content packages."""

import os

MAGICS = (b"CON ", b"LIVE", b"PIRS")
HEADER_BYTES = 0x571A + 0x4000  # through the end of the title thumbnail

CONTENT_TYPES = {
    0x00000001: "Saved Game",
    0x00000002: "DLC",
    0x00000003: "Publisher",
    0x00001000: "Xbox 360 Title",
    0x00002000: "IPTV Pause Buffer",
    0x00003000: "Installed Game",
    0x00004000: "Xbox Original Game",
    0x00005000: "Xbox Title",
    0x00006000: "Community Game",
    0x00007000: "Game on Demand",
    0x00008000: "System Update",
    0x00009000: "Avatar Item",
    0x00010000: "Profile",
    0x00020000: "Gamer Picture",
    0x00030000: "Theme",
    0x00040000: "Cache File",
    0x00050000: "Storage Download",
    0x00060000: "Xbox Saved Game",
    0x00070000: "Xbox Download",
    0x00080000: "Game Demo / App Data",
    0x00090000: "Video",
    0x000A0000: "Game Title",
    0x000B0000: "Title Update",
    0x000C0000: "Game Trailer",
    0x000D0000: "Arcade Title",
    0x000E0000: "XNA",
    0x000F0000: "License Store",
    0x00100000: "Movie",
    0x00200000: "TV",
    0x00300000: "Music Video",
    0x00400000: "Game Video",
}

# Content types that represent a playable, installed title.
GAME_TYPES = {0x00001000, 0x00003000, 0x00004000, 0x00005000, 0x00006000,
              0x00007000, 0x000A0000, 0x000D0000, 0x000E0000}

# Content types that hold original Xbox (not 360) titles.
XBOX_TYPES = {0x00004000, 0x00005000, 0x00060000, 0x00070000}


def category(content_type):
    if content_type in GAME_TYPES:
        return "Game"
    return {0x00000002: "DLC", 0x000B0000: "Update", 0x00000001: "Save",
            0x00060000: "Save", 0x00010000: "Profile"}.get(content_type, "Other")


def _wstr(buf, off, size=0x80):
    """Decode one UTF-16BE fixed-width field."""
    raw = buf[off:off + size]
    end = len(raw)
    for i in range(0, len(raw) - 1, 2):
        if raw[i] == 0 and raw[i + 1] == 0:
            end = i
            break
    try:
        return raw[:end].decode("utf-16-be").strip()
    except UnicodeDecodeError:
        return ""


def _u32(buf, off):
    return int.from_bytes(buf[off:off + 4], "big")


def read_header(path):
    """Parse an STFS package header. Returns a dict, or None if not a package."""
    try:
        with open(path, "rb") as fh:
            buf = fh.read(HEADER_BYTES)
    except OSError:
        return None
    if len(buf) < 0x1800 or buf[:4] not in MAGICS:
        return None

    thumb_size = _u32(buf, 0x1712)
    title_thumb_size = _u32(buf, 0x1716)
    content_type = _u32(buf, 0x344)

    return {
        "magic": buf[:4].decode("ascii", "replace").strip(),
        "content_type": content_type,
        "content_type_name": CONTENT_TYPES.get(content_type, "Unknown (0x%X)" % content_type),
        "category": category(content_type),
        "content_size": int.from_bytes(buf[0x34C:0x354], "big"),
        "media_id": "%08X" % _u32(buf, 0x354),
        "version": _u32(buf, 0x358),
        "base_version": _u32(buf, 0x35C),
        "title_id": "%08X" % _u32(buf, 0x360),
        "disc_number": buf[0x366],
        "disc_in_set": buf[0x367],
        "data_file_count": _u32(buf, 0x39D),
        # Both fields span an 18-locale 0x900 region; some writers run the first
        # string past the 0x80 slot, so scan the whole region to the NUL.
        "display_name": _wstr(buf, 0x411, 0x900),
        "description": _wstr(buf, 0xD11, 0x900),
        "publisher": _wstr(buf, 0x1611),
        "title_name": _wstr(buf, 0x1691),
        "thumbnail": buf[0x171A:0x171A + thumb_size] if 0 < thumb_size <= 0x4000 else b"",
        "title_thumbnail": buf[0x571A:0x571A + title_thumb_size] if 0 < title_thumb_size <= 0x4000 else b"",
    }


def dir_size(path):
    """Total bytes under a directory (no symlink following)."""
    total = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total
