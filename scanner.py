"""Scans an Xbox 360 (RGH/JTAG) drive for installed games and other content."""

import collections
import csv
import os
import sys

import stfs
import xbe

ISO2GOD_DIR = r"C:\Users\McZeal\Downloads\Uploads\Iso2God-main"
# Frozen by PyInstaller the gamelists live in the unpacked bundle, not beside the exe.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

# Folders an original Xbox game may be dropped into, alongside Games\.
XBOX_ROOTS = ("Games", "Xbox1", "XBOX1", "XboxOriginals", "Xbox Originals")


def _load_list(filename, hash_column):
    """title_id -> {'name': str, 'hashes': [str]} from one Iso2God TSV."""
    index = {}
    path = next((p for p in (os.path.join(HERE, filename),
                             os.path.join(ISO2GOD_DIR, filename))
                 if os.path.isfile(p)), None)
    if not path:
        return index

    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            tid = (row.get("title_id") or "").strip().upper()
            if not tid:
                continue
            entry = index.setdefault(tid, {"name": "", "hashes": []})
            entry["name"] = entry["name"] or (row.get("title_name") or "").strip()
            value = (row.get(hash_column) or "").strip().upper()
            if value and value not in entry["hashes"]:
                entry["hashes"].append(value)
    return index


def load_gamelists():
    """Both Iso2God gamelists: 360 keyed by media ID, Xbox keyed by default.xbe MD5."""
    return {
        "x360": _load_list("gamelist_xbox360.csv", "media_id"),
        "xbox": _load_list("gamelist_xbox.csv", "xbe_md5"),
    }


def find_drives():
    """Drive roots that look like Xbox content drives."""
    roots = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = "%s:\\" % letter
        if not os.path.isdir(root):
            continue
        if any(os.path.isdir(os.path.join(root, sub))
               for sub in ("Games", "Content") + XBOX_ROOTS):
            roots.append(root)
    return roots


def _blank(**fields):
    """A record with every key the viewer expects."""
    item = {
        "name": "", "title_id": "", "media_id": "", "md5": "", "category": "Other",
        "content_type_name": "", "platform": "Xbox 360", "size": 0, "path": "",
        "profile": "", "source": "", "disc_number": 0, "disc_in_set": 0,
        "display_name": "", "description": "", "publisher": "", "title_name": "",
        "thumbnail": b"", "title_thumbnail": b"", "known_name": "", "known_hashes": [],
        "file_name": "", "version": 0, "base_version": 0, "content_size": 0, "region": "",
        "parent_name": "", "dlc": [],
    }
    item.update(fields)
    return item


def _is_title_id(name):
    return len(name) == 8 and all(c in "0123456789ABCDEFabcdef" for c in name)


def _identify(item, lists, fallback=""):
    """Attach gamelist name/hashes for the platform this item belongs to."""
    known = lists["xbox" if item["platform"] == "Xbox" else "x360"].get(item["title_id"], {})
    item["known_name"] = known.get("name", "")
    item["known_hashes"] = known.get("hashes", [])
    if not item["name"]:
        item["name"] = item["known_name"] or fallback or "(unnamed)"
    return item


def _package(path, size, profile, source, lists):
    head = stfs.read_header(path)
    if head is None:
        return None
    platform = "Xbox" if head["content_type"] in stfs.XBOX_TYPES else "Xbox 360"
    addon = head["category"] in ("DLC", "Update")
    item = _blank(**head)
    item.update({
        "name": (head["display_name"] or head["title_name"]) if addon
                else (head["title_name"] or head["display_name"]),
        "parent_name": head["title_name"] if addon else "",
        "platform": platform,
        "size": size,
        "path": path,
        "profile": profile,
        "source": source,
        "file_name": os.path.basename(path),
    })
    return _identify(item, lists)


def _packages_in(type_dir, profile, source, lists):
    """Every STFS package directly inside a content-type folder."""
    out = []
    try:
        entries = sorted(os.scandir(type_dir), key=lambda e: e.name)
    except OSError:
        return out
    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            continue  # .data payload folders are measured with their header
        size = entry.stat().st_size
        data_dir = entry.path + ".data"
        if os.path.isdir(data_dir):
            size += stfs.dir_size(data_dir)
        pkg = _package(entry.path, size, profile, source, lists)
        if pkg:
            out.append(pkg)
    return out


def _xbe_game(game_dir, xbe_path, source, lists):
    """An extracted original Xbox game (a folder holding default.xbe)."""
    info = xbe.read_xbe(xbe_path)
    if info is None:
        return None
    item = _blank(
        name=info["title_name"] or os.path.basename(game_dir),
        title_id=info["title_id"],
        md5=info["md5"],
        category="Game",
        content_type_name="Original Xbox",
        platform="Xbox",
        size=stfs.dir_size(game_dir),
        path=game_dir,
        source=source,
        disc_number=info["disc_number"],
        version=info["version"],
        region=info["region"],
        file_name=os.path.basename(xbe_path),
    )
    return _identify(item, lists)


def _find_xbe(folder):
    """default.xbe directly in a folder, or one level down (multi-disc layouts)."""
    direct = os.path.join(folder, "default.xbe")
    if os.path.isfile(direct):
        return [(folder, direct)]
    found = []
    try:
        for sub in sorted(os.scandir(folder), key=lambda e: e.name):
            if sub.is_dir(follow_symlinks=False):
                nested = os.path.join(sub.path, "default.xbe")
                if os.path.isfile(nested):
                    found.append((sub.path, nested))
    except OSError:
        pass
    return found


def _link_dlc(items):
    """Hang each title's DLC off the game it belongs to, by title ID."""
    by_title = collections.defaultdict(list)
    for item in items:
        if item["category"] == "DLC" and item["title_id"]:
            by_title[item["title_id"]].append(item)
    for group in by_title.values():
        group.sort(key=lambda d: d["name"].lower())
    for item in items:
        if item["category"] == "Game":
            item["dlc"] = by_title.get(item["title_id"], [])
    return items


def _scan_root(root, lists, progress, cancelled):
    """Walk a drive root. Returns a list of content records."""
    items = []

    def note(msg):
        if progress:
            progress(msg)

    def stop():
        return cancelled is not None and cancelled()

    # Games\<TitleID>\<ContentType>\<package>, or an extracted original Xbox folder.
    games_dir = os.path.join(root, "Games")
    if os.path.isdir(games_dir):
        for entry in sorted(os.scandir(games_dir), key=lambda e: e.name):
            if stop():
                return items
            if not entry.is_dir(follow_symlinks=False):
                continue
            note(r"Games\%s" % entry.name)

            found = []
            for type_entry in os.scandir(entry.path):
                if type_entry.is_dir(follow_symlinks=False):
                    found.extend(_packages_in(type_entry.path, "", "Games", lists))
            if found:
                items.extend(found)
                continue

            xbox_games = [_xbe_game(d, x, "Games", lists) for d, x in _find_xbe(entry.path)]
            xbox_games = [g for g in xbox_games if g]
            if xbox_games:
                items.extend(xbox_games)
                continue

            items.append(_identify(_blank(
                title_id=entry.name.upper() if _is_title_id(entry.name) else "",
                category="Broken", content_type_name="Empty / incomplete",
                size=stfs.dir_size(entry.path), path=entry.path, source="Games",
            ), lists, fallback=entry.name))

    # Dedicated original-Xbox folders.
    for folder in XBOX_ROOTS:
        if folder == "Games":
            continue
        xbox_dir = os.path.join(root, folder)
        if not os.path.isdir(xbox_dir):
            continue
        for entry in sorted(os.scandir(xbox_dir), key=lambda e: e.name):
            if stop():
                return items
            if not entry.is_dir(follow_symlinks=False):
                continue
            note("%s\\%s" % (folder, entry.name))
            for game_dir, xbe_path in _find_xbe(entry.path):
                game = _xbe_game(game_dir, xbe_path, folder, lists)
                if game:
                    items.append(game)

    # Content\<ProfileID>\<TitleID>\<ContentType>\<package>
    content_dir = os.path.join(root, "Content")
    if os.path.isdir(content_dir):
        for prof_entry in sorted(os.scandir(content_dir), key=lambda e: e.name):
            if not prof_entry.is_dir(follow_symlinks=False):
                continue
            profile = prof_entry.name
            for tid_entry in sorted(os.scandir(prof_entry.path), key=lambda e: e.name):
                if stop():
                    return items
                if not tid_entry.is_dir(follow_symlinks=False):
                    continue
                note(r"Content\%s\%s" % (profile[:8], tid_entry.name))
                for type_entry in os.scandir(tid_entry.path):
                    if type_entry.is_dir(follow_symlinks=False):
                        items.extend(_packages_in(type_entry.path, profile, "Content", lists))

    # Apps\<Name> -- homebrew, plain folders with no STFS header
    apps_dir = os.path.join(root, "Apps")
    if os.path.isdir(apps_dir):
        for app_entry in sorted(os.scandir(apps_dir), key=lambda e: e.name):
            if stop():
                return items
            if not app_entry.is_dir(follow_symlinks=False):
                continue
            note(r"Apps\%s" % app_entry.name)
            items.append(_blank(
                name=app_entry.name, category="App", content_type_name="Homebrew app",
                size=stfs.dir_size(app_entry.path), path=app_entry.path, source="Apps",
            ))

    return items


def scan(root, lists, progress=None, cancelled=None):
    """Walk a drive root and link each game to its DLC."""
    return _link_dlc(_scan_root(root, lists, progress, cancelled))
