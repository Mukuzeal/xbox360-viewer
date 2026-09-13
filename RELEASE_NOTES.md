A desktop app for browsing everything installed on an RGH/JTAG console's drive
-- Xbox 360 games, original Xbox games, DLC, title updates, saves and homebrew.
First release.

## Download

**Xbox360ContentViewer.exe** (29 MB) -- double-click and go. No Python, no
installer, nothing to unpack. Requires 64-bit Windows.

Windows SmartScreen will warn you on first run because the exe is unsigned:
choose **More info -> Run anyway**.

    SHA-256  2bfba74811210bdf2ca0e87f354c392717afaa3b49a763e1a840db11b864560f

## What it does

Nothing is matched by guesswork -- every title names itself.

- **Xbox 360 packages** are read straight from their STFS (`CON `/`LIVE`/`PIRS`)
  header: title name, title ID, media ID, disc number, and the 64x64 cover art
  embedded in the package.
- **Original Xbox games** are read from the certificate inside `default.xbe`:
  title ID, name, region and disc number, plus an MD5 of the file itself.
- **DLC and title updates** are matched to their game by title ID wherever they
  live -- under `Games\` or under a profile in `Content\`. Selecting a game
  lists each add-on with its size.
- **Dump identification** cross-checks against the bundled Iso2God gamelists
  (3,079 Xbox 360 titles by media ID, 1,134 original Xbox titles by XBE MD5) and
  tells you whether what you have matches a known dump, or is patched, rebuilt
  or simply unlisted.

## Where it looks

`Games\`, `Content\` per profile, `Apps\` for homebrew, and the `Xbox1\` /
`XboxOriginals\` folders for drives that keep original Xbox titles apart.
Drives are auto-detected, and you can point it at any folder instead.

A `Games` folder holding neither a readable package nor a valid `default.xbe`
is flagged **Empty / incomplete** in orange, so half-copied installs are easy
to spot.

Rows filter by category and platform, sort on any column, and export to CSV.

## Running from source

`python viewer.py` needs only Python 3 with tkinter. Pillow is optional --
without it you lose the cover thumbnails, everything else works.
