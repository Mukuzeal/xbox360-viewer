"""Builds the marketplace DLC catalog: title ID -> how many downloadable items exist.

Run it to create or refresh dlc_catalog.csv:

    python catalog.py

Source is the community scrape of download.xbox.com hosted on archive.org. Each
link looks like

    http://download.xbox.com/content/<titleid>/<sha1>.xcp

so the title ID is exact -- no name matching. Avatar-item URLs are skipped.

The count is every downloadable item Microsoft published for that title, which
covers DLC but also themes, gamer pictures, trailers and demos. Treat it as
"there is more content out there for this game", not as an exact DLC count. The
scrape is also not complete: some titles list fewer items than actually shipped.

download.xbox.com still serves these files. They arrive as .xcp -- zlib'd and
encrypted STFS -- so they need decrypting before the console will take them.
"""

import collections
import csv
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request

ITEM = "complete-xbox-360-marketplace-download-links.-7z_202510"
ARCHIVE_URL = ("https://archive.org/download/" + ITEM +
               "/Complete%20Xbox%20360%20Marketplace%20Download%20Links.7z")
CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dlc_catalog.csv")
LINK = re.compile(r"https?://download\.xbox\.com/content/([0-9a-fA-F]{8})/(.*)")


BASE = "http://download.xbox.com/content/%s/%s.xcp"


def url_for(title_id, content_hash):
    """Rebuild a CDN link. The host still serves these."""
    return BASE % (title_id.lower(), content_hash.lower())


def load(path=CATALOG):
    """title_id -> [content hash, ...]. Empty dict if the catalog isn't built."""
    index = collections.defaultdict(list)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                index[row["title_id"].strip().upper()].append(row["content_hash"].strip())
            except (KeyError, AttributeError):
                continue
    return dict(index)


def _download(url, dest):
    """Python's bundled roots reject archive.org here, so prefer certifi, then curl."""
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = None
    try:
        with urllib.request.urlopen(url, timeout=120, context=context) as src:
            with open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
        return
    except (ssl.SSLError, urllib.error.URLError) as exc:
        curl = shutil.which("curl")
        if not curl:
            raise
        print("  urllib failed (%s), retrying with curl" % exc)
        subprocess.run([curl, "-sL", "--max-time", "180", url, "-o", dest], check=True)


def _extract_7z(archive, into):
    """Windows' bundled bsdtar reads 7z; there is no stdlib reader."""
    tar = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")
    if not os.path.isfile(tar):
        raise RuntimeError("need %s (or 7-Zip) to unpack the archive" % tar)
    subprocess.run([tar, "-xf", archive], cwd=into, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for name in os.listdir(into):
        if name.lower().endswith(".txt"):
            return os.path.join(into, name)
    raise RuntimeError("no link list inside the archive")


def build(dest=CATALOG, url=ARCHIVE_URL, log=print):
    """Download the link dump and write title_id,available to dest."""
    with tempfile.TemporaryDirectory() as work:
        archive = os.path.join(work, "links.7z")
        log("downloading %s ..." % url.rsplit("/", 1)[-1])
        _download(url, archive)
        log("  %.1f MB" % (os.path.getsize(archive) / 2 ** 20))

        links = _extract_7z(archive, work)
        found = collections.defaultdict(list)
        with open(links, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = LINK.match(line.strip())
                if not match or "avataritems" in match.group(2):
                    continue
                name = match.group(2).rsplit("/", 1)[-1]
                if name.lower().endswith(".xcp"):
                    found[match.group(1).upper()].append(name[:-4])
        total = sum(len(v) for v in found.values())
        log("  %d content links across %d title IDs" % (total, len(found)))

    with open(dest, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["title_id", "content_hash"])
        for title_id in sorted(found):
            for content_hash in sorted(found[title_id]):
                writer.writerow([title_id, content_hash])
    log("wrote %s (%d rows)" % (dest, total))
    return found


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        print("catalog update failed: %s" % exc, file=sys.stderr)
        sys.exit(1)
