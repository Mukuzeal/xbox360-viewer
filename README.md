<p align="center">
  <img src="icon/icon.svg" width="128" alt="Xbox 360 Content Viewer">
</p>

# Xbox 360 Content Viewer

A small GUI for browsing the games installed on an RGH/JTAG console's drive --
both Xbox 360 titles and original Xbox ones.

## Download

Grab **Xbox360ContentViewer.exe** from the
[Releases page](https://github.com/Mukuzeal/xbox360-viewer/releases/latest)
and double-click it. No Python, no install -- the gamelists are baked in.

Windows SmartScreen will warn you the first time, because the exe is unsigned.
**More info -> Run anyway** to get past it.

## Run from source

    python viewer.py            # auto-picks the last detected Xbox drive
    python viewer.py F:\        # or point it at a specific drive/folder

Or double-click **Xbox 360 Content Viewer.bat**.

Requires Python 3 with tkinter. Pillow is optional -- without it you lose the
cover thumbnails, everything else still works.

## Building the exe

    pip install pyinstaller pillow
    pyinstaller --onefile --windowed --name Xbox360ContentViewer \
        --icon icon/icon.ico \
        --add-data "gamelist_xbox360.csv;." --add-data "gamelist_xbox.csv;." \
        --add-data "icon/icon.ico;icon" \
        viewer.py

The result lands in `dist/`. Both gamelists are bundled inside and read back
out of the unpacked bundle at runtime, so the exe ships as a single file.

## What it reads

Nothing is looked up by guesswork -- every title names itself.

### Xbox 360 content

The name, media ID and cover art come out of each package's own STFS
(`CON `/`LIVE`/`PIRS`) header:

| Offset   | Field                      |
|----------|----------------------------|
| `0x344`  | content type               |
| `0x354`  | media ID                   |
| `0x360`  | title ID                   |
| `0x366`  | disc number / discs in set |
| `0x411`  | display name               |
| `0x1691` | title name                 |
| `0x171A` | 64x64 PNG thumbnail        |
| `0x571A` | 64x64 PNG title thumbnail  |

### Original Xbox content

An extracted game is any folder holding a `default.xbe`. The certificate inside
it (at `CertificateAddress - BaseAddress`, little-endian) gives the title ID at
`+0x08`, the title name at `+0x0C`, region at `+0xA0` and disc number at
`+0xA8`. The whole `default.xbe` is also MD5'd, because that hash is how the
Xbox gamelist identifies a specific dump.

STFS packages whose content type is an Xbox-original one (`0x00004000`,
`0x00005000`, `0x00060000`, `0x00070000`) are matched against the Xbox list too.

### Scanned locations

- `Games\<TitleID>\<ContentType>\<package>` -- Games on Demand installs
- `Games\<Name>\default.xbe` -- extracted original Xbox games (one level
  deeper too, for multi-disc layouts)
- `Xbox1\`, `XboxOriginals\`, `Xbox Originals\` -- same, for drives that keep
  them apart
- `Content\<ProfileID>\<TitleID>\<ContentType>\<package>` -- XBLA, DLC, title
  updates, saves, profiles
- `Apps\<Name>` -- homebrew (Aurora, NAND flasher, ...)

A 360 game's size is its header file plus its `.data` payload folder; an
original Xbox game's is its whole folder. A `Games` folder with neither a
package nor a valid `default.xbe` is flagged **Empty / incomplete** in orange.

## DLC

DLC packages (content type `0x00000002`) are matched to their game by title ID,
wherever they live -- `Games\<TitleID>\00000002\` or under a profile in
`Content\`. The **DLC** column counts them per game, and selecting a game lists
each pack with its size; a game with none says so.

Worth knowing: in a DLC package the `title_name` field holds the *game's* name
and `display_name` holds the *add-on's*, so the viewer reads add-on rows the
other way round from game rows. That is why the DLC list reads "Autovista Car
Pack" and not four rows of "Forza Motorsport 4". Title updates (`0x000B0000`)
are named the same way.

Multi-disc games share one title ID, so both discs show the same DLC -- that is
correct, the content belongs to the title rather than to a disc.

## Gamelists

Both Iso2God tab-separated lists ship alongside the scripts and are used only
to fill in a name when a package can't be read, and to tell you whether what
you have matches a known dump:

| File | Key column | Identifies |
|------|-----------|------------|
| `gamelist_xbox360.csv` | `media_id` | which disc revision a 360 game came from |
| `gamelist_xbox.csv` | `xbe_md5` | which dump an original Xbox game came from |

The **Media ID / MD5** column and the detail pane's **Known dump** row show the
result. "not in gamelist" means the hash is unknown -- a patched, rebuilt or
simply unlisted dump, not necessarily a broken one.

## Files

- `viewer.py` -- the tkinter GUI
- `scanner.py` -- drive walker and gamelist lookup
- `stfs.py` -- STFS header parser (Xbox 360 packages)
- `xbe.py` -- default.xbe header parser (original Xbox)
- `gamelist_xbox360.csv`, `gamelist_xbox.csv` -- Iso2God dump lists, bundled into the exe
- `icon/` -- `icon.svg` source, PNG exports, and the multi-size `icon.ico` the exe uses
