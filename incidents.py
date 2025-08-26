import os
import sqlite3
import time
import tkinter as tk
from tkinter import ttk, messagebox, font as tkFont


class Database:
    def __init__(self, path="incidents.db"):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                assignee TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                author TEXT,
                text TEXT NOT NULL,
                FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()

    def _next_incident_id(self):
        row = self.conn.execute(
            "SELECT id FROM incidents WHERE id LIKE 'INC-%' "
            "ORDER BY CAST(SUBSTR(id,5) AS INTEGER) DESC LIMIT 1"
        ).fetchone()
        n = int(row["id"][4:]) + 1 if row else 1
        return f"INC-{n:03d}"

    def list_incidents(self, search=""):
        if search:
            q = f"%{search}%"
            rows = self.conn.execute(
                "SELECT * FROM incidents "
                "WHERE id LIKE ? OR title LIKE ? "
                "ORDER BY created_at DESC",
                (q, q),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM incidents ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_incident(self, inc_id):
        r = self.conn.execute("SELECT * FROM incidents WHERE id=?", (inc_id,)).fetchone()
        return dict(r) if r else None

    def insert_incident(self, data):
        inc_id = self._next_incident_id()
        now = time.strftime("%Y-%m-%d %H:%M")
        self.conn.execute(
            "INSERT INTO incidents (id,title,severity,status,assignee,created_at,resolved_at) "
            "VALUES (?,?,?,?,?,?,NULL)",
            (inc_id, data["title"], data["severity"], data["status"], data["assignee"], now),
        )
        self.conn.commit()
        return inc_id

    def update_incident(self, data):
        self.conn.execute(
            "UPDATE incidents SET title=?, severity=?, status=?, assignee=? WHERE id=?",
            (data["title"], data["severity"], data["status"], data["assignee"], data["id"]),
        )
        if data.get("status") == "Resolved":
            self.conn.execute(
                "UPDATE incidents SET resolved_at=? WHERE id=? AND resolved_at IS NULL",
                (time.strftime("%Y-%m-%d %H:%M"), data["id"]),
            )
        self.conn.commit()

    def resolve_incident(self, inc_id):
        self.conn.execute(
            "UPDATE incidents SET status='Resolved', resolved_at=? WHERE id=?",
            (time.strftime("%Y-%m-%d %H:%M"), inc_id),
        )
        self.conn.commit()

    def list_timeline(self, inc_id):
        rows = self.conn.execute(
            "SELECT * FROM timeline WHERE incident_id=? ORDER BY ts ASC", (inc_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def add_timeline(self, inc_id, author, text, ts=None):
        ts = ts or time.strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "INSERT INTO timeline (incident_id, ts, author, text) VALUES (?,?,?,?)",
            (inc_id, ts, author, text),
        )
        self.conn.commit()

    def update_timeline(self, tl_id, text):
        self.conn.execute("UPDATE timeline SET text=? WHERE id=?", (text, tl_id))
        self.conn.commit()

    def delete_timeline(self, tl_id):
        self.conn.execute("DELETE FROM timeline WHERE id=?", (tl_id,))
        self.conn.commit()

    def metrics(self):
        r_total = self.conn.execute(
            "SELECT COUNT(*) AS c FROM incidents WHERE status!='Resolved'"
        ).fetchone()
        r_p0 = self.conn.execute(
            "SELECT COUNT(*) AS c FROM incidents WHERE status!='Resolved' AND severity='P0'"
        ).fetchone()
        r_unassigned = self.conn.execute(
            "SELECT COUNT(*) AS c FROM incidents "
            "WHERE status!='Resolved' AND (assignee IS NULL OR assignee='')"
        ).fetchone()
        r_resolved = self.conn.execute(
            "SELECT created_at, resolved_at FROM incidents WHERE resolved_at IS NOT NULL"
        ).fetchall()
        mttr = "-"
        if r_resolved:
            tot = 0
            n = 0
            for row in r_resolved:
                try:
                    t1 = time.strptime(row["created_at"], "%Y-%m-%d %H:%M")
                    t2 = time.strptime(row["resolved_at"], "%Y-%m-%d %H:%M")
                    tot += int(time.mktime(t2) - time.mktime(t1)) // 60
                    n += 1
                except Exception:
                    pass
            if n:
                mttr = f"~{tot // n} min"
        return {
            "active": str(r_total["c"]),
            "p0": str(r_p0["c"]),
            "unassigned": str(r_unassigned["c"]),
            "mttr": mttr,
        }

    def recent_activity(self, limit=12):
        rows = self.conn.execute(
            "SELECT t.ts, t.author, t.text, t.incident_id "
            "FROM timeline t ORDER BY t.ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


class ThemeManager:
    TOKYO_DARK = {
        "bg": "#1a1b26",
        "panel": "#24283b",
        "card": "#2a2f45",
        "fg": "#c0caf5",
        "muted": "#a9b1d6",
        "accent": "#7aa2f7",
        "border": "#3b4261",
        "select": "#394b70",
        "entry_bg": "#1f2335",
        "text_bg": "#1f2335",
    }
    TOKYO_LIGHT = {
        "bg": "#f5f7fb",
        "panel": "#ffffff",
        "card": "#ffffff",
        "fg": "#111827",
        "muted": "#374151",
        "accent": "#2563eb",
        "border": "#e5e7eb",
        "select": "#eaf2ff",
        "entry_bg": "#ffffff",
        "text_bg": "#ffffff",
    }

    def __init__(self, app: tk.Tk, initial="TokyoDark"):
        self.app = app
        self.style = ttk.Style(self.app)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.current = initial
        self._tokyo = {"TokyoDark": self.TOKYO_DARK, "TokyoLight": self.TOKYO_LIGHT}
        self._text_widgets = []

    def register_text(self, widget: tk.Text):
        self._text_widgets.append(widget)

    def palette(self):
        return self._tokyo[self.current]

    def apply(self):
        c = self.palette()
        self.app.configure(bg=c["bg"])

        self.style.configure(".", background=c["panel"], foreground=c["fg"], fieldbackground=c["entry_bg"])
        self.style.configure("TFrame", background=c["panel"])
        self.style.configure("Panel.TFrame", background=c["panel"])
        self.style.configure("Card.TFrame", background=c["card"], borderwidth=1, relief="solid")
        self.style.configure("Muted.TLabel", background=c["panel"], foreground=c["muted"])
        self.style.configure("Accent.TLabel", background=c["panel"], foreground=c["accent"])
        self.style.configure("Small.TLabel", background=c["panel"], foreground=c["fg"], font=tkFont.Font(size=10))

        self.style.configure("TButton", padding=8)
        self.style.map("TButton", background=[("active", c["select"])])

        self.style.configure("Sidebar.TButton", background=c["panel"], relief="flat", anchor="w", padding=8)
        self.style.map("Sidebar.TButton", background=[("active", c["select"])])

        self.style.configure("TEntry", fieldbackground=c["entry_bg"], foreground=c["fg"],
                             bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"])
        self.style.configure("TCombobox", fieldbackground=c["entry_bg"], foreground=c["fg"], bordercolor=c["border"])

        self.style.configure("TNotebook", background=c["panel"], borderwidth=0)
        self.style.configure("TNotebook.Tab", padding=(12, 6))
        self.style.map("TNotebook.Tab", background=[("selected", c["select"])], foreground=[("selected", c["fg"])])

        self.style.configure("Treeview", background=c["panel"], fieldbackground=c["panel"],
                             foreground=c["fg"], bordercolor=c["border"])
        self.style.configure("Treeview.Heading", background=c["panel"], foreground=c["fg"])

        self.style.configure("TProgressbar", background=c["accent"])

        self.style.configure("Pill.TLabel", background=c["card"], foreground=c["fg"])
        self.style.configure("Pill.TFrame", background=c["card"], borderwidth=1, relief="solid")

        for w in self._text_widgets:
            try:
                w.configure(bg=c["text_bg"], fg=c["fg"], insertbackground=c["fg"])
            except tk.TclError:
                pass

    def toggle(self):
        self.current = "TokyoLight" if self.current == "TokyoDark" else "TokyoDark"
        self.apply()


class TimelineDialog(tk.Toplevel):
    def __init__(self, parent, db: Database, incident_id: str, theme: ThemeManager, on_change=None):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.incident_id = incident_id
        self.theme = theme
        self.on_change = on_change

        inc = self.db.get_incident(self.incident_id)
        self.title(f"Timeline · {inc['id']} · {inc['title']}")
        self.geometry("820x560")
        self.configure(bg=self.theme.palette()["bg"])
        self.transient(parent)
        self.grab_set()

        root = ttk.Frame(self, style="Panel.TFrame")
        root.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        top = ttk.Frame(root, style="Panel.TFrame")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.grid_columnconfigure(0, weight=1)
        ttk.Label(top, text=inc["title"], style="Small.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, text=f"[{inc['severity']}] {inc['status']}", style="Muted.TLabel").grid(row=0, column=1, sticky="e", padx=8)
        ttk.Button(top, text="Edit", command=self._edit_incident).grid(row=0, column=2, sticky="e")

        mid = ttk.Frame(root, style="Panel.TFrame")
        mid.grid(row=1, column=0, sticky="nsew")
        mid.grid_columnconfigure(0, weight=1)
        mid.grid_rowconfigure(0, weight=1)

        cols = ("ID", "Time", "Author", "Text")
        self.tv = ttk.Treeview(mid, columns=cols, show="headings")
        for col in cols:
            self.tv.heading(col, text=col)
        self.tv.column("ID", width=70, anchor="w")
        self.tv.column("Time", width=170, anchor="w")
        self.tv.column("Author", width=120, anchor="w")
        self.tv.column("Text", width=480, anchor="w")
        self.tv.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")
        self.tv.bind("<Double-1>", self._load_selected_into_editor)

        editor = ttk.Frame(root, style="Card.TFrame", padding=10)
        editor.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        editor.grid_columnconfigure(0, weight=1)
        ttk.Label(editor, text="Paste / Edit", style="Small.TLabel").grid(row=0, column=0, sticky="w")
        self.txt = tk.Text(editor, height=8, wrap="word", bd=0, highlightthickness=0)
        self.txt.grid(row=1, column=0, sticky="nsew", pady=(6, 6))
        self.theme.register_text(self.txt)
        self.theme.apply()

        btns = ttk.Frame(editor, style="Panel.TFrame")
        btns.grid(row=2, column=0, sticky="e")
        ttk.Button(btns, text="Paste", command=self._paste_clip).grid(row=0, column=0, padx=4)
        ttk.Button(btns, text="Append", command=self._append_new).grid(row=0, column=1, padx=4)
        ttk.Button(btns, text="Replace", command=self._replace_selected).grid(row=0, column=2, padx=4)
        ttk.Button(btns, text="Delete", command=self._delete_selected).grid(row=0, column=3, padx=4)
        ttk.Button(btns, text="Close", command=self.destroy).grid(row=0, column=4, padx=4)

        self._reload()
        self.wait_window(self)

    def _reload(self):
        for i in self.tv.get_children():
            self.tv.delete(i)
        for row in self.db.list_timeline(self.incident_id):
            short = (row["text"].replace("\n", " ")[:120] + "…") if len(row["text"]) > 120 else row["text"]
            self.tv.insert("", "end", values=(row["id"], row["ts"], row.get("author", "") or "", short))

    def _paste_clip(self):
        try:
            data = self.clipboard_get()
        except tk.TclError:
            data = ""
        if data:
            self.txt.insert("end", data if data.endswith("\n") else data + "\n")

    def _selected_tl_id(self):
        sel = self.tv.focus()
        if not sel:
            return None
        vals = self.tv.item(sel, "values")
        return int(vals[0]) if vals else None

    def _append_new(self):
        content = self.txt.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("Empty", "Nothing to append.")
            return
        self.db.add_timeline(self.incident_id, "Operator", content)
        self.txt.delete("1.0", "end")
        self._reload()
        if self.on_change:
            self.on_change()

    def _replace_selected(self):
        tl_id = self._selected_tl_id()
        if not tl_id:
            messagebox.showwarning("No Selection", "Select an item to replace.")
            return
        content = self.txt.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("Empty", "Nothing to replace with.")
            return
        self.db.update_timeline(tl_id, content)
        self._reload()
        if self.on_change:
            self.on_change()

    def _delete_selected(self):
        tl_id = self._selected_tl_id()
        if not tl_id:
            messagebox.showwarning("No Selection", "Select an item to delete.")
            return
        self.db.delete_timeline(tl_id)
        self._reload()
        if self.on_change:
            self.on_change()

    def _load_selected_into_editor(self, _evt=None):
        tl_id = self._selected_tl_id()
        if not tl_id:
            return
        row = self.parent.db.conn.execute("SELECT text FROM timeline WHERE id=?", (tl_id,)).fetchone()
        self.txt.delete("1.0", "end")
        if row:
            self.txt.insert("1.0", row["text"])

    def _edit_incident(self):
        IncidentDialog(self.parent, db=self.db, incident_id=self.incident_id,
                       theme=self.theme, on_save=self._after_edit)

    def _after_edit(self):
        inc = self.db.get_incident(self.incident_id)
        self.parent.refresh_incident_list()
        self.parent.update_dashboard_metrics()
        self.parent.update_recent_activity()
        self.title(f"Timeline · {inc['id']} · {inc['title']}")


class IncidentDialog(tk.Toplevel):
    def __init__(self, parent, db: Database, incident_id=None, theme: ThemeManager=None, on_save=None):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.theme = theme or parent.theme
        self.on_save = on_save
        self.incident_id = incident_id
        inc = self.db.get_incident(incident_id) if incident_id else None

        self.title("New Incident" if not inc else f"Edit Incident {inc['id']}")
        self.geometry("520x360")
        self.configure(bg=self.theme.palette()["bg"])
        self.transient(parent)
        self.grab_set()

        frame = ttk.Frame(self, style="Panel.TFrame")
        frame.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        ttk.Label(frame, text="Title:", style="Small.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        self.e_title = ttk.Entry(frame); self.e_title.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Severity:", style="Small.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        self.cb_sev = ttk.Combobox(frame, values=["P0", "P1", "P2", "P3"], state="readonly")
        self.cb_sev.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Status:", style="Small.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        self.cb_status = ttk.Combobox(frame, values=["Investigating", "Identified", "Monitoring", "Resolved"], state="readonly")
        self.cb_status.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Assignee:", style="Small.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        self.e_assignee = ttk.Entry(frame); self.e_assignee.grid(row=3, column=1, sticky="ew", pady=4)

        btns = ttk.Frame(self, style="Panel.TFrame")
        btns.grid(row=1, column=0, pady=(0, 12))
        ttk.Button(btns, text="Save", command=self._save).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text="Cancel", command=self.destroy).grid(row=0, column=1, padx=6)

        if inc:
            self.e_title.insert(0, inc["title"])
            self.cb_sev.set(inc["severity"])
            self.cb_status.set(inc["status"])
            self.e_assignee.insert(0, inc.get("assignee") or "")
        else:
            self.cb_sev.set("P1")
            self.cb_status.set("Investigating")

        self.wait_window(self)

    def _save(self):
        title = self.e_title.get().strip()
        if not title:
            messagebox.showwarning("Missing", "Title is required.")
            return
        data = {
            "title": title,
            "severity": self.cb_sev.get(),
            "status": self.cb_status.get(),
            "assignee": self.e_assignee.get().strip(),
        }
        if self.incident_id:
            data["id"] = self.incident_id
            self.db.update_incident(data)
        else:
            self.incident_id = self.db.insert_incident(data)
        if self.on_save:
            self.on_save()
        self.destroy()


class App(tk.Tk):
    SIDEBAR_EXPANDED_W = 260
    SIDEBAR_COLLAPSED_W = 72

    def __init__(self):
        super().__init__()
        self.title("E-commerce Incident Management")
        self.geometry("1200x780")

        self.db = Database(os.environ.get("INCIDENT_DB", "incidents.db"))
        self.theme = ThemeManager(self, initial="TokyoDark")
        self.theme.apply()

        self.grid_columnconfigure(0, minsize=self.SIDEBAR_EXPANDED_W)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar_expanded = True

        self._create_sidebar()
        self._create_main()
        self._create_footer()

        self.refresh_incident_list()
        self.update_dashboard_metrics()
        self.update_recent_activity()

    # Sidebar: title removed; search bar added here
    def _create_sidebar(self):
        self.sidebar_frame = ttk.Frame(self, style="Panel.TFrame")
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.sidebar_frame.grid_propagate(False)
        self.sidebar_frame.configure(width=self.SIDEBAR_EXPANDED_W)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self.sidebar_frame, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        header.grid_columnconfigure(0, weight=1)

        # search in sidebar
        self.search_box = ttk.Entry(header)
        self.search_box.insert(0, "Search incidents…")
        self.search_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search_box.bind("<Return>", lambda e: self.refresh_incident_list(self.search_box.get().strip()))

        ttk.Button(header, text="☰", width=3, style="Sidebar.TButton",
                   command=self.toggle_sidebar).grid(row=0, column=1, sticky="e")

        nav_wrap = ttk.Frame(self.sidebar_frame, style="Panel.TFrame")
        nav_wrap.grid(row=1, column=0, sticky="nsew", padx=8)
        self.sidebar_frame.grid_rowconfigure(1, weight=1)

        self.nav_items = [
            ("Dashboard", "🏠", lambda: self.select_tab("Dashboard")),
            ("Incidents", "⚠️", lambda: self.select_tab("Incidents")),
            ("Reports", "📊", lambda: self.select_tab("Reports")),
            ("Configuration", "⚙️", lambda: self.select_tab("Configuration")),
            ("Logs", "🧾", lambda: self.select_tab("Logs")),
            ("Refresh", "🔄", self.refresh_all_data),
            ("Theme", "🌓", self.toggle_theme),
        ]
        self.nav_btns = {}
        for i, (label, icon, cmd) in enumerate(self.nav_items):
            b = ttk.Button(nav_wrap, text=f"{icon}  {label}", style="Sidebar.TButton", command=cmd)
            b.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
            self.nav_btns[label] = b

        bottom = ttk.Frame(self.sidebar_frame, style="Panel.TFrame")
        bottom.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 12))
        ttk.Label(bottom, text=os.path.basename(self.db.path), style="Muted.TLabel").grid(row=0, column=0, sticky="w")

        self._apply_sidebar_width()

    def _apply_sidebar_width(self):
        if self.sidebar_expanded:
            self.grid_columnconfigure(0, minsize=self.SIDEBAR_EXPANDED_W)
            self.sidebar_frame.configure(width=self.SIDEBAR_EXPANDED_W)
            # show search
            self.search_box.grid()  # ensure visible
            for label, icon, _ in self.nav_items:
                self.nav_btns[label].configure(text=f"{icon}  {label}")
        else:
            self.grid_columnconfigure(0, minsize=self.SIDEBAR_COLLAPSED_W)
            self.sidebar_frame.configure(width=self.SIDEBAR_COLLAPSED_W)
            # hide search when collapsed
            self.search_box.grid_remove()
            for label, icon, _ in self.nav_items:
                self.nav_btns[label].configure(text=icon)

    def toggle_sidebar(self):
        self.sidebar_expanded = not self.sidebar_expanded
        self._apply_sidebar_width()

    # Main: header now only a compact stats strip (no big title)
    def _create_main(self):
        self.main_frame = ttk.Frame(self, style="Panel.TFrame")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(2, weight=1)

        # header stats strip
        hdr = ttk.Frame(self.main_frame, style="Panel.TFrame")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for i in range(8):
            hdr.grid_columnconfigure(i, weight=0)
        hdr.grid_columnconfigure(7, weight=1)

        self.hstat_open = ttk.Label(hdr, text="Open: 0", style="Pill.TLabel")
        self.hstat_p0 = ttk.Label(hdr, text="P0: 0", style="Pill.TLabel")
        self.hstat_unassigned = ttk.Label(hdr, text="Unassigned: 0", style="Pill.TLabel")
        self.hstat_mttr = ttk.Label(hdr, text="MTTR: -", style="Pill.TLabel")

        def place_pill(widget, col):
            wrap = ttk.Frame(hdr, style="Pill.TFrame", padding=(8, 4))
            wrap.grid(row=0, column=col, padx=(0 if col == 0 else 8), sticky="w")
            widget.master = wrap
            widget.grid(row=0, column=0, sticky="w")

        place_pill(self.hstat_open, 0)
        place_pill(self.hstat_p0, 1)
        place_pill(self.hstat_unassigned, 2)
        place_pill(self.hstat_mttr, 3)

        # tabs
        self.tab_view = ttk.Notebook(self.main_frame, style="TNotebook")
        self.tab_view.grid(row=2, column=0, sticky="nsew")

        self.tabs = {}
        for name in ["Dashboard", "Incidents", "Reports", "Configuration", "Logs"]:
            f = ttk.Frame(self.tab_view, style="Panel.TFrame")
            self.tab_view.add(f, text=name)
            self.tabs[name] = f

        self._tab_dashboard(self.tabs["Dashboard"])
        self._tab_incidents(self.tabs["Incidents"])
        self._tab_config(self.tabs["Configuration"])
        self._tab_logs(self.tabs["Logs"])

        self.select_tab("Dashboard")

    def _tab_dashboard(self, tab):
        for i in range(4):
            tab.grid_columnconfigure(i, weight=1)

        self.metric_widgets = {}
        def card(col, key, title):
            frame = ttk.Frame(tab, style="Card.TFrame", padding=12)
            frame.grid(row=0, column=col, sticky="nsew", padx=8, pady=8)
            ttk.Label(frame, text=title, style="Small.TLabel").grid(row=0, column=0, sticky="w")
            val = ttk.Label(frame, text="-", style="Accent.TLabel",
                            font=tkFont.Font(size=22, weight="bold"))
            val.grid(row=1, column=0, sticky="w", pady=(4, 0))
            self.metric_widgets[key] = val

        card(0, "active", "Active")
        card(1, "p0", "P0")
        card(2, "unassigned", "Unassigned")
        card(3, "mttr", "Avg. Resolution")

        body = ttk.Frame(tab, style="Card.TFrame", padding=12)
        body.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=8, pady=8)
        tab.grid_rowconfigure(1, weight=1)

        ttk.Label(body, text="Recent Activity", style="Small.TLabel").grid(row=0, column=0, sticky="w")
        self.recent_activity_text = tk.Text(body, height=10, wrap="word", bd=0, highlightthickness=0)
        self.recent_activity_text.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        self.theme.register_text(self.recent_activity_text)
        self.theme.apply()

    def _tab_incidents(self, tab):
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        wrap = ttk.Frame(tab, style="Panel.TFrame")
        wrap.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        cols = ("ID", "Title", "Severity", "Status", "Assignee", "Created At")
        tv = ttk.Treeview(wrap, columns=cols, show="headings")
        for col in cols:
            tv.heading(col, text=col)
        tv.column("ID", width=90, anchor="w")
        tv.column("Title", width=320, anchor="w")
        for c in ("Severity", "Status", "Assignee", "Created At"):
            tv.column(c, width=140, anchor="w")
        tv.grid(row=0, column=0, sticky="nsew")

        sb = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")
        self.incident_tree = tv
        self.incident_tree.bind("<Double-1>", self._open_timeline_from_click)

        actions = ttk.Frame(tab, style="Panel.TFrame")
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(actions, text="New", command=self.open_incident_dialog).grid(row=0, column=0, padx=4, sticky="w")
        ttk.Button(actions, text="Edit", command=self.edit_selected_incident).grid(row=0, column=1, padx=4, sticky="w")
        ttk.Button(actions, text="Resolve", command=self.resolve_selected_incident).grid(row=0, column=2, padx=4, sticky="w")
        ttk.Button(actions, text="Timeline", command=self.open_selected_timeline).grid(row=0, column=3, padx=4, sticky="w")
        actions.grid_columnconfigure(4, weight=1)

    def _tab_config(self, tab):
        tab.grid_columnconfigure((0, 1), weight=1)

        box1 = ttk.Frame(tab, style="Card.TFrame", padding=12)
        box1.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        ttk.Label(box1, text="Notification Service", style="Small.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(box1, text="API Key:", style="Small.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(box1, show="•").grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Label(box1, text="Channel ID:", style="Small.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(box1).grid(row=2, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Button(box1, text="Save").grid(row=3, column=1, sticky="e", pady=(8, 0))
        box1.grid_columnconfigure(1, weight=1)

        box2 = ttk.Frame(tab, style="Card.TFrame", padding=12)
        box2.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        ttk.Label(box2, text="Ticketing (e.g., Jira)", style="Small.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(box2, text="API Token:", style="Small.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(box2, show="•").grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Label(box2, text="Project Key:", style="Small.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(box2).grid(row=2, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Button(box2, text="Test").grid(row=3, column=1, sticky="e", pady=(8, 0))
        box2.grid_columnconfigure(1, weight=1)

    def _tab_logs(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        self.log_textbox = tk.Text(tab, state="disabled", wrap="word", bd=0, highlightthickness=0)
        self.log_textbox.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.theme.register_text(self.log_textbox)
        self.theme.apply()
        self.log_message("Ready")

    def _create_footer(self):
        f = ttk.Frame(self, height=36, style="Panel.TFrame")
        f.grid(row=1, column=1, sticky="ew", padx=16, pady=(0, 16))
        f.grid_propagate(False)
        self.status_label = ttk.Label(f, text="Ready", style="Muted.TLabel")
        self.status_label.grid(row=0, column=0, sticky="w")

    # data/metrics wiring
    def refresh_all_data(self):
        self.refresh_incident_list(self.search_box.get().strip())
        self.update_dashboard_metrics()
        self.update_recent_activity()

    def refresh_incident_list(self, search=""):
        for i in self.incident_tree.get_children():
            self.incident_tree.delete(i)
        c = self.theme.palette()
        rows = self.db.list_incidents(search=search)
        for idx, inc in enumerate(rows):
            tag = "odd" if idx % 2 else "even"
            self.incident_tree.insert(
                "", "end",
                values=(inc["id"], inc["title"], inc["severity"], inc["status"], inc["assignee"] or "", inc["created_at"]),
                tags=(tag,),
            )
        self.incident_tree.tag_configure("even", background=c["panel"])
        self.incident_tree.tag_configure("odd", background=c["card"])

    def update_dashboard_metrics(self):
        m = self.db.metrics()
        self.metric_widgets["active"].configure(text=m["active"])
        self.metric_widgets["p0"].configure(text=m["p0"])
        self.metric_widgets["unassigned"].configure(text=m["unassigned"])
        self.metric_widgets["mttr"].configure(text=m["mttr"])
        # header pills too
        self.hstat_open.configure(text=f"Open: {m['active']}")
        self.hstat_p0.configure(text=f"P0: {m['p0']}")
        self.hstat_unassigned.configure(text=f"Unassigned: {m['unassigned']}")
        self.hstat_mttr.configure(text=f"MTTR: {m['mttr']}")

    def update_recent_activity(self):
        c = self.theme.palette()
        self.recent_activity_text.configure(state="normal", bg=c["text_bg"], fg=c["fg"], insertbackground=c["fg"])
        self.recent_activity_text.delete("1.0", "end")
        for e in self.db.recent_activity(limit=12):
            self.recent_activity_text.insert("end", f"[{e['ts']}] ({e['incident_id']}) {e.get('author','')}: {e['text']}\n")
        self.recent_activity_text.configure(state="disabled")

    def open_incident_dialog(self, incident=None):
        IncidentDialog(self, db=self.db, theme=self.theme, on_save=self._after_edit)

    def _after_edit(self):
        self.refresh_incident_list(self.search_box.get().strip())
        self.update_dashboard_metrics()

    def edit_selected_incident(self):
        sel = self.incident_tree.focus()
        if not sel:
            messagebox.showwarning("No Selection", "Select an incident.")
            return
        inc_id = self.incident_tree.item(sel, "values")[0]
        IncidentDialog(self, db=self.db, incident_id=inc_id, theme=self.theme, on_save=self._after_edit)

    def resolve_selected_incident(self):
        sel = self.incident_tree.focus()
        if not sel:
            messagebox.showwarning("No Selection", "Select an incident.")
            return
        inc_id = self.incident_tree.item(sel, "values")[0]
        self.db.resolve_incident(inc_id)
        self.log_message(f"Incident {inc_id} resolved.")
        self.refresh_all_data()

    def open_selected_timeline(self):
        sel = self.incident_tree.focus()
        if not sel:
            messagebox.showwarning("No Selection", "Select an incident.")
            return
        inc_id = self.incident_tree.item(sel, "values")[0]
        TimelineDialog(self, db=self.db, incident_id=inc_id, theme=self.theme, on_change=self._after_edit)

    def _open_timeline_from_click(self, event):
        row_id = self.incident_tree.identify_row(event.y)
        if not row_id:
            return
        self.incident_tree.selection_set(row_id)
        self.incident_tree.focus(row_id)
        self.open_selected_timeline()

    def select_tab(self, name):
        self.tab_view.select(self.tabs[name])

    def toggle_theme(self):
        self.theme.toggle()
        self.refresh_incident_list(self.search_box.get().strip())
        self.update_recent_activity()
        self.log_message(f"Theme: {self.theme.current}")

    def log_message(self, msg):
        c = self.theme.palette()
        self.log_textbox.configure(state="normal", bg=c["text_bg"], fg=c["fg"], insertbackground=c["fg"])
        self.log_textbox.insert("end", f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
        self.log_textbox.configure(state="disabled")
        self.log_textbox.see("end")


if __name__ == "__main__":
    App().mainloop()
