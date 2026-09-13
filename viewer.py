"""Xbox 360 RGH content viewer -- browse the games installed on a modded console's drive.

Usage:  python viewer.py [drive_or_folder]
"""

import io
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanner

try:
    from PIL import Image, ImageTk
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

BG = "#16181a"
PANEL = "#1e2124"
ROW_ALT = "#1a1d1f"
FG = "#e6e8ea"
DIM = "#8b9296"
ACCENT = "#107C10"
BORDER = "#2c3134"


# (label, categories, platform, extra test) -- None means "no restriction".
FILTERS = [
    ("Games", ("Game",), None, None),
    ("Xbox 360 games", ("Game",), "Xbox 360", None),
    ("Original Xbox games", ("Game",), "Xbox", None),
    ("Games + broken", ("Game", "Broken"), None, None),
    ("DLC", ("DLC",), None, None),
    ("Title updates", ("Update",), None, None),
    ("Saves", ("Save",), None, None),
    ("Apps", ("App",), None, None),
    ("Everything", None, None, None),
]

COLUMNS = [
    ("name", "Title", 280, "w"),
    ("platform", "Platform", 74, "center"),
    ("title_id", "Title ID", 78, "center"),
    ("ident", "Media ID / MD5", 118, "center"),
    ("type", "Type", 124, "w"),
    ("disc", "Disc", 46, "center"),
    ("dlc", "DLC", 68, "center"),
    ("size", "Size", 84, "e"),
    ("where", "Location", 120, "w"),
]


def clip(text, limit):
    """Trim to a word boundary instead of mid-word."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def dlc_text(item):
    """How many add-ons are installed for a game; blank for anything else."""
    if item["category"] != "Game":
        return ""
    return str(len(item["dlc"]))


def ident_of(item):
    """The hash that identifies this dump: media ID on 360, default.xbe MD5 on Xbox."""
    return item.get("md5") or item.get("media_id") or ""


def human_size(n):
    if not n:
        return "--"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit in ("B", "KB"):
                return "%d %s" % (value, unit)
            return "%.1f %s" % (value, unit)
        value /= 1024.0


class Viewer(tk.Tk):
    def __init__(self, initial_root=None):
        super().__init__()
        self.title("Xbox 360 Content Viewer")
        self.geometry("1180x680")
        self.minsize(940, 480)
        self.configure(bg=BG)

        self.items = []
        self.shown = []
        self.icons = {}
        self.detail_image = None
        self.sort_key = "name"
        self.sort_desc = False
        self.scan_thread = None
        self.cancel_scan = False
        self.events = queue.Queue()

        self.lists = scanner.load_gamelists()
        self._build_style()
        self._build_ui()

        drives = scanner.find_drives()
        choices = [d for d in drives if d.upper() != "C:\\"] or drives
        self.drive_box["values"] = choices
        start = initial_root or (choices[-1] if choices else "")
        if start:
            self.drive_var.set(start)
            self.after(120, self.start_scan)

    # ---------------------------------------------------------------- styling
    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, fieldbackground=PANEL,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Panel.TLabel", background=PANEL, foreground=FG)
        style.configure("Dim.TLabel", background=PANEL, foreground=DIM)
        style.configure("Head.TLabel", background=PANEL, foreground=FG,
                        font=("Segoe UI Semibold", 13))
        style.configure("Sub.TLabel", background=PANEL, foreground=FG,
                        font=("Segoe UI Semibold", 9))
        style.configure("Dlc.TLabel", background=PANEL, foreground=DIM,
                        font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=PANEL, foreground=DIM)
        style.configure("TButton", background=PANEL, foreground=FG, borderwidth=1,
                        focuscolor=BG, padding=(10, 4))
        style.map("TButton", background=[("active", "#2a2f33"), ("disabled", PANEL)],
                  foreground=[("disabled", DIM)])
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=FG, arrowcolor=FG, padding=3)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)],
                  selectbackground=[("readonly", PANEL)], selectforeground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

        row_height = 38 if HAVE_PIL else 24
        style.configure("Treeview", background=BG, fieldbackground=BG, foreground=FG,
                        rowheight=row_height, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=PANEL, foreground=DIM,
                        relief="flat", padding=(6, 6), font=("Segoe UI Semibold", 9))
        style.map("Treeview.Heading", background=[("active", "#2a2f33")])
        style.map("Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])
        style.configure("TProgressbar", background=ACCENT, troughcolor=PANEL, borderwidth=0)

    # --------------------------------------------------------------------- ui
    def _build_ui(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")

        ttk.Label(bar, text="Drive").pack(side="left", padx=(0, 6))
        self.drive_var = tk.StringVar()
        self.drive_box = ttk.Combobox(bar, textvariable=self.drive_var, width=12,
                                      state="readonly")
        self.drive_box.pack(side="left")
        self.drive_box.bind("<<ComboboxSelected>>", lambda _e: self.start_scan())

        ttk.Button(bar, text="Browse...", command=self.browse).pack(side="left", padx=6)
        self.scan_btn = ttk.Button(bar, text="Rescan", command=self.start_scan)
        self.scan_btn.pack(side="left")

        ttk.Label(bar, text="Show").pack(side="left", padx=(18, 6))
        self.filter_var = tk.StringVar(value=FILTERS[0][0])
        filt = ttk.Combobox(bar, textvariable=self.filter_var, width=20, state="readonly",
                            values=[f[0] for f in FILTERS])
        filt.pack(side="left")
        filt.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ttk.Button(bar, text="Export CSV", command=self.export).pack(side="right")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_a: self.refresh())
        search = tk.Entry(bar, textvariable=self.search_var, bg=PANEL, fg=FG,
                          insertbackground=FG, relief="flat", width=28,
                          highlightthickness=1, highlightbackground=BORDER,
                          highlightcolor=ACCENT)
        search.pack(side="right", padx=8, ipady=4)
        ttk.Label(bar, text="Search").pack(side="right")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        self.tree = ttk.Treeview(left, columns=[c[0] for c in COLUMNS],
                                 show="tree headings", selectmode="browse")
        self.tree.column("#0", width=44 if HAVE_PIL else 0,
                         minwidth=44 if HAVE_PIL else 0, stretch=False)
        for key, label, width, anchor in COLUMNS:
            self.tree.heading(key, text=label, anchor="w",
                              command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "name"))
        self.tree.tag_configure("odd", background=ROW_ALT)
        self.tree.tag_configure("broken", foreground="#d98b5f")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda _e: self.open_location())

        bar_y = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        bar_y.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=bar_y.set)

        self.detail = ttk.Frame(body, style="Panel.TFrame", width=308, padding=14)
        self.detail.pack(side="right", fill="y", padx=(10, 0))
        self.detail.pack_propagate(False)

        self.thumb_label = tk.Label(self.detail, bg=PANEL, bd=0)
        self.thumb_label.pack(anchor="w")
        self.detail_title = ttk.Label(self.detail, text="Select a title",
                                      style="Head.TLabel", wraplength=270)
        self.detail_title.pack(anchor="w", pady=(10, 2))
        self.detail_sub = ttk.Label(self.detail, text="", style="Dim.TLabel", wraplength=270)
        self.detail_sub.pack(anchor="w")

        self.fields = ttk.Frame(self.detail, style="Panel.TFrame")
        self.fields.pack(fill="x", pady=12)

        self.dlc_box = ttk.Frame(self.detail, style="Panel.TFrame")
        self.dlc_box.pack(fill="x", pady=(0, 10))

        self.detail_desc = ttk.Label(self.detail, text="", style="Dim.TLabel",
                                     wraplength=270, justify="left")
        self.detail_desc.pack(anchor="w")

        btns = ttk.Frame(self.detail, style="Panel.TFrame")
        btns.pack(side="bottom", fill="x")
        ttk.Button(btns, text="Open folder", command=self.open_location).pack(fill="x")

        foot = ttk.Frame(self, style="Panel.TFrame", padding=(10, 6))
        foot.pack(fill="x", side="bottom")
        self.status = ttk.Label(foot, text="Ready", style="Status.TLabel")
        self.status.pack(side="left")
        self.progress = ttk.Progressbar(foot, mode="indeterminate", length=160)

    # ---------------------------------------------------------------- actions
    def browse(self):
        path = filedialog.askdirectory(
            title="Pick the drive or folder holding Games and Content")
        if path:
            path = os.path.normpath(path)
            values = list(self.drive_box["values"])
            if path not in values:
                self.drive_box["values"] = values + [path]
            self.drive_var.set(path)
            self.start_scan()

    def start_scan(self):
        if self.scan_thread and self.scan_thread.is_alive():
            self.cancel_scan = True
            return
        root = self.drive_var.get()
        if not root or not os.path.isdir(root):
            messagebox.showwarning("No drive", "Pick a drive or folder to scan.")
            return

        self.cancel_scan = False
        self.scan_btn.configure(text="Stop")
        self.progress.pack(side="right")
        self.progress.start(12)
        self.tree.delete(*self.tree.get_children())
        self.icons.clear()
        self.items = []

        # The worker only touches the queue; Tk calls all happen on the main thread.
        def work():
            try:
                found = scanner.scan(root, self.lists,
                                     progress=lambda m: self.events.put(("progress", m)),
                                     cancelled=lambda: self.cancel_scan)
            except OSError as exc:
                self.events.put(("error", str(exc)))
                found = []
            self.events.put(("done", found))

        self.scan_thread = threading.Thread(target=work, daemon=True)
        self.scan_thread.start()
        self.pump()

    def pump(self):
        """Drain worker events on the main thread."""
        running = True
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self.set_status("Scanning " + payload)
            elif kind == "error":
                messagebox.showerror("Scan failed", payload)
            elif kind == "done":
                self.scan_done(payload)
                running = False
        if running and self.scan_thread and self.scan_thread.is_alive():
            self.after(60, self.pump)

    def scan_done(self, found):
        self.items = found
        self.progress.stop()
        self.progress.pack_forget()
        self.scan_btn.configure(text="Rescan")
        self.refresh()

    def set_status(self, text):
        self.status.configure(text=text)

    def sort_by(self, key):
        self.sort_desc = not self.sort_desc if self.sort_key == key else False
        self.sort_key = key
        self.refresh()

    # ---------------------------------------------------------------- display
    def refresh(self):
        wanted, platform, extra = {f[0]: f[1:] for f in FILTERS}[self.filter_var.get()]
        query = self.search_var.get().strip().lower()

        rows = [i for i in self.items if wanted is None or i["category"] in wanted]
        if platform:
            rows = [i for i in rows if i["platform"] == platform]
        if extra:
            rows = [i for i in rows if extra(i)]
        if query:
            rows = [i for i in rows
                    if query in i["name"].lower()
                    or query in i["title_id"].lower()
                    or query in ident_of(i).lower()
                    or query in i.get("known_name", "").lower()]

        def sort_value(item):
            if self.sort_key == "size":
                return item["size"]
            if self.sort_key == "disc":
                return item.get("disc_number", 0)
            if self.sort_key == "type":
                return item["content_type_name"].lower()
            if self.sort_key == "where":
                return item["source"].lower()
            if self.sort_key == "ident":
                return ident_of(item).lower()
            if self.sort_key == "platform":
                return item["platform"]
            if self.sort_key == "dlc":
                return len(item.get("dlc") or [])
            return str(item.get(self.sort_key, "")).lower()

        rows.sort(key=sort_value, reverse=self.sort_desc)
        self.shown = rows

        self.tree.delete(*self.tree.get_children())
        self.icons.clear()
        for n, item in enumerate(rows):
            discs = item.get("disc_in_set", 0)
            disc_text = "%d/%d" % (item["disc_number"], discs) if discs > 1 else ""
            where = item["source"]
            if item["profile"] and item["profile"] != "0000000000000000":
                where += " \u00b7 profile"
            tags = ["odd"] if n % 2 else []
            if item["category"] == "Broken":
                tags.append("broken")
            ident = ident_of(item)
            self.tree.insert("", "end", iid=str(n), image=self.icon_for(item, n), tags=tags,
                             values=(item["name"], item["platform"],
                                     item["title_id"] or "--",
                                     (ident[:12] + "…") if len(ident) > 14 else (ident or "--"),
                                     item["content_type_name"], disc_text,
                                     dlc_text(item),
                                     human_size(item["size"]), where))

        games = [i for i in self.items if i["category"] == "Game"]
        total = sum(i["size"] for i in self.items)
        counts = {}
        for i in self.items:
            counts[i["category"]] = counts.get(i["category"], 0) + 1
        parts = ["%d game%s" % (len(games), "" if len(games) == 1 else "s")]
        for label, plural, key in (("DLC", "DLC", "DLC"), ("update", "updates", "Update"),
                                   ("save", "saves", "Save"), ("app", "apps", "App"),
                                   ("broken", "broken", "Broken")):
            n = counts.get(key, 0)
            if n:
                parts.append("%d %s" % (n, label if n == 1 else plural))
        self.set_status("%s  \u00b7  %s on disk  \u00b7  showing %d"
                        % (", ".join(parts), human_size(total), len(rows)))

    def icon_for(self, item, index):
        if not HAVE_PIL:
            return ""
        data = item.get("title_thumbnail") or item.get("thumbnail")
        if not data:
            return ""
        try:
            img = Image.open(io.BytesIO(data)).convert("RGBA").resize((32, 32), Image.LANCZOS)
        except Exception:
            return ""
        self.icons["row%d" % index] = ImageTk.PhotoImage(img)
        return self.icons["row%d" % index]

    def on_select(self, _event=None):
        item = self.selected()
        for child in self.fields.winfo_children():
            child.destroy()
        for child in self.dlc_box.winfo_children():
            child.destroy()
        if not item:
            return

        data = item.get("title_thumbnail") or item.get("thumbnail")
        self.detail_image = None
        if data and HAVE_PIL:
            try:
                img = Image.open(io.BytesIO(data)).convert("RGBA").resize((128, 128),
                                                                          Image.LANCZOS)
                self.detail_image = ImageTk.PhotoImage(img)
            except Exception:
                pass
        self.thumb_label.configure(image=self.detail_image or "")

        self.detail_title.configure(text=item["name"])
        sub = item["content_type_name"]
        if item.get("publisher"):
            sub += " \u00b7 " + item["publisher"]
        self.detail_sub.configure(text=sub)

        rows = [("Platform", item["platform"]),
                ("Title ID", item["title_id"] or "--")]
        if item.get("md5"):
            rows.append(("XBE MD5", item["md5"]))
        elif item.get("media_id"):
            rows.append(("Media ID", item["media_id"]))
        rows.append(("Size", human_size(item["size"])))
        if item.get("region"):
            rows.append(("Region", item["region"]))
        if item.get("disc_in_set", 0) > 1:
            rows.append(("Disc", "%d of %d" % (item["disc_number"], item["disc_in_set"])))
        if item.get("version"):
            rows.append(("Version", str(item["version"])))
        if item.get("known_name") and item["known_name"] != item["name"]:
            rows.append(("Gamelist", item["known_name"]))
        known = item.get("known_hashes") or []
        ident = ident_of(item)
        if ident and known:
            rows.append(("Known dump", "yes" if ident in known else "not in gamelist"))
        elif ident and item["title_id"]:
            rows.append(("Known dump", "title ID not in gamelist"))
        rows.append(("Path", item["path"].replace(self.drive_var.get(), "")))

        for n, (label, value) in enumerate(rows):
            ttk.Label(self.fields, text=label, style="Dim.TLabel").grid(
                row=n, column=0, sticky="nw", pady=2, padx=(0, 10))
            ttk.Label(self.fields, text=value, style="Panel.TLabel",
                      wraplength=180, justify="left").grid(row=n, column=1,
                                                           sticky="nw", pady=2)

        self.show_dlc(item)
        self.detail_desc.configure(text=clip(item.get("description"), 150))

    def show_dlc(self, item):
        """List the DLC installed for this title."""
        if item["category"] == "DLC" and item.get("parent_name"):
            ttk.Label(self.dlc_box, text="Add-on for " + item["parent_name"],
                      style="Dlc.TLabel", wraplength=262,
                      justify="left").pack(anchor="w")
            return
        if item["category"] != "Game":
            return

        dlc = item.get("dlc") or []
        if dlc:
            total = sum(d["size"] for d in dlc)
            ttk.Label(self.dlc_box,
                      text="Installed DLC (%d) · %s" % (len(dlc), human_size(total)),
                      style="Sub.TLabel").pack(anchor="w", pady=(0, 4))
            for add_on in dlc[:5]:
                ttk.Label(self.dlc_box,
                          text="• %s  (%s)" % (add_on["name"], human_size(add_on["size"])),
                          style="Dlc.TLabel", wraplength=262,
                          justify="left").pack(anchor="w")
            if len(dlc) > 5:
                ttk.Label(self.dlc_box, text="+ %d more" % (len(dlc) - 5),
                          style="Dlc.TLabel").pack(anchor="w")
        else:
            ttk.Label(self.dlc_box, text="No DLC installed",
                      style="Sub.TLabel").pack(anchor="w")

    def selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self.shown[int(sel[0])]

    def open_location(self):
        item = self.selected()
        if not item:
            return
        target = item["path"] if os.path.isdir(item["path"]) else os.path.dirname(item["path"])
        try:
            subprocess.Popen(["explorer", os.path.normpath(target)])
        except OSError as exc:
            messagebox.showerror("Could not open", str(exc))

    def export(self):
        if not self.shown:
            messagebox.showinfo("Nothing to export", "Scan a drive first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            initialfile="xbox360_content.csv")
        if not path:
            return
        import csv
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["title_name", "platform", "title_id", "media_id", "xbe_md5",
                             "content_type", "disc", "dlc_installed",
                             "size_bytes", "size", "path"])
            for i in self.shown:
                writer.writerow([i["name"], i["platform"], i["title_id"],
                                 i["media_id"], i["md5"], i["content_type_name"],
                                 "%d/%d" % (i["disc_number"], i["disc_in_set"])
                                 if i.get("disc_in_set", 0) > 1 else "",
                                 len(i["dlc"]),
                                 i["size"], human_size(i["size"]), i["path"]])
        self.set_status("Exported %d rows to %s" % (len(self.shown), path))


if __name__ == "__main__":
    Viewer(sys.argv[1] if len(sys.argv) > 1 else None).mainloop()
