import os
import io
import csv
import base64
import threading
import sqlite3
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

DB_FILE = "products.db"

class ProductDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Product Management Dashboard")
        self.root.geometry("1300x800")
        self.page_size = 12
        self.current_page = 0
        self.sort_column = None
        self.sort_reverse = False
        self.view_mode = tk.StringVar(value="table")
        self.search_text = tk.StringVar(value="")
        self.page_size_var = tk.IntVar(value=self.page_size)
        self.all_data = []
        self.filtered_data = []
        self.image_cache = {}
        self._setup_theme()
        self._setup_db()
        self._setup_ui()
        self._load_data()

    def _setup_theme(self):
        self.colors = {
            "bg": "#1a1b26",
            "bg2": "#24283b",
            "fg": "#c0caf5",
            "fg_muted": "#a9b1d6",
            "accent": "#7aa2f7",
            "accent2": "#bb9af7",
            "selected": "#414868",
            "warning": "#e0af68",
            "error": "#f7768e",
            "ok": "#9ece6a",
            "card_border": "#2a2e3f"
        }
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=self.colors["bg"], foreground=self.colors["fg"])
        style.configure("Panel.TFrame", background=self.colors["bg"])
        style.configure("SubPanel.TFrame", background=self.colors["bg2"])
        style.configure("Header.TLabel", background=self.colors["bg"], foreground=self.colors["fg"], font=("Segoe UI", 12, "bold"))
        style.configure("Muted.TLabel", background=self.colors["bg"], foreground=self.colors["fg_muted"])
        style.configure("Accent.TButton", padding=8, relief="flat")
        style.map("Accent.TButton", background=[("!disabled", self.colors["accent"]), ("active", self.colors["accent2"])], foreground=[("!disabled", self.colors["bg"])])
        style.configure("TEntry", fieldbackground=self.colors["bg2"], foreground=self.colors["fg"])
        style.configure("TCombobox", fieldbackground=self.colors["bg2"], foreground=self.colors["fg"])
        style.configure("Treeview",
                        background=self.colors["bg2"],
                        foreground=self.colors["fg"],
                        fieldbackground=self.colors["bg2"],
                        rowheight=26,
                        bordercolor=self.colors["card_border"],
                        borderwidth=0)
        style.map("Treeview", background=[("selected", self.colors["selected"])], foreground=[("selected", self.colors["fg"])])

    def _setup_db(self):
        self.conn = sqlite3.connect(DB_FILE)
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE,
                name TEXT,
                price REAL,
                stock INTEGER,
                category TEXT,
                status TEXT,
                image_path TEXT,
                description TEXT
            )
        """)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.commit()

    def _get_db_connection(self):
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _setup_ui(self):
        self.root.configure(bg=self.colors["bg"])
        container = ttk.Frame(self.root, style="Panel.TFrame")
        container.pack(fill=tk.BOTH, expand=True)
        self.left = ttk.Frame(container, style="Panel.TFrame")
        self.left.pack(side=tk.LEFT, fill=tk.Y)
        self.left.configure(width=300)
        self.left.pack_propagate(False)
        self.right = ttk.Frame(container, style="Panel.TFrame")
        self.right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        ttk.Label(self.left, text="Controls", style="Header.TLabel").pack(pady=(12, 6), anchor="w", padx=12)
        ttk.Button(self.left, text="Import CSV", style="Accent.TButton", command=self.import_csv).pack(padx=12, pady=4, fill="x")
        ttk.Button(self.left, text="Export Visible to CSV", style="Accent.TButton", command=self.export_csv).pack(padx=12, pady=4, fill="x")
        ttk.Label(self.left, text="View Mode", style="Muted.TLabel").pack(padx=12, pady=(12, 0), anchor="w")
        view_frame = ttk.Frame(self.left, style="Panel.TFrame")
        view_frame.pack(padx=12, pady=4, anchor="w")
        ttk.Radiobutton(view_frame, text="Table", value="table", variable=self.view_mode, command=self._refresh_view).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(view_frame, text="Cards", value="cards", variable=self.view_mode, command=self._refresh_view).pack(side=tk.LEFT)
        ttk.Label(self.left, text="Search (SKU/Name/Category)", style="Muted.TLabel").pack(padx=12, pady=(12, 0), anchor="w")
        search_entry = ttk.Entry(self.left, textvariable=self.search_text)
        search_entry.pack(padx=12, pady=4, fill="x")
        search_entry.bind("<Return>", lambda e: self._apply_search())
        ttk.Button(self.left, text="Apply Filter", style="Accent.TButton", command=self._apply_search).pack(padx=12, pady=4, fill="x")
        ttk.Button(self.left, text="Clear Filter", style="Accent.TButton", command=self._clear_search).pack(padx=12, pady=(0, 12), fill="x")
        ttk.Label(self.left, text="Page Size", style="Muted.TLabel").pack(padx=12, pady=(6, 0), anchor="w")
        ps = ttk.Combobox(self.left, textvariable=self.page_size_var, values=[6, 12, 24, 48], state="readonly")
        ps.pack(padx=12, pady=4, fill="x")
        ps.bind("<<ComboboxSelected>>", lambda e: self._change_page_size())
        self.stats_label = ttk.Label(self.left, text="Products: 0", style="Header.TLabel")
        self.stats_label.pack(padx=12, pady=(18, 6), anchor="w")
        header = ttk.Frame(self.right, style="Panel.TFrame")
        header.pack(fill="x")
        self.status_label = ttk.Label(header, text="Ready", style="Muted.TLabel")
        self.status_label.pack(side=tk.LEFT, padx=12, pady=8)
        nav = ttk.Frame(header, style="Panel.TFrame")
        nav.pack(side=tk.RIGHT, padx=12, pady=8)
        self.prev_btn = ttk.Button(nav, text="Prev", style="Accent.TButton", command=self.prev_page)
        self.prev_btn.pack(side=tk.LEFT, padx=4)
        self.page_label = ttk.Label(nav, text="Page 1", style="Header.TLabel")
        self.page_label.pack(side=tk.LEFT, padx=6)
        self.next_btn = ttk.Button(nav, text="Next", style="Accent.TButton", command=self.next_page)
        self.next_btn.pack(side=tk.LEFT, padx=4)
        self.content_stack = ttk.Frame(self.right, style="Panel.TFrame")
        self.content_stack.pack(fill=tk.BOTH, expand=True)
        self.table_frame = ttk.Frame(self.content_stack, style="Panel.TFrame")
        cols = ("sku", "name", "price", "stock", "category", "status")
        self.tree = ttk.Treeview(self.table_frame, columns=cols, show="headings")
        headings = {"sku": "SKU", "name": "Name", "price": "Price", "stock": "Stock", "category": "Category", "status": "Status"}
        for cid in cols:
            self.tree.heading(cid, text=headings[cid], command=lambda c=cid: self.sort_by_column(c))
            width = 120 if cid != "name" else 240
            self.tree.column(cid, width=width, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self._table_double_click)
        self.cards_frame = ttk.Frame(self.content_stack, style="Panel.TFrame")
        self.cards_canvas = tk.Canvas(self.cards_frame, bg=self.colors["bg"], highlightthickness=0, bd=0)
        self.cards_scroll = ttk.Scrollbar(self.cards_frame, orient="vertical", command=self.cards_canvas.yview)
        self.cards_inner = tk.Frame(self.cards_canvas, bg=self.colors["bg"])
        self.cards_inner.bind("<Configure>", lambda e: self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox("all")))
        self.cards_canvas.create_window((0, 0), window=self.cards_inner, anchor="nw")
        self.cards_canvas.configure(yscrollcommand=self.cards_scroll.set)
        self.cards_canvas.pack(side="left", fill=tk.BOTH, expand=True)
        self.cards_scroll.pack(side="right", fill="y")
        self._show_table()

    def _load_data(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, sku, name, price, stock, category, status, image_path, description
            FROM products
            ORDER BY id ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        self.all_data = rows
        self._apply_search()
        self.stats_label.config(text=f"Products: {len(self.all_data)}")
        self.status_label.config(text="Loaded products")

    def _apply_search(self):
        q = self.search_text.get().strip().lower()
        if not q:
            self.filtered_data = list(self.all_data)
        else:
            self.filtered_data = [
                r for r in self.all_data
                if q in (r.get("sku") or "").lower()
                or q in (r.get("name") or "").lower()
                or q in (r.get("category") or "").lower()
            ]
        self.current_page = 0
        self._refresh_view()

    def _clear_search(self):
        self.search_text.set("")
        self._apply_search()

    def sort_by_column(self, col):
        reverse = self.sort_column == col and not self.sort_reverse
        self.filtered_data.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=reverse)
        self.sort_column = col
        self.sort_reverse = reverse
        self._refresh_view()

    def _page_slice(self):
        total = len(self.filtered_data)
        start = self.current_page * self.page_size
        end = min(start + self.page_size, total)
        return start, end

    def _change_page_size(self):
        self.page_size = int(self.page_size_var.get())
        self.current_page = 0
        self._refresh_view()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._refresh_view()

    def next_page(self):
        if (self.current_page + 1) * self.page_size < len(self.filtered_data):
            self.current_page += 1
            self._refresh_view()

    def _refresh_view(self):
        total_pages = max(1, (len(self.filtered_data) - 1) // self.page_size + 1)
        self.page_label.config(text=f"Page {self.current_page + 1} of {total_pages}")
        if self.view_mode.get() == "table":
            self._show_table()
            self._update_table()
        else:
            self._show_cards()
            self._update_cards()

    def _show_table(self):
        self.cards_frame.pack_forget()
        self.table_frame.pack(fill=tk.BOTH, expand=True)

    def _show_cards(self):
        self.table_frame.pack_forget()
        self.cards_frame.pack(fill=tk.BOTH, expand=True)

    def _update_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        start, end = self._page_slice()
        for r in self.filtered_data[start:end]:
            self.tree.insert("", "end", iid=str(r["id"]), values=(
                r.get("sku") or "",
                r.get("name") or "",
                f'{(r.get("price") or 0):.2f}',
                int(r.get("stock") or 0),
                r.get("category") or "",
                r.get("status") or "",
            ))

    def _table_double_click(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        prod = next((x for x in self.all_data if x["id"] == pid), None)
        if prod:
            self._open_detail_dialog(prod)

    def _clear_cards(self):
        for w in self.cards_inner.winfo_children():
            w.destroy()

    def _update_cards(self):
        self._clear_cards()
        start, end = self._page_slice()
        data = self.filtered_data[start:end]
        cols = 3 if self.page_size <= 12 else 4
        thumb_w, thumb_h = 120, 120
        for idx, r in enumerate(data):
            card = tk.Frame(self.cards_inner, bg=self.colors["bg2"], bd=1, relief="solid", highlightthickness=0)
            card.configure(highlightbackground=self.colors["card_border"])
            row, col = divmod(idx, cols)
            card.grid(row=row, column=col, padx=12, pady=12, sticky="n")
            card.bind("<Button-1>", lambda e, rr=r: self._open_detail_dialog(rr))
            img_holder = tk.Label(card, bg=self.colors["bg2"])
            img_holder.pack(padx=12, pady=(12, 6))
            photo = self._get_thumbnail_for_product(r, thumb_w, thumb_h)
            if photo is not None:
                img_holder.configure(image=photo)
                img_holder.image = photo
            else:
                ph = tk.Canvas(card, width=thumb_w, height=thumb_h, bg=self.colors["bg"], highlightthickness=0, bd=0)
                ph.create_text(thumb_w//2, thumb_h//2, text="No Image", fill=self.colors["fg_muted"])
                ph.pack(padx=12, pady=(12, 6))
            name = tk.Label(card, text=r.get("name") or "(no name)", bg=self.colors["bg2"], fg=self.colors["fg"], font=("Segoe UI", 10, "bold"))
            name.pack(padx=12, anchor="w")
            sku = tk.Label(card, text=f"SKU: {r.get('sku') or ''}", bg=self.colors["bg2"], fg=self.colors["fg_muted"])
            sku.pack(padx=12, anchor="w")
            details = tk.Label(card, text=f"${(r.get('price') or 0):.2f}  |  Stock: {int(r.get('stock') or 0)}", bg=self.colors["bg2"], fg=self.colors["fg_muted"])
            details.pack(padx=12, pady=(0, 8), anchor="w")
            for w in (img_holder, name, sku, details):
                w.bind("<Button-1>", lambda e, rr=r: self._open_detail_dialog(rr))
        for c in range(cols):
            self.cards_inner.grid_columnconfigure(c, weight=1)

    def _get_thumbnail_for_product(self, r, max_w, max_h):
        pid = r["id"]
        if pid in self.image_cache:
            return self.image_cache[pid]
        path = (r.get("image_path") or "").strip()
        if not path:
            return None
        try:
            if path.startswith("http://") or path.startswith("https://"):
                with urllib.request.urlopen(path, timeout=5) as resp:
                    data = resp.read()
                b64 = base64.b64encode(data).decode("ascii")
                img = tk.PhotoImage(data=b64)
            else:
                if not os.path.exists(path):
                    return None
                img = tk.PhotoImage(file=path)
        except Exception:
            return None
        w, h = img.width(), img.height()
        if w > max_w or h > max_h:
            fx = max(1, w // max_w)
            fy = max(1, h // max_h)
            img = img.subsample(fx, fy)
        self.image_cache[pid] = img
        return img

    def _ensure_db_indexes(self, conn):
        cur = conn.cursor()
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku)")
        conn.commit()

    def _detect_encoding(self, path):
        with open(path, "rb") as fb:
            head = fb.read(8)
        if head.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig", True
        if head.startswith(b"\xff\xfe\x00\x00") or head.startswith(b"\x00\x00\xfe\xff"):
            pass
        if head.startswith(b"\xff\xfe"):
            return "utf-16le", True
        if head.startswith(b"\xfe\xff"):
            return "utf-16be", True
        candidates = ["utf-8", "cp1252", "latin-1", "utf-16", "utf-16le", "utf-16be"]
        with open(path, "rb") as fb:
            sample = fb.read(65536)
        for enc in candidates:
            try:
                sample.decode(enc)
                return enc, False
            except Exception:
                continue
        return "latin-1", False

    def _open_csv_text(self, path):
        enc, _ = self._detect_encoding(path)
        fh = open(path, "rb")
        tw = io.TextIOWrapper(fh, encoding=enc, errors="replace", newline="")
        return tw, enc, fh

    def _sniff_delimiter(self, text_stream):
        pos = text_stream.tell()
        sample = text_stream.read(16384).replace("\x00", "")
        text_stream.seek(pos)
        try:
            d = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
            return d.delimiter if d.delimiter in [",", ";", "\t", "|"] else ","
        except Exception:
            return ","

    def _normalize_header(self, h):
        return (h or "").strip().lower().replace("\u00a0", " ").replace(" ", "").replace("-", "").replace("_", "")

    def _dedupe_headers(self, headers):
        seen = {}
        out = []
        for h in headers:
            base = h
            if base in seen:
                seen[base] += 1
                h = f"{base}{seen[base]}"
            else:
                seen[base] = 0
            out.append(h)
        return out

    def _build_header_map(self, hdrs_norm):
        synonyms = {
            "sku": {"sku", "productcode", "code", "itemcode", "id", "productid"},
            "name": {"name", "title", "productname", "descriptionshort", "itemname"},
            "price": {"price", "unitprice", "sellprice", "rrp", "priceex", "priceinctax"},
            "stock": {"stock", "qty", "quantity", "onhand", "inventory"},
            "category": {"category", "cat", "segment"},
            "status": {"status", "state", "enabled", "active"},
            "image_path": {"image", "imagepath", "imageurl", "picture", "img"},
            "description": {"description", "longdescription", "fulldescription", "details", "notes"}
        }
        mapping = {}
        for target, keys in synonyms.items():
            for i, src in enumerate(hdrs_norm):
                if src in keys:
                    mapping[target] = i
                    break
        return mapping

    def _to_float(self, x):
        s = str(x or "").strip()
        if not s or s.lower() in {"n/a", "na", "null", "none", "-"}:
            return 0.0
        s = s.replace("$", "").replace("€", "").replace("£", "")
        s = s.replace(",", "")
        try:
            return float(s)
        except Exception:
            return 0.0

    def _to_int(self, x):
        s = str(x or "").strip()
        if not s or s.lower() in {"n/a", "na", "null", "none", "-"}:
            return 0
        try:
            return int(float(s.replace(",", "")))
        except Exception:
            return 0

    def _sanitize_cell(self, s):
        return (str(s or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")).strip()

    def import_csv(self):
        path = filedialog.askopenfilename(title="Select products CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        def worker():
            conn = None
            try:
                conn = self._get_db_connection()
                self._ensure_db_indexes(conn)
                try:
                    text, enc, fh = self._open_csv_text(path)
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Import CSV", f"Failed to open file:\n{e}"))
                    return
                try:
                    csv.field_size_limit(10**7)
                    delimiter = self._sniff_delimiter(text)
                    reader = csv.reader(text, delimiter=delimiter)
                    raw_headers = next(reader, None)
                    if not raw_headers:
                        raise ValueError("File has no header row.")
                    headers_norm = [self._normalize_header(h) for h in raw_headers]
                    headers_norm = self._dedupe_headers(headers_norm)
                    target_map = self._build_header_map(headers_norm)
                    cur = conn.cursor()
                    cur.execute("BEGIN")
                    have_upsert = True
                    upsert_sql = """
                        INSERT INTO products (sku, name, price, stock, category, status, image_path, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(sku) DO UPDATE SET
                        name=excluded.name,
                        price=excluded.price,
                        stock=excluded.stock,
                        category=excluded.category,
                        status=excluded.status,
                        image_path=excluded.image_path,
                        description=excluded.description
                    """
                    batch, BATCH_SIZE = [], 500
                    skipped = 0
                    error_lines = []
                    line_no = 1
                    text.seek(0)
                    reader = csv.reader(text, delimiter=delimiter)
                    _ = next(reader, None)
                    def flush_batch():
                        nonlocal have_upsert
                        if not batch:
                            return
                        try:
                            if have_upsert:
                                cur.executemany(upsert_sql, batch)
                            else:
                                for tpl in batch:
                                    sku = tpl[0]
                                    cur.execute("SELECT id FROM products WHERE sku=?", (sku,))
                                    if cur.fetchone():
                                        cur.execute("""
                                            UPDATE products
                                            SET name=?, price=?, stock=?, category=?, status=?, image_path=?, description=?
                                            WHERE sku=?""",
                                            (tpl[1], tpl[2], tpl[3], tpl[4], tpl[5], tpl[6], tpl[7], sku)
                                        )
                                    else:
                                        cur.execute("""
                                            INSERT INTO products (sku, name, price, stock, category, status, image_path, description)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", tpl)
                        except sqlite3.OperationalError:
                            have_upsert = False
                            flush_batch()
                        batch.clear()
                    for row in reader:
                        line_no += 1
                        try:
                            vals = [self._sanitize_cell(row[i]) if i < len(row) else "" for i in range(len(headers_norm))]
                            def get_by_target(t):
                                idx = target_map.get(t, None)
                                return vals[idx] if idx is not None and idx < len(vals) else ""
                            sku = get_by_target("sku")
                            name = get_by_target("name")
                            if not sku or not name:
                                skipped += 1
                                error_lines.append(f"[Line {line_no}] Missing SKU or Name; row skipped.")
                                continue
                            price = self._to_float(get_by_target("price"))
                            stock = self._to_int(get_by_target("stock"))
                            category = get_by_target("category")
                            status = get_by_target("status")
                            image_path = get_by_target("image_path")
                            description = get_by_target("description")
                            batch.append((sku, name, price, stock, category, status, image_path, description))
                            if len(batch) >= BATCH_SIZE:
                                flush_batch()
                        except Exception as e:
                            skipped += 1
                            error_lines.append(f"[Line {line_no}] {e}")
                    flush_batch()
                    conn.commit()
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    self.root.after(0, lambda: messagebox.showerror("Import CSV", f"Failed to import:\n{e}"))
                finally:
                    try:
                        text.detach()
                    except Exception:
                        pass
                    try:
                        fh.close()
                    except Exception:
                        pass
                self.root.after(0, self._load_data)
                self.root.after(0, lambda: self._set_status("Import complete"))
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    def export_csv(self):
        path = filedialog.asksaveasfilename(title="Save visible page as CSV", defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        start, end = self._page_slice()
        rows = self.filtered_data[start:end]
        headers = ["sku", "name", "price", "stock", "category", "status", "image_path", "description"]
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in rows:
                    writer.writerow([r.get(h, "") for h in headers])
            self._set_status(f"Exported {len(rows)} rows")
        except Exception as e:
            messagebox.showerror("Export CSV", f"Failed to export:\n{e}")

    def _open_detail_dialog(self, product_row):
        d = tk.Toplevel(self.root)
        d.title(f"Product Detail – {product_row.get('sku') or ''}")
        d.configure(bg=self.colors["bg"])
        d.geometry("600x520")
        d.transient(self.root)
        d.grab_set()
        def mk_row(parent, label, var):
            fr = tk.Frame(parent, bg=self.colors["bg"])
            fr.pack(fill="x", padx=16, pady=6)
            tk.Label(fr, text=label, bg=self.colors["bg"], fg=self.colors["fg_muted"], width=12, anchor="w").pack(side="left")
            ent = ttk.Entry(fr, textvariable=var)
            ent.pack(side="left", fill="x", expand=True)
            return ent
        v_sku = tk.StringVar(value=product_row.get("sku") or "")
        v_name = tk.StringVar(value=product_row.get("name") or "")
        v_price = tk.StringVar(value=str(product_row.get("price") if product_row.get("price") is not None else "0.0"))
        v_stock = tk.StringVar(value=str(product_row.get("stock") if product_row.get("stock") is not None else "0"))
        v_category = tk.StringVar(value=product_row.get("category") or "")
        v_status = tk.StringVar(value=product_row.get("status") or "")
        v_image = tk.StringVar(value=product_row.get("image_path") or "")
        v_desc = tk.Text(d, height=6, wrap="word", bg=self.colors["bg2"], fg=self.colors["fg"])
        tk.Label(d, text="Edit Product", bg=self.colors["bg"], fg=self.colors["fg"], font=("Segoe UI", 12, "bold")).pack(padx=16, pady=(16, 4), anchor="w")
        mk_row(d, "SKU", v_sku).configure(state="disabled")
        mk_row(d, "Name", v_name)
        mk_row(d, "Price", v_price)
        mk_row(d, "Stock", v_stock)
        mk_row(d, "Category", v_category)
        mk_row(d, "Status", v_status)
        mk_row(d, "Image Path", v_image)
        desc_frame = tk.Frame(d, bg=self.colors["bg"])
        desc_frame.pack(fill="both", expand=False, padx=16, pady=6)
        tk.Label(desc_frame, text="Description", bg=self.colors["bg"], fg=self.colors["fg_muted"], width=12, anchor="w").pack(side="top", anchor="w")
        v_desc.pack(in_=desc_frame, fill="x")
        v_desc.delete("1.0", "end")
        v_desc.insert("1.0", product_row.get("description") or "")
        btns = tk.Frame(d, bg=self.colors["bg"])
        btns.pack(fill="x", padx=16, pady=12)
        ttk.Button(btns, text="Save", style="Accent.TButton", command=lambda: self._save_product(d, product_row["id"], v_name, v_price, v_stock, v_category, v_status, v_image, v_desc)).pack(side="left")
        ttk.Button(btns, text="Delete", style="Accent.TButton", command=lambda: self._delete_product(d, product_row["id"])).pack(side="left", padx=8)
        ttk.Button(btns, text="Close", style="Accent.TButton", command=d.destroy).pack(side="right")

    def _save_product(self, dialog, pid, v_name, v_price, v_stock, v_category, v_status, v_image, v_desc):
        try:
            price = float(v_price.get().strip())
        except Exception:
            messagebox.showerror("Validate", "Price must be a number.")
            return
        try:
            stock = int(float(v_stock.get().strip()))
        except Exception:
            messagebox.showerror("Validate", "Stock must be an integer.")
            return
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE products
            SET name=?, price=?, stock=?, category=?, status=?, image_path=?, description=?
            WHERE id=?
        """, (
            v_name.get().strip(),
            price,
            stock,
            v_category.get().strip(),
            v_status.get().strip(),
            v_image.get().strip(),
            v_desc.get("1.0", "end").strip(),
            pid
        ))
        self.conn.commit()
        self._set_status("Saved")
        dialog.destroy()
        self._load_data()
        if pid in self.image_cache:
            del self.image_cache[pid]

    def _delete_product(self, dialog, pid):
        if not messagebox.askyesno("Delete Product", "Are you sure you want to delete this product?"):
            return
        cur = self.conn.cursor()
        cur.execute("DELETE FROM products WHERE id=?", (pid,))
        self.conn.commit()
        self._set_status("Deleted")
        dialog.destroy()
        self._load_data()

    def _set_status(self, text):
        self.status_label.config(text=text)

if __name__ == "__main__":
    root = tk.Tk()
    app = ProductDashboard(root)
    root.mainloop()
