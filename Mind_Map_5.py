"""
Mind Map ©
==========
"A map is not the territory."

A CustomTkinter + pandas to-do / mind-map manager.

Views (tabs)
    List       sortable/filterable table with a smart-list sidebar + category
               check-boxes to show only chosen categories.
    Board      Kanban columns (Open / In Progress / Complete)
    Matrix     Eisenhower urgent x important quadrants
    Goals      items grouped by goal horizon (Short / Medium / Long-term)
    Values     free-form Core Values + First Principles (autosaved)
    Analytics  throughput, lead time, distributions (charts if matplotlib present)

Requirements:  pip install customtkinter pandas   (matplotlib optional, for charts)
Run:           python mind_map.py
"""

import os
import re
import json
import time
import shutil
import datetime as dt
import customtkinter as ctk
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
import pandas as pd

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
CSV_COLUMNS = ["ID", "Task", "Category", "Subcategory", "Tags", "Urgency",
               "Importance", "Horizon", "Motivation", "Status", "Start Date",
               "Due Date", "Date Created", "Date Completed", "Recurrence",
               "Estimate", "Actual", "Blocked By", "Subtasks", "Link", "Notes",
               "Archived"]
# "Task" is rendered in the tree's #0 column (so subtasks can nest beneath it);
# the remaining entries are ordinary data columns.
TREE_COLUMNS = ["Category", "Subcategory", "Tags", "Urgency", "Importance",
                "Horizon", "Motivation", "Status", "Due Date", "Progress", "Link"]
TREE_WIDTHS = {"Task": 210, "Category": 98, "Subcategory": 100, "Tags": 104,
               "Urgency": 68, "Importance": 78, "Horizon": 100, "Motivation": 96,
               "Status": 90, "Due Date": 94, "Progress": 70, "Link": 140}
STATUSES = ["Open", "In Progress", "Complete"]
RECURRENCES = ["", "daily", "weekly", "biweekly", "monthly"]
HORIZONS = ["", "Short-term", "Medium-term", "Long-term"]
# "Need to do" vs "fun to do": obligation vs intrinsic enjoyment.
# Rename these labels here if you'd prefer different wording.
MOTIVATIONS = ["", "Obligation", "Joy"]
SMART_LISTS = ["All", "Not Complete", "Today", "This Week", "Overdue",
               "In Progress", "High Priority", "Blocked", "No Date",
               "Completed", "Archived"]
ADD_NEW_CATEGORY = "➕ Add category…"
ADD_NEW_SUBCATEGORY = "➕ Add subcategory…"
UNCATEGORIZED = "Uncategorized"
DATE_FMT = "%Y-%m-%d"
DATE_INPUT_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y")
DATE_COLS = ("Start Date", "Due Date", "Date Created", "Date Completed")
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".mind_map.json")
# Files allowed when attaching a clickable document to an item.
FILE_TYPES = [("Documents", "*.doc *.docx *.txt *.odt"), ("All files", "*.*")]

# Urgency -> color, shared by main rows, board cards, and subtask rows.
URGENCY_COLORS = {1: "#ff6b6b", 2: "#ffa94d", 3: "#ffd43b", 4: "#a9e34b", 5: "#69db7c"}
# Dimmed variants used for completed subtasks so the urgency hue still reads.
URGENCY_COLORS_DIM = {1: "#9e5757", 2: "#9c6a44", 3: "#9c8a36", 4: "#6f8a44", 5: "#4f854f"}

# Colors for the Connections web when coloring by Motivation.
MOTIVATION_COLORS = {"Obligation": "#5c7cfa", "Joy": "#ffa94d", "": "#6b727d"}
# Distinct hues cycled through when the web is colored by Category.
CATEGORY_PALETTE = ["#4dabf7", "#ffa94d", "#69db7c", "#da77f2", "#ff8787",
                    "#3bc9db", "#ffd43b", "#a9e34b", "#f783ac", "#9775fa",
                    "#63e6be", "#ffc078"]

TEMPLATES = {
    "PLD sample growth": [
        {"Task": "Prepare substrate", "Urgency": 2},
        {"Task": "Pump down chamber", "Urgency": 2},
        {"Task": "Run deposition", "Urgency": 1},
        {"Task": "Cool down & vent", "Urgency": 3},
        {"Task": "Characterize (XRD/AFM)", "Urgency": 2},
        {"Task": "Log results", "Urgency": 3},
    ],
    "Weekly lab upkeep": [
        {"Task": "Check precursor levels", "Urgency": 3, "Recurrence": "weekly"},
        {"Task": "Back up instrument data", "Urgency": 2, "Recurrence": "weekly"},
        {"Task": "Tidy workspace", "Urgency": 4, "Recurrence": "weekly"},
    ],
}


# --------------------------------------------------------------------------- #
# Pure helpers (no GUI -> testable)
# --------------------------------------------------------------------------- #
def today():
    return dt.date.today()


def today_str():
    return today().strftime(DATE_FMT)


def coerce_rating(v, default=3):
    try:
        n = int(float(str(v).strip()))
    except (ValueError, TypeError):
        return default
    return max(1, min(5, n))


def coerce_horizon(v):
    s = str(v or "").strip().lower()
    return next((h for h in HORIZONS if h.lower() == s), "")


def coerce_motivation(v):
    s = str(v or "").strip().lower()
    return next((m for m in MOTIVATIONS if m.lower() == s), "")


def parse_date(s):
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in DATE_INPUT_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def valid_date(s):
    return not str(s or "").strip() or parse_date(s) is not None


def add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    # clamp day to month length
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.date(y, m, min(d.day, last))


def advance_date(date_str, recurrence):
    d = parse_date(date_str)
    if d is None or not recurrence:
        return date_str
    if recurrence == "daily":
        d += dt.timedelta(days=1)
    elif recurrence == "weekly":
        d += dt.timedelta(weeks=1)
    elif recurrence == "biweekly":
        d += dt.timedelta(weeks=2)
    elif recurrence == "monthly":
        d = add_months(d, 1)
    return d.strftime(DATE_FMT)


# --------------------------------------------------------------------------- #
# Subtask storage
# --------------------------------------------------------------------------- #
SUB_DEFAULTS = {"cat": "", "sub": "", "u": 3, "i": 3}
_SUB_FIELD_RE = re.compile(r"\|\s*([a-zA-Z]+)\s*=\s*([^|]*)")


def reset_subtasks(text):
    """Uncheck every subtask while preserving its category/urgency/etc."""
    items = parse_subtask_lines(text)
    for it in items:
        it["done"] = False
    return serialize_subtasks(items)


def subtasks_progress(text):
    items = parse_subtask_lines(text)
    if not items:
        return (0, 0)
    done = sum(1 for it in items if it["done"])
    return (done, len(items))


def progress_str(text):
    done, total = subtasks_progress(text)
    return f"{done}/{total}" if total else ""


def parse_subtask_lines(text):
    items = []
    for ln in str(text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        done = s.lower().startswith("[x]")
        m = re.match(r"^\[[ xX]\]\s*", s)
        body = s[m.end():] if m else s

        fields = dict(SUB_DEFAULTS)
        first_pipe = body.find("|")
        if first_pipe != -1:
            label = body[:first_pipe].strip()
            for key, val in _SUB_FIELD_RE.findall(body[first_pipe:]):
                key = key.lower()
                val = val.strip()
                if key in ("u", "i"):
                    fields[key] = coerce_rating(val)
                elif key in ("cat", "sub"):
                    fields[key] = val
        else:
            label = body.strip()

        items.append({"done": done, "text": label,
                      "cat": fields["cat"], "sub": fields["sub"],
                      "u": coerce_rating(fields["u"]),
                      "i": coerce_rating(fields["i"])})
    return items


def serialize_subtasks(items):
    out = []
    for it in items:
        txt = str(it.get("text", "")).strip()
        if not txt:
            continue
        parts = [f"[{'x' if it.get('done') else ' '}] {txt}"]
        cat = str(it.get("cat", "")).strip()
        sub = str(it.get("sub", "")).strip()
        u = coerce_rating(it.get("u", 3))
        i = coerce_rating(it.get("i", 3))
        if cat:
            parts.append(f"cat={cat}")
        if sub:
            parts.append(f"sub={sub}")
        if u != 3:
            parts.append(f"u={u}")
        if i != 3:
            parts.append(f"i={i}")
        out.append(" | ".join(parts))
    return "\n".join(out)


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_due_token(tok, base=None):
    base = base or today()
    tok = tok.strip().lower()
    if tok in ("today",):
        return base.strftime(DATE_FMT)
    if tok in ("tomorrow", "tmr"):
        return (base + dt.timedelta(days=1)).strftime(DATE_FMT)
    m = re.fullmatch(r"\+(\d+)d", tok)
    if m:
        return (base + dt.timedelta(days=int(m.group(1)))).strftime(DATE_FMT)
    for i, wd in enumerate(WEEKDAYS):
        if tok in (wd, wd[:3]):
            delta = (i - base.weekday()) % 7
            delta = delta or 7
            return (base + dt.timedelta(days=delta)).strftime(DATE_FMT)
    if parse_date(tok):
        return parse_date(tok).strftime(DATE_FMT)
    return None


def parse_quick_add(text, categories=None, base=None):
    """Parse 'fix XRD ~tomorrow !1 *2 #urgent @PLD' into task fields."""
    categories = categories or []
    out = {"Task": "", "Category": "", "Tags": [], "Urgency": None,
           "Importance": None, "Due Date": ""}
    tokens = str(text).split()
    keep = []
    for t in tokens:
        if re.fullmatch(r"!([1-5])", t):
            out["Urgency"] = int(t[1])
        elif re.fullmatch(r"\*([1-5])", t):
            out["Importance"] = int(t[1])
        elif t.startswith("#") and len(t) > 1:
            out["Tags"].append(t[1:])
        elif t.startswith("@") and len(t) > 1:
            name = t[1:]
            match = next((c for c in categories if c.lower() == name.lower()), name)
            out["Category"] = match
        elif t.startswith("~") and len(t) > 1:
            due = parse_due_token(t[1:], base)
            if due:
                out["Due Date"] = due
            else:
                keep.append(t)
        else:
            keep.append(t)
    out["Task"] = " ".join(keep).strip()
    out["Tags"] = ";".join(out["Tags"])
    return out


def _incomplete_id_set(df):
    return {int(i) for i, s in zip(df["ID"], df["Status"]) if s != "Complete"}


def is_blocked(row, df=None, incomplete=None):
    raw = str(row.get("Blocked By", "")).strip()
    if not raw:
        return False
    if incomplete is None:
        incomplete = _incomplete_id_set(df) if df is not None else set()
    for x in re.split(r"[;,]", raw):
        x = x.strip()
        if not x:
            continue
        try:
            bid = int(float(x))
        except ValueError:
            continue
        if bid in incomplete:
            return True
    return False


def smart_mask(df, name, base=None):
    base = base or today()
    if df.empty:
        return pd.Series([], dtype=bool)
    archived = df["Archived"].astype(str).str.lower().isin(["yes", "true", "1"])
    done = df["Status"] == "Complete"
    bts = pd.Timestamp(base)
    due = pd.to_datetime(df["Due Date"], errors="coerce").dt.normalize()
    start = pd.to_datetime(df["Start Date"], errors="coerce").dt.normalize()
    active = ~archived & ~done
    if name == "Archived":
        return archived
    if name == "Completed":
        return done & ~archived
    if name == "All":
        return ~archived
    if name == "Not Complete":
        return active
    if name == "Today":
        return active & ((due == bts) | (start == bts))
    if name == "This Week":
        end = bts + pd.Timedelta(days=7)
        return active & due.notna() & (due >= bts) & (due <= end)
    if name == "Overdue":
        return active & due.notna() & (due < bts)
    if name == "In Progress":
        return ~archived & (df["Status"] == "In Progress")
    if name == "High Priority":
        return active & ((df["Urgency"].map(coerce_rating) <= 2) |
                         (df["Importance"].map(coerce_rating) <= 2))
    if name == "No Date":
        return active & (df["Due Date"].astype(str).str.strip() == "")
    if name == "Blocked":
        inc = _incomplete_id_set(df)
        return active & df.apply(lambda r: is_blocked(r, incomplete=inc), axis=1)
    return ~archived


def filter_view(df, search="", categories=None, smart="All", base=None):
    if df.empty:
        return df
    view = df[smart_mask(df, smart, base)]
    # categories: None/empty -> all; "All" -> all; str -> one; iterable -> subset.
    if categories and categories != "All":
        if isinstance(categories, str):
            view = view[view["Category"] == categories]
        else:
            catset = set(categories)
            colcat = view["Category"].map(lambda s: s if str(s).strip() else UNCATEGORIZED)
            view = view[colcat.isin(catset)]
    q = str(search or "").strip().lower()
    if q:
        mask = pd.Series(False, index=view.index)
        for c in ("Task", "Category", "Subcategory", "Tags", "Notes", "Status"):
            mask |= view[c].astype(str).str.lower().str.contains(q, regex=False, na=False)
        view = view[mask]
    return view


def sort_view(view, col, ascending):
    if view.empty or not col:
        return view
    if col == "Progress":
        key = view["Subtasks"].map(lambda s: (subtasks_progress(s)[0] /
                                              subtasks_progress(s)[1]) if subtasks_progress(s)[1] else -1)
    elif col in ("Urgency", "Importance"):
        key = view[col].map(coerce_rating)
    elif col in DATE_COLS:
        key = pd.to_datetime(view[col], errors="coerce")
    else:
        key = view[col].astype(str).str.lower()
    return view.assign(_k=key).sort_values("_k", ascending=ascending,
                                           na_position="last").drop(columns="_k")


def normalize_frame(df):
    df = df.copy()
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[CSV_COLUMNS].fillna("")
    df["Urgency"] = df["Urgency"].map(coerce_rating)
    df["Importance"] = df["Importance"].map(coerce_rating)
    df["Horizon"] = df["Horizon"].map(coerce_horizon)
    df["Motivation"] = df["Motivation"].map(coerce_motivation)
    df["Status"] = df["Status"].map(
        lambda s: next((v for v in STATUSES if str(s).strip().lower() == v.lower()),
                       "Complete" if str(s).strip().lower().startswith("c") else "Open"))
    df["Date Created"] = df["Date Created"].map(lambda s: str(s).strip() or today_str())
    for c in ("Task", "Category", "Tags", "Due Date", "Start Date", "Date Completed",
              "Recurrence", "Estimate", "Actual", "Blocked By", "Subtasks", "Link", "Notes"):
        df[c] = df[c].map(lambda s: str(s).strip())
    df["Subcategory"] = df["Subcategory"].map(lambda s: str(s).strip() or UNCATEGORIZED)
    df["Archived"] = df["Archived"].map(
        lambda s: "Yes" if str(s).strip().lower() in ("yes", "true", "1") else "")
    # assign / repair IDs
    ids, seen, nxt = [], set(), 0
    for v in df["ID"]:
        try:
            i = int(float(v))
        except (ValueError, TypeError):
            i = None
        if i is None or i in seen:
            i = nxt
        seen.add(i)
        nxt = max(nxt, i) + 1
        ids.append(i)
    df["ID"] = ids
    return df.reset_index(drop=True)


def next_occurrence(task):
    nxt = dict(task)
    rec = task.get("Recurrence", "")
    nxt["Start Date"] = advance_date(task.get("Start Date", ""), rec)
    base_due = task.get("Due Date", "") or today_str()
    nxt["Due Date"] = advance_date(base_due, rec)
    nxt["Status"] = "Open"
    nxt["Date Created"] = today_str()
    nxt["Date Completed"] = ""
    nxt["Subtasks"] = reset_subtasks(task.get("Subtasks", ""))
    return nxt


def export_markdown(df):
    lines = [f"# Tasks (exported {today_str()})", ""]
    for cat, grp in df.groupby(df["Category"].replace("", UNCATEGORIZED)):
        lines.append(f"## {cat}")
        for _, r in grp.iterrows():
            box = "x" if r["Status"] == "Complete" else " "
            extra = []
            if str(r["Due Date"]).strip():
                extra.append(f"due {r['Due Date']}")
            extra.append(f"U{coerce_rating(r['Urgency'])}/I{coerce_rating(r['Importance'])}")
            lines.append(f"- [{box}] {r['Task']}  ({', '.join(extra)})")
        lines.append("")
    return "\n".join(lines)


def export_ics(df):
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MindMap//EN"]
    for _, r in df.iterrows():
        d = parse_date(r["Due Date"])
        if d is None:
            continue
        out += ["BEGIN:VEVENT", f"UID:task-{r['ID']}@mindmap",
                f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
                f"SUMMARY:{str(r['Task'])}",
                f"DESCRIPTION:{str(r['Notes']).replace(chr(10), ' ')}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\n".join(out)


def analytics(df):
    a = {"total": len(df)}
    active = df[df["Archived"] != "Yes"]
    a["open"] = int((active["Status"] == "Open").sum())
    a["in_progress"] = int((active["Status"] == "In Progress").sum())
    a["done"] = int((active["Status"] == "Complete").sum())
    a["archived"] = int((df["Archived"] == "Yes").sum())
    due = pd.to_datetime(active["Due Date"], errors="coerce")
    a["overdue"] = int(((active["Status"] != "Complete") & due.notna() &
                        (due < pd.Timestamp(today()))).sum())
    finished = a["done"] + a["open"] + a["in_progress"]
    a["completion_rate"] = (a["done"] / finished) if finished else 0.0
    comp = df[df["Status"] == "Complete"]
    leads = []
    for _, r in comp.iterrows():
        c1, c2 = parse_date(r["Date Created"]), parse_date(r["Date Completed"])
        if c1 and c2:
            leads.append((c2 - c1).days)
    a["avg_lead_days"] = (sum(leads) / len(leads)) if leads else None
    weeks = {}
    for _, r in comp.iterrows():
        c2 = parse_date(r["Date Completed"])
        if c2:
            wk = (today() - c2).days // 7
            if 0 <= wk < 4:
                weeks[wk] = weeks.get(wk, 0) + 1
    a["throughput"] = [weeks.get(i, 0) for i in range(4)]
    a["by_category"] = active["Category"].replace("", UNCATEGORIZED).value_counts().to_dict()
    a["by_urgency"] = active["Urgency"].map(coerce_rating).value_counts().sort_index().to_dict()
    ages = [(today() - parse_date(r["Date Created"])).days
            for _, r in active[active["Status"] != "Complete"].iterrows()
            if parse_date(r["Date Created"])]
    a["oldest_open_days"] = max(ages) if ages else 0
    return a


# --------------------------------------------------------------------------- #
# Splash / load page
# --------------------------------------------------------------------------- #
def show_splash(root):
    """Borderless start page: 'Mind Map ©' + 'A map is not the territory'."""
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg="#15171c")
    w, h = 560, 320
    sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
    splash.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    frame = tk.Frame(splash, bg="#15171c", highlightthickness=1,
                     highlightbackground="#2a2f3a")
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="Mind Map \u00a9", bg="#15171c", fg="#e8edf4",
             font=("Segoe UI Semibold", 42)).place(relx=0.5, rely=0.40, anchor="center")
    tk.Label(frame, text="But remember, a map is not the territory...", bg="#15171c", fg="#9aa0aa",
             font=("Segoe UI", 16, "italic")).place(relx=0.5, rely=0.60, anchor="center")
    try:
        splash.update()
    except Exception:  # noqa: BLE001
        pass
    return splash


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
class TaskManager:
    def __init__(self, root):
        self.root = root
        self.settings = self._load_settings()
        self.root.geometry(self.settings.get("geometry", "1320x820"))
        self.root.minsize(1040, 620)
        ctk.set_appearance_mode(self.settings.get("theme", "dark").lower())

        self.current_file = None
        self.dirty = False
        # Categories are NOT hard-coded — they come from the loaded CSV only.
        self.categories = []
        self.subcategories = [UNCATEGORIZED]
        self.smart = self.settings.get("smart", "All")
        self._sort_col, self._sort_asc = "Urgency", True
        self._subtasks_open = True
        self._undo, self._redo = [], []
        self._autosave_job = None
        self._last_backup_ts = 0.0
        # Global text/UI scale (the +/- buttons drive this). Remembered per run.
        self.ui_scale = float(self.settings.get("ui_scale", 1.0))
        try:
            ctk.set_widget_scaling(self.ui_scale)
        except Exception:  # noqa: BLE001
            pass

        self.df = normalize_frame(pd.DataFrame(columns=CSV_COLUMNS))

        self._style_tree()
        self._build_ui()

        last = self.settings.get("last_file")
        if last and os.path.exists(last):
            self._load_path(last)
        self._collect_categories()
        self.refresh_all()
        self._update_title()
        self.root.bind("<Control-plus>", lambda e: self._bump_text(0.1))
        self.root.bind("<Control-minus>", lambda e: self._bump_text(-0.1))
        self.root.bind("<Control-equal>", lambda e: self._bump_text(0.1))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        for seq, fn in (("<Control-s>", self.save_csv), ("<Control-o>", self.open_csv),
                        ("<Control-n>", self.new_file), ("<Control-z>", self.undo),
                        ("<Control-y>", self.redo), ("<Control-f>", self._focus_search)):
            self.root.bind(seq, lambda e, f=fn: f())

    # ---------- settings ---------- #
    def _load_settings(self):
        try:
            with open(SETTINGS_PATH) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}

    def _save_settings(self):
        self._values_job = None
        data = {"geometry": self.root.geometry(),
                "theme": ctk.get_appearance_mode(),
                "last_file": self.current_file, "smart": self.smart,
                "ui_scale": getattr(self, "ui_scale", 1.0)}
        # Core values / first principles live in settings so they persist
        # independent of which task file is open.
        if hasattr(self, "values_box"):
            try:
                data["core_values"] = self.values_box.get("1.0", "end").rstrip("\n")
            except Exception:  # noqa: BLE001
                pass
        if hasattr(self, "principles_box"):
            try:
                data["first_principles"] = self.principles_box.get("1.0", "end").rstrip("\n")
            except Exception:  # noqa: BLE001
                pass
        try:
            with open(SETTINGS_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:  # noqa: BLE001
            pass

    # ---------- ids / dirty / undo / autosave ---------- #
    def _next_id(self):
        return (int(self.df["ID"].max()) + 1) if len(self.df) else 0

    def _snapshot(self):
        self._undo.append((self.df.copy(deep=True), list(self.categories)))
        self._undo = self._undo[-40:]
        self._redo.clear()

    def undo(self):
        if not self._undo:
            return
        self._redo.append((self.df.copy(deep=True), list(self.categories)))
        self.df, self.categories = self._undo.pop()
        self._after_change()

    def redo(self):
        if not self._redo:
            return
        self._undo.append((self.df.copy(deep=True), list(self.categories)))
        self.df, self.categories = self._redo.pop()
        self._after_change()

    def _after_change(self):
        self._mark_dirty()
        self._refresh_category_widgets()
        self.refresh_all()

    def _mark_dirty(self, dirty=True):
        self.dirty = dirty
        self._update_title()
        if dirty:
            self._schedule_autosave()

    def _schedule_autosave(self):
        """Autosave after every change (debounced). Undo history is untouched."""
        if not self.current_file:
            return
        if self._autosave_job:
            try:
                self.root.after_cancel(self._autosave_job)
            except Exception:  # noqa: BLE001
                pass
        self._autosave_job = self.root.after(400, self._autosave)

    def _autosave(self):
        self._autosave_job = None
        if not self.current_file:
            return
        try:
            now = time.time()
            # Keep a timestamped backup at most once every 5 minutes so frequent
            # autosaves don't flood the backup folder.
            if now - self._last_backup_ts > 300:
                self._write_backup(self.current_file)
                self._last_backup_ts = now
            self.df[CSV_COLUMNS].to_csv(self.current_file, index=False)
            self.dirty = False
            self._update_title()
        except Exception:  # noqa: BLE001
            pass

    def _update_title(self):
        name = os.path.basename(self.current_file) if self.current_file else "untitled.csv"
        self.root.title(f"Mind Map © — {name}{' *' if self.dirty else ''}")

    # ---------- styling / text scaling ---------- #
    TREE_BASE_FONT = 11

    def _style_tree(self):
        size = max(7, round(self.TREE_BASE_FONT * getattr(self, "ui_scale", 1.0)))
        self.tree_font = tkfont.Font(family="Segoe UI", size=size)
        self.tree_head_font = tkfont.Font(family="Segoe UI Semibold", size=size)
        rowh = self.tree_font.metrics("linespace") + 14
        style = ttk.Style()
        self.ttk_style = style
        style.theme_use("clam")
        style.configure("Treeview", background="#242424", fieldbackground="#242424",
                        foreground="#dce4ee", rowheight=rowh, borderwidth=0,
                        font=self.tree_font)
        style.configure("Treeview.Heading", background="#1f6aa5", foreground="white",
                        relief="flat", font=self.tree_head_font)
        style.map("Treeview", background=[("selected", "#2a5d86")],
                  foreground=[("selected", "white")])
        style.map("Treeview.Heading", background=[("active", "#2785cf")])

    def _wf(self, size):
        """Scaled canvas font size (the web tab draws on a raw tk.Canvas)."""
        return max(6, int(round(size * getattr(self, "ui_scale", 1.0))))

    def _apply_tree_scale(self):
        if not hasattr(self, "tree_font"):
            return
        size = max(7, round(self.TREE_BASE_FONT * self.ui_scale))
        self.tree_font.configure(size=size)
        self.tree_head_font.configure(size=size)
        rowh = self.tree_font.metrics("linespace") + 14
        if hasattr(self, "ttk_style"):
            self.ttk_style.configure("Treeview", rowheight=rowh)

    def _bump_text(self, delta):
        """+ / - buttons: scale ALL text (CTk widgets, the table, and the web)."""
        self.ui_scale = round(min(2.2, max(0.7, self.ui_scale + delta)), 2)
        try:
            ctk.set_widget_scaling(self.ui_scale)   # scales every CTk widget + text
        except Exception:  # noqa: BLE001
            pass
        self._apply_tree_scale()                    # the ttk table isn't a CTk widget
        if hasattr(self, "web_canvas"):
            self.refresh_web()                      # redraw canvas text at new size
        if hasattr(self, "scale_lbl"):
            self.scale_lbl.configure(text=f"{int(self.ui_scale * 100)}%")

    # ---------- UI ---------- #
    def _build_ui(self):
        self._build_header()
        self._build_tabs()
        self.status_lbl = ctk.CTkLabel(self.root, text="", anchor="w")
        self.status_lbl.pack(fill="x", padx=16, pady=(0, 8))

    def _build_header(self):
        bar = ctk.CTkFrame(self.root)
        bar.pack(fill="x", padx=10, pady=(10, 4))
        for txt, cmd in (("New", self.new_file), ("Open", self.open_csv),
                         ("Save", self.save_csv), ("Save As", self.save_as)):
            ctk.CTkButton(bar, text=txt, width=64, command=cmd).pack(side="left", padx=3, pady=6)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8, pady=8)
        ctk.CTkButton(bar, text="↶ Undo", width=72, command=self.undo).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="↷ Redo", width=72, command=self.redo).pack(side="left", padx=3)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8, pady=8)
        ctk.CTkButton(bar, text="Add many…", width=88, command=self._add_many).pack(side="left", padx=3)
        self.template_var = tk.StringVar(value="Template…")
        ctk.CTkOptionMenu(bar, variable=self.template_var, width=150,
                          values=list(TEMPLATES.keys()),
                          command=self._insert_template).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="Export ▾", width=84, command=self._export_menu).pack(side="left", padx=3)

        ctk.CTkLabel(bar, text="Theme").pack(side="right", padx=(4, 4))
        ctk.CTkOptionMenu(bar, values=["Dark", "Light", "System"], width=96,
                          command=lambda m: ctk.set_appearance_mode(m.lower())
                          ).pack(side="right", padx=(0, 8))

        # Text-size controls: scale ALL text up/down for whichever monitor you're on.
        ttk.Separator(bar, orient="vertical").pack(side="right", fill="y", padx=8, pady=8)
        ctk.CTkButton(bar, text="A+", width=44,
                      command=lambda: self._bump_text(0.1)).pack(side="right", padx=(0, 6))
        self.scale_lbl = ctk.CTkLabel(bar, text=f"{int(self.ui_scale * 100)}%", width=42)
        self.scale_lbl.pack(side="right", padx=2)
        ctk.CTkButton(bar, text="A-", width=44,
                      command=lambda: self._bump_text(-0.1)).pack(side="right", padx=(0, 2))
        ctk.CTkLabel(bar, text="Text").pack(side="right", padx=(8, 4))

        q = ctk.CTkFrame(self.root)
        q.pack(fill="x", padx=10, pady=4)

        top = ctk.CTkFrame(q, fg_color="transparent")
        top.pack(fill="x")
        self.quick_var = tk.StringVar()
        e = ctk.CTkEntry(top, textvariable=self.quick_var,
                         placeholder_text="Quick add:  fix XRD ~tomorrow !1 *2 #urgent @PLD")
        e.pack(side="left", fill="x", expand=True, padx=(8, 6), pady=(8, 4))
        e.bind("<Return>", lambda ev: self._quick_add())
        ctk.CTkButton(top, text="Add Task", width=96,
                      command=self._quick_add).pack(side="left", padx=(4, 8), pady=(8, 4))

        sel = ctk.CTkFrame(q, fg_color="transparent")
        sel.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(sel, text="Category").pack(side="left", padx=(8, 4))
        self.qcat_var = tk.StringVar(value=UNCATEGORIZED)
        self.qcat_box = ctk.CTkComboBox(sel, width=140, variable=self.qcat_var,
                                        values=self._cat_values(),
                                        command=lambda v: self._on_pick_category(v, self.qcat_var))
        self.qcat_box.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(sel, text="Subcategory").pack(side="left", padx=(0, 4))
        self.qsub_var = tk.StringVar(value=UNCATEGORIZED)
        self.qsub_box = ctk.CTkComboBox(sel, width=140, variable=self.qsub_var,
                                        values=self._subcat_values(),
                                        command=lambda v: self._on_pick_subcategory(v, self.qsub_var))
        self.qsub_box.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(sel, text="Urgency").pack(side="left", padx=(0, 4))
        self.qurg_var = tk.StringVar(value="3")
        self.qurg_seg = ctk.CTkSegmentedButton(sel, values=["1", "2", "3", "4", "5"],
                                               variable=self.qurg_var)
        self.qurg_seg.pack(side="left", padx=(0, 10))
        self.qurg_seg.set("3")

        ctk.CTkLabel(sel, text="Importance").pack(side="left", padx=(0, 4))
        self.qimp_var = tk.StringVar(value="3")
        self.qimp_seg = ctk.CTkSegmentedButton(sel, values=["1", "2", "3", "4", "5"],
                                               variable=self.qimp_var)
        self.qimp_seg.pack(side="left", padx=(0, 8))
        self.qimp_seg.set("3")

    def _build_tabs(self):
        self.tabs = ctk.CTkTabview(self.root, command=self._on_tab_change)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(4, 4))
        for name in ("List", "Board", "Matrix", "Goals", "Values",
                     "Connections", "Analytics"):
            self.tabs.add(name)
        self._build_list_tab(self.tabs.tab("List"))
        self._build_board_tab(self.tabs.tab("Board"))
        self._build_matrix_tab(self.tabs.tab("Matrix"))
        self._build_goals_tab(self.tabs.tab("Goals"))
        self._build_values_tab(self.tabs.tab("Values"))
        self._build_web_tab(self.tabs.tab("Connections"))
        self._build_analytics_tab(self.tabs.tab("Analytics"))

    def _build_list_tab(self, tab):
        # sidebar: smart lists + category check-boxes
        side = ctk.CTkScrollableFrame(tab, width=170, label_text="Smart lists")
        side.pack(side="left", fill="y", padx=(0, 8), pady=4)
        self.smart_buttons = {}
        for name in SMART_LISTS:
            b = ctk.CTkButton(side, text=name, anchor="w",
                              command=lambda n=name: self._set_smart(n))
            b.pack(fill="x", pady=2)
            self.smart_buttons[name] = b

        # category check-box filter (show only the ticked categories)
        ctk.CTkLabel(side, text="Categories", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x", pady=(12, 2))
        ctk.CTkButton(side, text="Clear category filter", height=24,
                      fg_color="gray30", hover_color="gray40",
                      command=self._clear_category_filter).pack(fill="x", pady=(0, 4))
        self.cat_filter_holder = ctk.CTkFrame(side, fg_color="transparent")
        self.cat_filter_holder.pack(fill="x")
        self.cat_filter_vars = {}
        self._build_category_filter()

        right = ctk.CTkFrame(tab, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        flt = ctk.CTkFrame(right)
        flt.pack(fill="x", pady=(4, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._schedule_list_refresh())
        ctk.CTkLabel(flt, text="Search").pack(side="left", padx=(8, 4))
        self.search_entry = ctk.CTkEntry(flt, textvariable=self.search_var, width=240,
                                         placeholder_text="title, tags, notes…")
        self.search_entry.pack(side="left", padx=4)
        ctk.CTkButton(flt, text="Edit", width=56, command=self.edit_selected).pack(side="left", padx=(14, 3))
        ctk.CTkButton(flt, text="Bulk edit", width=78, command=self._bulk_edit).pack(side="left", padx=3)
        ctk.CTkButton(flt, text="Complete", width=80, command=lambda: self._bulk_status("Complete")).pack(side="left", padx=3)
        ctk.CTkButton(flt, text="✓ Sub", width=64, fg_color="#2f7d4f",
                      hover_color="#37925c",
                      command=lambda: self._set_selected_subtasks_done(True)
                      ).pack(side="left", padx=(8, 1))
        ctk.CTkButton(flt, text="↺ Sub", width=64, fg_color="gray30",
                      hover_color="gray40",
                      command=lambda: self._set_selected_subtasks_done(False)
                      ).pack(side="left", padx=(1, 3))
        ctk.CTkButton(flt, text="Archive", width=70, command=self._bulk_archive).pack(side="left", padx=3)
        ctk.CTkButton(flt, text="Delete", width=64, fg_color="#a33", hover_color="#c44",
                      command=self._bulk_delete).pack(side="left", padx=3)
        self.subtask_toggle_btn = ctk.CTkButton(flt, text="Collapse all", width=96,
                                                command=self._toggle_subtasks)
        self.subtask_toggle_btn.pack(side="left", padx=(14, 3))

        tf = tk.Frame(right, bg="#242424")
        tf.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tf, columns=TREE_COLUMNS, show="tree headings",
                                 selectmode="extended")
        self.tree.heading("#0", text="Task", command=lambda: self._sort_column("Task"))
        self.tree.column("#0", width=TREE_WIDTHS["Task"], anchor="w", stretch=True)
        for c in TREE_COLUMNS:
            self.tree.heading(c, text=c, command=lambda cc=c: self._sort_column(cc))
            anchor = "w" if c in ("Tags", "Category", "Subcategory", "Link") else "center"
            self.tree.column(c, width=TREE_WIDTHS[c], anchor=anchor,
                             stretch=(c == "Tags"))
        # vertical + horizontal scrollbars (Horizon column can push width past view)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        for u, col in URGENCY_COLORS.items():
            self.tree.tag_configure(f"u{u}", foreground=col)
        for u, col in URGENCY_COLORS.items():
            self.tree.tag_configure(f"su{u}", foreground=col)
        for u, col in URGENCY_COLORS_DIM.items():
            self.tree.tag_configure(f"su{u}_done", foreground=col)
        self.tree.tag_configure("done", foreground="#6c757d")
        self.tree.tag_configure("overdue", background="#4a2530", foreground="#ff8787")
        self.tree.tag_configure("blocked", foreground="#9aa0aa")
        self.tree.tag_configure("subtask", foreground="#aab2bd")
        self.tree.tag_configure("subtask_done", foreground="#5c636a")
        self.tree.bind("<Double-1>", self._on_tree_double)
        self.tree.bind("<Delete>", lambda e: self._bulk_delete())

    def _build_category_filter(self):
        """(Re)build the category check-boxes; keeps previously-ticked state."""
        if not hasattr(self, "cat_filter_holder"):
            return
        for w in self.cat_filter_holder.winfo_children():
            w.destroy()
        cats = sorted(set(self.categories) | {UNCATEGORIZED})
        new_vars = {}
        for c in cats:
            var = self.cat_filter_vars.get(c) or tk.BooleanVar(value=False)
            new_vars[c] = var
            ctk.CTkCheckBox(self.cat_filter_holder, text=c, variable=var,
                            checkbox_width=18, checkbox_height=18,
                            command=self.refresh_list).pack(fill="x", pady=1)
        self.cat_filter_vars = new_vars

    def _clear_category_filter(self):
        for v in getattr(self, "cat_filter_vars", {}).values():
            v.set(False)
        self.refresh_list()

    def _build_board_tab(self, tab):
        self.board = ctk.CTkFrame(tab, fg_color="transparent")
        self.board.pack(fill="both", expand=True)
        self.board_cols = {}
        for st in STATUSES:
            col = ctk.CTkScrollableFrame(self.board, label_text=st)
            col.pack(side="left", fill="both", expand=True, padx=6, pady=4)
            self.board_cols[st] = col

    def _build_matrix_tab(self, tab):
        self.matrix = ctk.CTkFrame(tab, fg_color="transparent")
        self.matrix.pack(fill="both", expand=True)
        titles = ["Q1 · Urgent & Important (do now)",
                  "Q2 · Important, not urgent (schedule)",
                  "Q3 · Urgent, not important (delegate/quick)",
                  "Q4 · Neither (drop?)"]
        self.matrix_cells = []
        for i, t in enumerate(titles):
            cell = ctk.CTkScrollableFrame(self.matrix, label_text=t)
            cell.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            self.matrix_cells.append(cell)
        self.matrix.grid_rowconfigure((0, 1), weight=1)
        self.matrix.grid_columnconfigure((0, 1), weight=1)

    def _build_goals_tab(self, tab):
        # Items grouped by their goal horizon (uses the new Horizon column).
        self.goals = ctk.CTkFrame(tab, fg_color="transparent")
        self.goals.pack(fill="both", expand=True)
        self.goal_cols = {}
        for h in ("Short-term", "Medium-term", "Long-term"):
            col = ctk.CTkScrollableFrame(self.goals, label_text=h + " goals")
            col.pack(side="left", fill="both", expand=True, padx=6, pady=4)
            self.goal_cols[h] = col

    def _build_values_tab(self, tab):
        wrap = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        ctk.CTkLabel(wrap, text="Core values", anchor="w",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(wrap, text="What matters most — the principles you want to steer by.",
                     anchor="w", text_color="#9aa0aa").pack(fill="x", pady=(0, 4))
        self.values_box = ctk.CTkTextbox(wrap, height=230)
        self.values_box.pack(fill="both", expand=True, pady=(0, 12))

        ctk.CTkLabel(wrap, text="First principles", anchor="w",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(wrap, text="The foundational truths you reason up from.",
                     anchor="w", text_color="#9aa0aa").pack(fill="x", pady=(0, 4))
        self.principles_box = ctk.CTkTextbox(wrap, height=230)
        self.principles_box.pack(fill="both", expand=True, pady=(0, 6))

        self.values_box.insert("1.0", self.settings.get("core_values", ""))
        self.principles_box.insert("1.0", self.settings.get("first_principles", ""))
        self._values_job = None
        self.values_box.bind("<KeyRelease>", lambda e: self._schedule_values_save())
        self.principles_box.bind("<KeyRelease>", lambda e: self._schedule_values_save())

    def _schedule_values_save(self):
        if getattr(self, "_values_job", None):
            try:
                self.root.after_cancel(self._values_job)
            except Exception:  # noqa: BLE001
                pass
        self._values_job = self.root.after(600, self._save_settings)

    # ---------- Connections (category <-> subcategory web) ---------- #
    def _build_web_tab(self, tab):
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 2))
        ctk.CTkLabel(top, text="Color nodes by").pack(side="left", padx=(4, 6))
        self.web_color_var = tk.StringVar(value="Urgency")
        seg = ctk.CTkSegmentedButton(
            top, values=["Urgency", "Motivation", "Category"],
            variable=self.web_color_var, command=lambda v: self.refresh_web())
        seg.pack(side="left")
        seg.set("Urgency")
        ctk.CTkLabel(top, text="   •   node size = number of tasks   •   "
                              "click a category to filter the List",
                     text_color="#9aa0aa").pack(side="left", padx=8)
        # Plain tk.Canvas so the web needs no extra libraries.
        self.web_canvas = tk.Canvas(tab, bg="#1b1d22", highlightthickness=0)
        self.web_canvas.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self._web_nodes = []   # (x, y, r, kind, name) for click hit-testing
        self.web_canvas.bind("<Configure>", lambda e: self.refresh_web())
        self.web_canvas.bind("<Button-1>", self._on_web_click)

    def _web_structure(self):
        """category -> {count, urg[], mot{}, subs{sub: {count, urg[], mot{}}}}."""
        active = self.df[self.df["Archived"] != "Yes"]
        struct = {}
        for _, r in active.iterrows():
            cat = str(r["Category"]).strip() or UNCATEGORIZED
            sub = str(r["Subcategory"]).strip() or UNCATEGORIZED
            mot = coerce_motivation(r["Motivation"])
            urg = coerce_rating(r["Urgency"])
            d = struct.setdefault(cat, {"count": 0, "urg": [], "mot": {},
                                        "subs": {}})
            d["count"] += 1
            d["urg"].append(urg)
            d["mot"][mot] = d["mot"].get(mot, 0) + 1
            s = d["subs"].setdefault(sub, {"count": 0, "urg": [], "mot": {}})
            s["count"] += 1
            s["urg"].append(urg)
            s["mot"][mot] = s["mot"].get(mot, 0) + 1
        return struct

    def _node_color(self, info, mode, cat_color=None):
        if mode == "Category" and cat_color:
            return cat_color
        if mode == "Motivation":
            mot = info.get("mot", {})
            obl = mot.get("Obligation", 0)
            joy = mot.get("Joy", 0)
            if obl == 0 and joy == 0:
                return MOTIVATION_COLORS[""]
            return MOTIVATION_COLORS["Obligation" if obl >= joy else "Joy"]
        # default: Urgency (average -> nearest band)
        urg = info.get("urg", [])
        avg = round(sum(urg) / len(urg)) if urg else 3
        return URGENCY_COLORS.get(max(1, min(5, avg)), "#ffd43b")

    def refresh_web(self):
        if not hasattr(self, "web_canvas"):
            return
        import math
        cv = self.web_canvas
        cv.delete("all")
        self._web_nodes = []
        w = cv.winfo_width()
        h = cv.winfo_height()
        if w < 60 or h < 60:           # not laid out yet; try again shortly
            self.root.after(80, self.refresh_web)
            return

        mode = self.web_color_var.get() if hasattr(self, "web_color_var") else "Urgency"
        struct = self._web_structure()
        cx, cy = w / 2, h / 2

        if not struct:
            cv.create_text(cx, cy, fill="#80868f", font=("Segoe UI", self._wf(14)),
                           text="No tasks yet — add some, set their Category and\n"
                                "Subcategory, and your map of connections appears here.")
            return

        total = sum(d["count"] for d in struct.values())
        max_count = max([d["count"] for d in struct.values()] +
                        [sc["count"] for d in struct.values()
                         for sc in d["subs"].values()] + [1])

        def radius(count):
            return 9 + 22 * math.sqrt(count / max_count)

        cats = sorted(struct.items(), key=lambda kv: -kv[1]["count"])
        n = len(cats)
        R1 = min(w, h) * 0.30          # category ring radius
        R2 = min(w, h) * 0.155         # subcategory offset from its category

        # ----- edges & nodes ----- #
        cat_color_map = {c: CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)]
                         for i, (c, _) in enumerate(cats)}

        positions = {}
        for i, (cat, info) in enumerate(cats):
            ang = (2 * math.pi * i / n) - math.pi / 2
            x = cx + R1 * math.cos(ang)
            y = cy + R1 * math.sin(ang)
            positions[cat] = (x, y, ang)

        # center -> category links first (drawn under everything)
        for cat, (x, y, ang) in positions.items():
            cv.create_line(cx, cy, x, y, fill="#3a3f4a", width=2)

        # subcategory links + nodes
        for cat, (x, y, ang) in positions.items():
            info = struct[cat]
            subs = sorted(info["subs"].items(), key=lambda kv: -kv[1]["count"])
            m = len(subs)
            spread = math.radians(150)     # fan the subs outward from the hub
            base = ang
            for j, (sub, sinfo) in enumerate(subs):
                off = 0 if m == 1 else (spread * (j / (m - 1)) - spread / 2)
                sang = base + off
                sx = x + R2 * math.cos(sang)
                sy = y + R2 * math.sin(sang)
                cv.create_line(x, y, sx, sy, fill="#30343d", width=1)
                sc = self._node_color(sinfo, mode,
                                      cat_color_map[cat] if mode == "Category" else None)
                sr = radius(sinfo["count"]) * 0.8
                cv.create_oval(sx - sr, sy - sr, sx + sr, sy + sr,
                               fill=sc, outline="#15171c", width=1)
                self._web_nodes.append((sx, sy, sr, "sub", sub))
                cv.create_text(sx, sy + sr + 9, fill="#c7ccd4",
                               font=("Segoe UI", self._wf(8)),
                               text=f"{sub} ({sinfo['count']})")

        # category nodes on top of their sub links
        for cat, (x, y, ang) in positions.items():
            info = struct[cat]
            color = self._node_color(info, mode,
                                     cat_color_map[cat] if mode == "Category" else None)
            r = radius(info["count"]) + 4
            cv.create_oval(x - r, y - r, x + r, y + r, fill=color,
                           outline="#0e0f12", width=2)
            self._web_nodes.append((x, y, r, "cat", cat))
            cv.create_text(x, y - r - 11, fill="#f1f3f5",
                           font=("Segoe UI", self._wf(10), "bold"),
                           text=f"{cat} ({info['count']})")

        # center hub
        cr = 26
        cv.create_oval(cx - cr, cy - cr, cx + cr, cy + cr,
                       fill="#2b2f37", outline="#4b5563", width=2)
        cv.create_text(cx, cy, fill="#e8edf4", font=("Segoe UI", self._wf(9), "bold"),
                       text=f"All\n{total}")

        self._draw_web_legend(cv, mode, w, h)

    def _draw_web_legend(self, cv, mode, w, h):
        x0, y0 = 14, 14
        cv.create_text(x0, y0, anchor="nw", fill="#9aa0aa",
                       font=("Segoe UI", self._wf(9), "bold"), text=f"Color: {mode}")
        if mode == "Urgency":
            items = [(URGENCY_COLORS[u], f"U{u}") for u in (1, 3, 5)]
            labels = ["1 = most urgent", "", "5 = least"]
        elif mode == "Motivation":
            items = [(MOTIVATION_COLORS["Obligation"], "Obligation (need-to-do)"),
                     (MOTIVATION_COLORS["Joy"], "Joy (fun-to-do)"),
                     (MOTIVATION_COLORS[""], "unset")]
            labels = ["", "", ""]
        else:
            cv.create_text(x0, y0 + 18, anchor="nw", fill="#80868f",
                           font=("Segoe UI", self._wf(8)),
                           text="each category a distinct hue")
            return
        yy = y0 + 20
        for (color, lab), extra in zip(items, labels):
            cv.create_oval(x0, yy, x0 + 12, yy + 12, fill=color, outline="")
            txt = lab + (f"   {extra}" if extra else "")
            cv.create_text(x0 + 18, yy + 6, anchor="w", fill="#9aa0aa",
                           font=("Segoe UI", self._wf(8)), text=txt)
            yy += 18

    def _on_web_click(self, event):
        # Nearest node within its radius wins. Category -> filter List by it;
        # subcategory -> search the List for it.
        for (x, y, r, kind, name) in reversed(self._web_nodes):
            if (event.x - x) ** 2 + (event.y - y) ** 2 <= (r + 3) ** 2:
                if kind == "cat":
                    for c, var in getattr(self, "cat_filter_vars", {}).items():
                        var.set(c == name)
                    try:
                        self.tabs.set("List")
                    except Exception:  # noqa: BLE001
                        pass
                    self.refresh_list()
                else:
                    self.search_var.set(name)
                    try:
                        self.tabs.set("List")
                    except Exception:  # noqa: BLE001
                        pass
                return

    def _build_analytics_tab(self, tab):
        self.analytics_text = ctk.CTkTextbox(tab, height=160)
        self.analytics_text.pack(fill="x", padx=8, pady=8)
        self.analytics_chart = ctk.CTkFrame(tab, fg_color="transparent")
        self.analytics_chart.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ---------- category dropdown (add-new lives inside) ---------- #
    def _cat_values(self):
        # Only categories present in the data, plus Uncategorized + the add option.
        cats = sorted(set(self.categories) | {UNCATEGORIZED})
        return cats + [ADD_NEW_CATEGORY]

    def _on_pick_category(self, value, var):
        if value == ADD_NEW_CATEGORY:
            new = self._prompt_new_category()
            var.set(new or UNCATEGORIZED)

    def _prompt_new_category(self):
        dlg = ctk.CTkInputDialog(text="New category name:", title="Add Category")
        name = (dlg.get_input() or "").strip()
        if name and name not in self.categories:
            self.categories.append(name)
            self.categories.sort()
            self._refresh_category_widgets()
        return name

    def _collect_categories(self):
        # Derived ONLY from the data — nothing hard-coded is kept.
        cats = {c for c in self.df["Category"].tolist() if str(c).strip()}
        self.categories = sorted(cats)
        self._refresh_category_widgets()

    def _subcategories(self):
        subs = {UNCATEGORIZED}
        subs.update(getattr(self, "subcategories", []))
        if "Subcategory" in self.df.columns:
            subs.update(s for s in self.df["Subcategory"].tolist() if str(s).strip())
        return sorted(subs)

    def _subcat_values(self):
        return self._subcategories() + [ADD_NEW_SUBCATEGORY]

    def _on_pick_subcategory(self, value, var):
        if value == ADD_NEW_SUBCATEGORY:
            new = self._prompt_new_subcategory()
            var.set(new or UNCATEGORIZED)

    def _prompt_new_subcategory(self):
        dlg = ctk.CTkInputDialog(text="New subcategory name:", title="Add Subcategory")
        name = (dlg.get_input() or "").strip()
        if name and name not in self.subcategories:
            self.subcategories.append(name)
            self.subcategories.sort()
        return name

    def _refresh_category_widgets(self):
        if hasattr(self, "qcat_box"):
            self.qcat_box.configure(values=self._cat_values())
        if hasattr(self, "qsub_box"):
            self.qsub_box.configure(values=self._subcat_values())
        self._build_category_filter()

    # ---------- adding tasks ---------- #
    def _new_task(self, **kw):
        row = {c: "" for c in CSV_COLUMNS}
        row.update({"ID": self._next_id(), "Urgency": 3, "Importance": 3,
                    "Status": "Open", "Category": UNCATEGORIZED,
                    "Subcategory": UNCATEGORIZED, "Horizon": "", "Motivation": "",
                    "Date Created": today_str(), "Archived": ""})
        row.update(kw)
        row["Urgency"] = coerce_rating(row["Urgency"])
        row["Importance"] = coerce_rating(row["Importance"])
        row["Horizon"] = coerce_horizon(row.get("Horizon", ""))
        row["Motivation"] = coerce_motivation(row.get("Motivation", ""))
        row["Category"] = str(row.get("Category", "")).strip() or UNCATEGORIZED
        row["Subcategory"] = str(row.get("Subcategory", "")).strip() or UNCATEGORIZED
        return row

    def _append(self, row):
        self.df.loc[len(self.df)] = row

    def _quick_add(self):
        text = self.quick_var.get().strip()
        if not text:
            return
        self._snapshot()
        parsed = parse_quick_add(text, self.categories)
        if not parsed["Task"]:
            parsed["Task"] = text
        row = self._new_task(
            Task=parsed["Task"],
            Category=parsed["Category"] or self.qcat_var.get().strip() or UNCATEGORIZED,
            Subcategory=self.qsub_var.get().strip() or UNCATEGORIZED,
            Tags=parsed["Tags"],
            Urgency=parsed["Urgency"] if parsed["Urgency"] else self.qurg_var.get(),
            Importance=parsed["Importance"] if parsed["Importance"] else self.qimp_var.get(),
            **{"Due Date": parsed["Due Date"]})
        self._append(row)
        self.quick_var.set("")
        # Don't keep the last picks lingering — reset to Uncategorized.
        self.qcat_var.set(UNCATEGORIZED)
        self.qsub_var.set(UNCATEGORIZED)
        self._mark_dirty()
        self._collect_categories()
        self.refresh_all()

    def _add_many(self):
        win = ctk.CTkToplevel(self.root)
        win.title("Add many tasks")
        win.geometry("680x620")
        win.minsize(540, 520)
        win.transient(self.root)
        win.after(120, win.grab_set)

        ctk.CTkLabel(
            win, justify="left",
            text="Paste one task per line. Tokens on a line override the defaults:\n"
                 "   ~date (today / tomorrow / +3d / mon / 2026-06-30)   "
                 "!urgency   *importance   #tag   @Category"
        ).pack(anchor="w", padx=14, pady=(12, 6))

        dflt = ctk.CTkFrame(win)
        dflt.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(dflt, text="Defaults for all pasted tasks").grid(
            row=0, column=0, columnspan=6, sticky="w", padx=8, pady=(8, 2))

        # New tasks default to Uncategorized unless explicitly changed here.
        cat_var = tk.StringVar(value=UNCATEGORIZED)
        sub_var = tk.StringVar(value=UNCATEGORIZED)
        urg_var = tk.StringVar(value="3")
        imp_var = tk.StringVar(value="3")
        st_var = tk.StringVar(value="Open")
        rec_var = tk.StringVar(value="")
        hz_var = tk.StringVar(value="")
        mot_var = tk.StringVar(value="")
        due_var = tk.StringVar(value="")
        tag_var = tk.StringVar(value="")

        def lab(text, r, c):
            ctk.CTkLabel(dflt, text=text).grid(row=r, column=c, sticky="e", padx=(8, 4), pady=4)

        lab("Category", 1, 0)
        ctk.CTkComboBox(dflt, values=self._cat_values(), variable=cat_var, width=150,
                        command=lambda v: self._on_pick_category(v, cat_var)
                        ).grid(row=1, column=1, sticky="w", padx=4)
        lab("Urgency", 1, 2)
        ctk.CTkComboBox(dflt, values=["1", "2", "3", "4", "5"], variable=urg_var,
                        width=70).grid(row=1, column=3, sticky="w", padx=4)
        lab("Importance", 1, 4)
        ctk.CTkComboBox(dflt, values=["1", "2", "3", "4", "5"], variable=imp_var,
                        width=70).grid(row=1, column=5, sticky="w", padx=4)
        lab("Subcategory", 2, 0)
        ctk.CTkComboBox(dflt, values=self._subcat_values(), variable=sub_var, width=150,
                        command=lambda v: self._on_pick_subcategory(v, sub_var)
                        ).grid(row=2, column=1, sticky="w", padx=4)
        lab("Status", 2, 2)
        ctk.CTkComboBox(dflt, values=STATUSES, variable=st_var, width=110
                        ).grid(row=2, column=3, sticky="w", padx=4)
        lab("Recurrence", 2, 4)
        ctk.CTkComboBox(dflt, values=RECURRENCES, variable=rec_var, width=110
                        ).grid(row=2, column=5, sticky="w", padx=4)
        lab("Due Date", 3, 0)
        ctk.CTkEntry(dflt, textvariable=due_var, width=150, placeholder_text="YYYY-MM-DD"
                     ).grid(row=3, column=1, sticky="w", padx=4)
        lab("Goal horizon", 3, 2)
        ctk.CTkComboBox(dflt, values=HORIZONS, variable=hz_var, width=130
                        ).grid(row=3, column=3, sticky="w", padx=4)
        lab("Motivation", 3, 4)
        ctk.CTkComboBox(dflt, values=MOTIVATIONS, variable=mot_var, width=130
                        ).grid(row=3, column=5, sticky="w", padx=4)
        lab("Tags", 4, 0)
        ctk.CTkEntry(dflt, textvariable=tag_var, placeholder_text="semicolon;separated"
                     ).grid(row=4, column=1, columnspan=5, sticky="we", padx=4, pady=(0, 8))
        dflt.grid_columnconfigure(5, weight=1)

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=14, pady=12)
        box = ctk.CTkTextbox(win)
        box.pack(fill="both", expand=True, padx=14, pady=(0, 4))

        def add():
            lines = [l.strip() for l in box.get("1.0", "end").splitlines() if l.strip()]
            if not lines:
                win.destroy(); return
            if not valid_date(due_var.get()):
                messagebox.showwarning("Add many",
                                       "Default Due Date must be YYYY-MM-DD or blank.",
                                       parent=win)
                return
            self._snapshot()
            for ln in lines:
                p = parse_quick_add(ln, self.categories)
                kw = dict(
                    Task=p["Task"] or ln,
                    Category=p["Category"] or cat_var.get().strip() or UNCATEGORIZED,
                    Subcategory=sub_var.get().strip() or UNCATEGORIZED,
                    Tags=p["Tags"] or tag_var.get().strip(),
                    Urgency=p["Urgency"] if p["Urgency"] else urg_var.get(),
                    Importance=p["Importance"] if p["Importance"] else imp_var.get(),
                    Status=st_var.get(),
                    Recurrence=rec_var.get().strip(),
                    Horizon=hz_var.get().strip(),
                    Motivation=mot_var.get().strip(),
                )
                kw["Due Date"] = p["Due Date"] or due_var.get().strip()
                if st_var.get() == "Complete":
                    kw["Date Completed"] = today_str()
                self._append(self._new_task(**kw))
            self._mark_dirty(); self._collect_categories(); self.refresh_all()
            win.destroy()

        ctk.CTkButton(btns, text="Cancel", fg_color="gray30", hover_color="gray40",
                      command=win.destroy).pack(side="right")
        ctk.CTkButton(btns, text="Add tasks", command=add).pack(side="right", padx=8)
        win.bind("<Escape>", lambda e: win.destroy())

    def _insert_template(self, name):
        self.template_var.set("Template…")
        items = TEMPLATES.get(name)
        if not items:
            return
        self._snapshot()
        for it in items:
            # No hard-coded category: template items default to Uncategorized.
            self._append(self._new_task(**it))
        self._mark_dirty(); self._collect_categories(); self.refresh_all()

    # ---------- files ---------- #
    def open_csv(self):
        if not self._maybe_save():
            return
        path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if path:
            self._load_path(path)
            self._collect_categories()
            self.refresh_all()

    def _load_path(self, path):
        try:
            raw = pd.read_csv(path, dtype=str, keep_default_na=False)
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Open", f"Could not read file:\n{ex}")
            return
        self.df = normalize_frame(raw)
        self.current_file = path
        self._last_backup_ts = 0.0
        self._mark_dirty(False)

    def save_csv(self):
        if self.current_file is None:
            return self.save_as()
        try:
            self._write_backup(self.current_file)
            self._last_backup_ts = time.time()
            self.df[CSV_COLUMNS].to_csv(self.current_file, index=False)
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Save", f"Could not save file:\n{ex}")
            return False
        self._mark_dirty(False)
        return True

    def save_as(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV Files", "*.csv")])
        if not path:
            return False
        self.current_file = path
        return self.save_csv()

    def _write_backup(self, path):
        if not os.path.exists(path):
            return
        d = os.path.join(os.path.dirname(path) or ".", ".task_backups")
        os.makedirs(d, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        base = os.path.basename(path)
        shutil.copy2(path, os.path.join(d, f"{base}.{stamp}.bak.csv"))
        backups = sorted(f for f in os.listdir(d) if f.startswith(base))
        for old in backups[:-10]:
            try:
                os.remove(os.path.join(d, old))
            except OSError:
                pass

    def new_file(self):
        if not self._maybe_save():
            return
        self._snapshot()
        self.df = normalize_frame(pd.DataFrame(columns=CSV_COLUMNS))
        self.current_file = None
        self._collect_categories()
        self._mark_dirty(False)
        self.refresh_all()

    def _maybe_save(self):
        if not self.dirty:
            return True
        ans = messagebox.askyesnocancel("Unsaved changes", "Save changes first?")
        if ans is None:
            return False
        return self.save_csv() if ans else True

    def _export_menu(self):
        win = ctk.CTkToplevel(self.root)
        win.title("Export")
        win.geometry("320x180")
        win.transient(self.root)
        win.after(120, win.grab_set)
        ctk.CTkLabel(win, text="Export the current list").pack(pady=(16, 8))
        ctk.CTkButton(win, text="Markdown checklist (.md)",
                      command=lambda: self._do_export("md", win)).pack(pady=4)
        ctk.CTkButton(win, text="Calendar / due dates (.ics)",
                      command=lambda: self._do_export("ics", win)).pack(pady=4)

    def _do_export(self, kind, win):
        win.destroy()
        if kind == "md":
            path = filedialog.asksaveasfilename(defaultextension=".md",
                                                filetypes=[("Markdown", "*.md")])
            text = export_markdown(self.df)
        else:
            path = filedialog.asksaveasfilename(defaultextension=".ics",
                                                filetypes=[("iCalendar", "*.ics")])
            text = export_ics(self.df)
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        messagebox.showinfo("Export", f"Saved to {os.path.basename(path)}")

    def _on_close(self):
        if self._maybe_save():
            self._save_settings()
            self.root.destroy()

    # ---------- smart lists / filters ---------- #
    def _set_smart(self, name):
        self.smart = name
        self.refresh_list()

    def _set_appearance_buttons(self):
        for n, b in self.smart_buttons.items():
            b.configure(fg_color=("#1f6aa5" if n == self.smart else "gray25"))

    def _focus_search(self):
        try:
            self.tabs.set("List")
            self.search_entry.focus_set()
        except Exception:  # noqa: BLE001
            pass

    # ---------- selection / bulk ---------- #
    def _selected_ids(self):
        return [int(i) for i in self.tree.selection() if str(i).isdigit()]

    def _bulk_status(self, status):
        ids = self._selected_ids()
        if not ids:
            return
        self._snapshot()
        for _id in ids:
            self._apply_status(_id, status, snapshot=False)
        self._mark_dirty(); self.refresh_all()

    def _apply_status(self, _id, status, snapshot=True):
        if snapshot:
            self._snapshot()
        mask = self.df["ID"] == _id
        if not mask.any():
            return
        task = self.df[mask].iloc[0].to_dict()
        self.df.loc[mask, "Status"] = status
        if status == "Complete":
            self.df.loc[mask, "Date Completed"] = today_str()
            if str(task.get("Recurrence", "")).strip():
                nxt = next_occurrence(task)
                nxt["ID"] = self._next_id()
                self._append(nxt)
        else:
            self.df.loc[mask, "Date Completed"] = ""
        if snapshot:
            self._mark_dirty(); self.refresh_all()

    def _bulk_edit(self):
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Bulk edit", "Select one or more tasks first "
                                             "(Ctrl/Shift-click to multi-select).")
            return
        win = ctk.CTkToplevel(self.root)
        win.title(f"Bulk edit — {len(ids)} task(s)")
        win.geometry("460x520")
        win.minsize(420, 440)
        win.transient(self.root)
        win.after(120, win.grab_set)

        ctk.CTkLabel(win, text=f"Apply to {len(ids)} selected task(s).\n"
                               "Tick a field to change it; unticked fields are left as-is.",
                     justify="left").pack(anchor="w", padx=16, pady=(14, 4))

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=16, pady=12)
        form = ctk.CTkScrollableFrame(win)
        form.pack(side="top", fill="both", expand=True, padx=12, pady=(6, 0))

        rows = {}

        def add_row(field, make_widget, var):
            en = tk.BooleanVar(value=False)
            fr = ctk.CTkFrame(form, fg_color="transparent")
            fr.pack(fill="x", pady=5)
            ctk.CTkCheckBox(fr, text=field, variable=en, width=150).pack(side="left")
            make_widget(fr).pack(side="left", fill="x", expand=True)
            rows[field] = (en, var)

        cat_var = tk.StringVar(value=UNCATEGORIZED)
        add_row("Category", lambda p: ctk.CTkComboBox(
            p, values=self._cat_values(), variable=cat_var,
            command=lambda v: self._on_pick_category(v, cat_var)), cat_var)
        sub_var = tk.StringVar(value=UNCATEGORIZED)
        add_row("Subcategory", lambda p: ctk.CTkComboBox(
            p, values=self._subcat_values(), variable=sub_var,
            command=lambda v: self._on_pick_subcategory(v, sub_var)), sub_var)
        urg_var = tk.StringVar(value="3")
        add_row("Urgency", lambda p: ctk.CTkComboBox(
            p, values=["1", "2", "3", "4", "5"], variable=urg_var), urg_var)
        imp_var = tk.StringVar(value="3")
        add_row("Importance", lambda p: ctk.CTkComboBox(
            p, values=["1", "2", "3", "4", "5"], variable=imp_var), imp_var)
        hz_var = tk.StringVar(value="")
        add_row("Horizon", lambda p: ctk.CTkComboBox(p, values=HORIZONS, variable=hz_var), hz_var)
        mot_var = tk.StringVar(value="")
        add_row("Motivation", lambda p: ctk.CTkComboBox(p, values=MOTIVATIONS, variable=mot_var), mot_var)
        st_var = tk.StringVar(value="Open")
        add_row("Status", lambda p: ctk.CTkComboBox(p, values=STATUSES, variable=st_var), st_var)
        rec_var = tk.StringVar(value="")
        add_row("Recurrence", lambda p: ctk.CTkComboBox(p, values=RECURRENCES, variable=rec_var), rec_var)
        due_var = tk.StringVar(value="")
        add_row("Due Date (YYYY-MM-DD)", lambda p: ctk.CTkEntry(p, textvariable=due_var), due_var)
        tag_var = tk.StringVar(value="")
        add_row("Tags (replace)", lambda p: ctk.CTkEntry(p, textvariable=tag_var), tag_var)

        def apply():
            changes = {f: var for f, (en, var) in rows.items() if en.get()}
            if not changes:
                win.destroy()
                return
            if "Due Date (YYYY-MM-DD)" in changes and \
                    not valid_date(changes["Due Date (YYYY-MM-DD)"].get()):
                messagebox.showwarning("Bulk edit",
                                       "Due Date must be YYYY-MM-DD or blank.", parent=win)
                return
            self._snapshot()
            mask = self.df["ID"].isin(ids)
            if "Category" in changes:
                self.df.loc[mask, "Category"] = changes["Category"].get().strip() or UNCATEGORIZED
            if "Subcategory" in changes:
                self.df.loc[mask, "Subcategory"] = changes["Subcategory"].get().strip() or UNCATEGORIZED
            if "Urgency" in changes:
                self.df.loc[mask, "Urgency"] = coerce_rating(changes["Urgency"].get())
            if "Importance" in changes:
                self.df.loc[mask, "Importance"] = coerce_rating(changes["Importance"].get())
            if "Horizon" in changes:
                self.df.loc[mask, "Horizon"] = coerce_horizon(changes["Horizon"].get())
            if "Motivation" in changes:
                self.df.loc[mask, "Motivation"] = coerce_motivation(changes["Motivation"].get())
            if "Recurrence" in changes:
                self.df.loc[mask, "Recurrence"] = changes["Recurrence"].get().strip()
            if "Due Date (YYYY-MM-DD)" in changes:
                self.df.loc[mask, "Due Date"] = changes["Due Date (YYYY-MM-DD)"].get().strip()
            if "Tags (replace)" in changes:
                self.df.loc[mask, "Tags"] = changes["Tags (replace)"].get().strip()
            if "Status" in changes:
                for _id in ids:
                    self._apply_status(_id, changes["Status"].get(), snapshot=False)
            self._mark_dirty()
            self._collect_categories()
            self.refresh_all()
            win.destroy()

        ctk.CTkButton(btns, text="Cancel", fg_color="gray30", hover_color="gray40",
                      command=win.destroy).pack(side="right")
        ctk.CTkButton(btns, text="Apply", command=apply).pack(side="right", padx=8)
        win.bind("<Escape>", lambda e: win.destroy())

    def _bulk_archive(self):
        ids = self._selected_ids()
        if not ids:
            return
        self._snapshot()
        self.df.loc[self.df["ID"].isin(ids), "Archived"] = "Yes"
        self._mark_dirty(); self.refresh_all()

    def _bulk_delete(self):
        ids = self._selected_ids()
        if not ids:
            return
        if not messagebox.askyesno("Delete", f"Delete {len(ids)} task(s)?"):
            return
        self._snapshot()
        self.df = self.df[~self.df["ID"].isin(ids)].reset_index(drop=True)
        self._mark_dirty(); self.refresh_all()

    # ---------- refresh ---------- #
    def refresh_all(self):
        name = self._current_tab()
        if name == "List":
            self.refresh_list()
        elif name == "Board":
            self.refresh_board()
        elif name == "Matrix":
            self.refresh_matrix()
        elif name == "Goals":
            self.refresh_goals()
        elif name == "Connections":
            self.refresh_web()
        elif name == "Analytics":
            self.refresh_analytics()
        # "Values" is free-form text; nothing to rebuild on data change.
        self._update_status_bar()

    def _current_tab(self):
        try:
            return self.tabs.get()
        except Exception:  # noqa: BLE001
            return "List"

    def _on_tab_change(self):
        self.refresh_all()

    def _schedule_list_refresh(self):
        if getattr(self, "_list_job", None):
            try:
                self.root.after_cancel(self._list_job)
            except Exception:  # noqa: BLE001
                pass
        self._list_job = self.root.after(160, self.refresh_list)

    def _row_tag(self, row, incomplete=None, today_d=None):
        if row["Status"] == "Complete":
            return "done"
        if incomplete is None:
            incomplete = _incomplete_id_set(self.df)
        if is_blocked(row, incomplete=incomplete):
            return "blocked"
        d = parse_date(row["Due Date"])
        if d and d < (today_d or today()):
            return "overdue"
        return f"u{coerce_rating(row['Urgency'])}"

    def _cell(self, row, col):
        if col == "Progress":
            return progress_str(row["Subtasks"])
        v = row[col]
        if col == "Tags":
            return str(v).replace(";", ", ")
        return v

    def refresh_list(self):
        if not hasattr(self, "tree"):
            return
        self._list_job = None
        self._set_appearance_buttons()
        self.tree.delete(*self.tree.get_children())
        checked = [c for c, v in getattr(self, "cat_filter_vars", {}).items() if v.get()]
        view = filter_view(self.df, self.search_var.get(), checked, self.smart)
        view = sort_view(view, self._sort_col, self._sort_asc)
        incomplete = _incomplete_id_set(self.df)
        today_d = today()
        for _, row in view.iterrows():
            pid = str(int(row["ID"]))
            self.tree.insert("", "end", iid=pid, text=str(row["Task"]),
                             open=self._subtasks_open,
                             values=[self._cell(row, c) for c in TREE_COLUMNS],
                             tags=(self._row_tag(row, incomplete, today_d),))
            subs = list(enumerate(parse_subtask_lines(row["Subtasks"])))

            hide_done_subs = self.smart == "Not Complete"
            if hide_done_subs:
                subs = [(j, it) for j, it in subs if not it["done"]]

            if self._sort_col in ("Urgency", "Importance"):
                key_field = "u" if self._sort_col == "Urgency" else "i"
                subs.sort(key=lambda pair: coerce_rating(pair[1][key_field]),
                          reverse=not self._sort_asc)

            for j, it in subs:
                box = "☑" if it["done"] else "☐"
                su = coerce_rating(it["u"])
                sub_vals = []
                for c in TREE_COLUMNS:
                    if c == "Category":
                        sub_vals.append(it.get("cat", ""))
                    elif c == "Subcategory":
                        sub_vals.append(it.get("sub", ""))
                    elif c == "Urgency":
                        sub_vals.append(str(su))
                    elif c == "Importance":
                        sub_vals.append(str(coerce_rating(it["i"])))
                    else:
                        sub_vals.append("")
                tag = f"su{su}_done" if it["done"] else f"su{su}"
                self.tree.insert(pid, "end", iid=f"sub::{pid}::{j}",
                                 text=f"   {box}  {it['text']}",
                                 values=sub_vals, tags=(tag,))
        task_arrow = ("  ▲" if self._sort_asc else "  ▼") if self._sort_col == "Task" else ""
        self.tree.heading("#0", text="Task" + task_arrow)
        for c in TREE_COLUMNS:
            arrow = ("  ▲" if self._sort_asc else "  ▼") if c == self._sort_col else ""
            self.tree.heading(c, text=c + arrow)
        self._update_subtask_toggle_btn()

    def _toggle_subtasks(self):
        self._subtasks_open = not self._subtasks_open
        for iid in self.tree.get_children(""):
            self.tree.item(iid, open=self._subtasks_open)
        self._update_subtask_toggle_btn()

    def _update_subtask_toggle_btn(self):
        if hasattr(self, "subtask_toggle_btn"):
            self.subtask_toggle_btn.configure(
                text="Collapse all" if self._subtasks_open else "Expand all")

    def _sort_column(self, col):
        if col == self._sort_col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col, self._sort_asc = col, True
        self.refresh_list()

    def refresh_board(self):
        if not hasattr(self, "board_cols"):
            return
        active = self.df[self.df["Archived"] != "Yes"]
        for st, col in self.board_cols.items():
            for w in col.winfo_children():
                w.destroy()
            sub = active[active["Status"] == st]
            sub = sort_view(sub, "Urgency", True)
            for _, row in sub.iterrows():
                self._board_card(col, row, st)

    def _board_card(self, parent, row, st):
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", pady=4, padx=2)
        urg_color = URGENCY_COLORS[coerce_rating(row["Urgency"])]
        ctk.CTkLabel(card, text=f"● {row['Task']}", anchor="w", text_color=urg_color,
                     wraplength=220, justify="left").pack(fill="x", padx=8, pady=(6, 0))
        meta = f"{row['Category']}"
        if str(row["Due Date"]).strip():
            meta += f"  ·  due {row['Due Date']}"
        prog = progress_str(row["Subtasks"])
        if prog:
            meta += f"  ·  {prog}"
        ctk.CTkLabel(card, text=meta, anchor="w", text_color="#9aa0aa",
                     font=ctk.CTkFont(size=11)).pack(fill="x", padx=8)
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=6, pady=(2, 6))
        idx = STATUSES.index(st)
        _id = int(row["ID"])
        if idx > 0:
            ctk.CTkButton(btns, text="◀", width=30,
                          command=lambda: self._apply_status(_id, STATUSES[idx - 1])
                          ).pack(side="left", padx=2)
        if idx < len(STATUSES) - 1:
            ctk.CTkButton(btns, text="▶", width=30,
                          command=lambda: self._apply_status(_id, STATUSES[idx + 1])
                          ).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="Edit", width=50,
                      command=lambda: self._open_edit_dialog(_id,
                          self.df[self.df["ID"] == _id].iloc[0])).pack(side="right", padx=2)

    def refresh_matrix(self):
        if not hasattr(self, "matrix_cells"):
            return
        for cell in self.matrix_cells:
            for w in cell.winfo_children():
                w.destroy()
        active = self.df[(self.df["Archived"] != "Yes") & (self.df["Status"] != "Complete")]
        for _, row in active.iterrows():
            d = parse_date(row["Due Date"])
            urgent = (coerce_rating(row["Urgency"]) <= 2 or
                      (d is not None and d <= today() + dt.timedelta(days=3)))
            important = coerce_rating(row["Importance"]) <= 2
            q = 0 if (urgent and important) else 1 if important else 2 if urgent else 3
            _id = int(row["ID"])
            ctk.CTkButton(self.matrix_cells[q], text=row["Task"], anchor="w",
                          fg_color="gray25", hover_color="gray35",
                          command=lambda i=_id: self._open_edit_dialog(
                              i, self.df[self.df["ID"] == i].iloc[0])).pack(fill="x", pady=2)

    def refresh_goals(self):
        if not hasattr(self, "goal_cols"):
            return
        active = self.df[self.df["Archived"] != "Yes"]
        for h, col in self.goal_cols.items():
            for w in col.winfo_children():
                w.destroy()
            sub = active[active["Horizon"] == h]
            sub = sort_view(sub, "Urgency", True)
            if sub.empty:
                ctk.CTkLabel(col, text="(no items — set an item's Goal horizon\n"
                                       "in its Edit dialog or via Bulk edit)",
                             text_color="#80868f", justify="left").pack(padx=8, pady=10)
                continue
            for _, row in sub.iterrows():
                self._goal_card(col, row)

    def _goal_card(self, parent, row):
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", pady=4, padx=2)
        urg = URGENCY_COLORS[coerce_rating(row["Urgency"])]
        ctk.CTkLabel(card, text=f"● {row['Task']}", anchor="w", text_color=urg,
                     wraplength=240, justify="left").pack(fill="x", padx=8, pady=(6, 0))
        meta = f"{row['Category']}"
        if str(row["Due Date"]).strip():
            meta += f"  ·  due {row['Due Date']}"
        meta += f"  ·  {row['Status']}"
        prog = progress_str(row["Subtasks"])
        if prog:
            meta += f"  ·  {prog}"
        ctk.CTkLabel(card, text=meta, anchor="w", text_color="#9aa0aa",
                     font=ctk.CTkFont(size=11)).pack(fill="x", padx=8)
        _id = int(row["ID"])
        ctk.CTkButton(card, text="Edit", width=50,
                      command=lambda: self._open_edit_dialog(
                          _id, self.df[self.df["ID"] == _id].iloc[0])
                      ).pack(anchor="e", padx=6, pady=(2, 6))

    def refresh_analytics(self):
        if not hasattr(self, "analytics_text"):
            return
        a = analytics(self.df)
        lead = f"{a['avg_lead_days']:.1f} days" if a["avg_lead_days"] is not None else "—"
        lines = [
            f"Total {a['total']}   |   Open {a['open']}   In progress {a['in_progress']}   "
            f"Done {a['done']}   Archived {a['archived']}",
            f"Overdue: {a['overdue']}      Completion rate: {a['completion_rate']*100:.0f}%"
            f"      Avg lead time: {lead}      Oldest open: {a['oldest_open_days']} days",
            f"Throughput (completed) — this wk {a['throughput'][0]}, "
            f"-1 {a['throughput'][1]}, -2 {a['throughput'][2]}, -3 {a['throughput'][3]}",
            "By category: " + (", ".join(f"{k}:{v}" for k, v in a["by_category"].items()) or "—"),
            "By urgency: " + (", ".join(f"U{k}:{v}" for k, v in a["by_urgency"].items()) or "—"),
        ]
        self.analytics_text.delete("1.0", "end")
        self.analytics_text.insert("1.0", "\n".join(lines))
        self._draw_charts(a)

    def _draw_charts(self, a):
        for w in self.analytics_chart.winfo_children():
            w.destroy()
        try:
            import matplotlib
            matplotlib.use("Agg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except Exception:  # noqa: BLE001
            ctk.CTkLabel(self.analytics_chart,
                         text="(install matplotlib for charts)").pack(pady=20)
            return
        fig = Figure(figsize=(8, 3), dpi=100)
        fig.patch.set_alpha(0)
        ax1 = fig.add_subplot(121)
        ax1.bar(range(4), a["throughput"][::-1], color="#1f6aa5")
        ax1.set_xticks(range(4)); ax1.set_xticklabels(["-3", "-2", "-1", "now"])
        ax1.set_title("Throughput / wk", color="#dce4ee")
        ax2 = fig.add_subplot(122)
        cats = list(a["by_category"].keys()) or ["—"]
        vals = list(a["by_category"].values()) or [0]
        ax2.barh(cats, vals, color="#2a9d8f")
        ax2.set_title("By category", color="#dce4ee")
        for ax in (ax1, ax2):
            ax.set_facecolor("none")
            ax.tick_params(colors="#9aa0aa")
            for s in ax.spines.values():
                s.set_color("#444")
        canvas = FigureCanvasTkAgg(fig, master=self.analytics_chart)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _update_status_bar(self):
        df = self.df
        total = len(df)
        active = df[df["Archived"] != "Yes"]
        status = active["Status"]
        open_c = int((status == "Open").sum())
        inprog = int((status == "In Progress").sum())
        done = int((status == "Complete").sum())
        due = pd.to_datetime(active["Due Date"], errors="coerce")
        overdue = int(((status != "Complete") & due.notna() &
                       (due < pd.Timestamp(today()))).sum())
        f = os.path.basename(self.current_file) if self.current_file else "untitled.csv"
        self.status_lbl.configure(
            text=f"{f}   •   {total} tasks   "
                 f"({open_c} open, {inprog} in-progress, "
                 f"{done} done, {overdue} overdue)   •   list: {self.smart}")

    # ---------- links / files ---------- #
    def _open_link(self, target):
        target = str(target or "").strip()
        if not target:
            return
        try:
            if re.match(r"^https?://", target):
                import webbrowser
                webbrowser.open(target)
            elif os.path.exists(target):
                if hasattr(os, "startfile"):
                    os.startfile(target)  # noqa
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", target])
            else:
                messagebox.showinfo("Open link",
                                    "Link is not an http(s) URL or an existing file path.")
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Open link", str(ex))

    def _browse_file(self, var):
        """Attach a clickable document (.doc / .docx / .txt / .odt)."""
        path = filedialog.askopenfilename(title="Choose a file to attach",
                                          filetypes=FILE_TYPES)
        if path:
            var.set(path)

    def _link_for_iid(self, iid):
        try:
            _id = int(iid)
        except (ValueError, TypeError):
            return ""
        mask = self.df["ID"] == _id
        if not mask.any():
            return ""
        return str(self.df[mask].iloc[0]["Link"]).strip()

    def _on_tree_double(self, event):
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        parent_iid = row
        if row and not str(row).isdigit():
            parent_iid = self.tree.parent(row)
        if row and col:
            try:
                idx = int(col.replace("#", "")) - 1
            except ValueError:
                idx = -1
            if 0 <= idx < len(TREE_COLUMNS) and TREE_COLUMNS[idx] == "Link":
                link = self._link_for_iid(parent_iid)
                if link:
                    self._open_link(link)
                    return
        if parent_iid and str(parent_iid).isdigit():
            _id = int(parent_iid)
            self._open_edit_dialog(_id, self.df[self.df["ID"] == _id].iloc[0])
            return
        self.edit_selected()

    def _selected_subtask_iids(self):
        return [str(i) for i in self.tree.selection()
                if re.match(r"^sub::\d+::\d+$", str(i))]

    def _set_selected_subtasks_done(self, done):
        iids = self._selected_subtask_iids()
        if not iids:
            messagebox.showinfo(
                "Subtasks",
                "Select one or more subtasks first.\n\n"
                "Click the subtask rows (the indented items under a task), "
                "then use this button.")
            return
        by_task = {}
        for iid in iids:
            m = re.match(r"^sub::(\d+)::(\d+)$", iid)
            by_task.setdefault(int(m.group(1)), set()).add(int(m.group(2)))
        self._snapshot()
        changed = False
        for _id, idxs in by_task.items():
            mask = self.df["ID"] == _id
            if not mask.any():
                continue
            items = parse_subtask_lines(self.df[mask].iloc[0]["Subtasks"])
            for j in idxs:
                if 0 <= j < len(items) and items[j]["done"] != done:
                    items[j]["done"] = done
                    changed = True
            self.df.loc[mask, "Subtasks"] = serialize_subtasks(items)
        if changed:
            self._mark_dirty()
            self.refresh_all()

    # ---------- edit dialog ---------- #
    def edit_selected(self):
        ids = self._selected_ids()
        if not ids:
            return
        _id = ids[0]
        self._open_edit_dialog(_id, self.df[self.df["ID"] == _id].iloc[0])

    def _open_edit_dialog(self, _id, row):
        win = ctk.CTkToplevel(self.root)
        win.title(f"Edit Task #{_id}")
        win.geometry("680x760")
        win.minsize(560, 480)
        win.transient(self.root)
        win.after(120, win.grab_set)

        v = {c: tk.StringVar(value=str(row[c])) for c in
             ("Task", "Category", "Subcategory", "Tags", "Urgency", "Importance",
              "Horizon", "Motivation", "Status", "Start Date", "Due Date",
              "Date Created", "Date Completed", "Recurrence", "Estimate",
              "Actual", "Blocked By", "Link")}
        v["Urgency"].set(str(coerce_rating(row["Urgency"])))
        v["Importance"].set(str(coerce_rating(row["Importance"])))
        v["Horizon"].set(coerce_horizon(row["Horizon"]))
        v["Motivation"].set(coerce_motivation(row["Motivation"]))

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=16, pady=12)
        form = ctk.CTkScrollableFrame(win)
        form.pack(side="top", fill="both", expand=True, padx=12, pady=(12, 0))

        def field(label, widget):
            ctk.CTkLabel(form, text=label, anchor="w").pack(fill="x", pady=(8, 2))
            widget.pack(fill="x")

        field("Task", ctk.CTkEntry(form, textvariable=v["Task"]))
        catbox = ctk.CTkComboBox(form, values=self._cat_values(), variable=v["Category"],
                                 command=lambda val: self._on_pick_category(val, v["Category"]))
        field("Category", catbox)
        field("Subcategory", ctk.CTkComboBox(
            form, values=self._subcat_values(), variable=v["Subcategory"],
            command=lambda val: self._on_pick_subcategory(val, v["Subcategory"])))
        field("Tags (semicolon-separated)", ctk.CTkEntry(form, textvariable=v["Tags"]))
        field("Urgency (1=most)", ctk.CTkComboBox(form, values=["1", "2", "3", "4", "5"], variable=v["Urgency"]))
        field("Importance (1=most)", ctk.CTkComboBox(form, values=["1", "2", "3", "4", "5"], variable=v["Importance"]))
        field("Goal horizon (short / medium / long-term)",
              ctk.CTkComboBox(form, values=HORIZONS, variable=v["Horizon"]))
        field("Motivation (Obligation = need-to-do · Joy = fun-to-do)",
              ctk.CTkComboBox(form, values=MOTIVATIONS, variable=v["Motivation"]))
        field("Status", ctk.CTkComboBox(form, values=STATUSES, variable=v["Status"]))
        field("Recurrence", ctk.CTkComboBox(form, values=RECURRENCES, variable=v["Recurrence"]))
        field("Start Date (YYYY-MM-DD)", ctk.CTkEntry(form, textvariable=v["Start Date"]))
        field("Due Date (YYYY-MM-DD)", ctk.CTkEntry(form, textvariable=v["Due Date"]))
        field("Date Created", ctk.CTkEntry(form, textvariable=v["Date Created"]))
        field("Date Completed", ctk.CTkEntry(form, textvariable=v["Date Completed"]))
        field("Estimate (h)", ctk.CTkEntry(form, textvariable=v["Estimate"]))
        field("Actual (h)", ctk.CTkEntry(form, textvariable=v["Actual"]))
        field("Blocked By (task IDs, semicolon-separated)",
              ctk.CTkEntry(form, textvariable=v["Blocked By"]))

        # Link / clickable file (.doc / .docx / .txt / .odt) with a Browse button.
        link_row = ctk.CTkFrame(form, fg_color="transparent")
        ctk.CTkEntry(link_row, textvariable=v["Link"]).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(link_row, text="Browse…", width=84,
                      command=lambda: self._browse_file(v["Link"])).pack(side="left", padx=(6, 0))
        field("Link (URL, or a .doc / .docx / .txt / .odt file)", link_row)

        ctk.CTkLabel(form, text="Subtasks (each has its own category / urgency / importance)",
                     anchor="w").pack(fill="x", pady=(8, 2))
        sub_wrap = ctk.CTkFrame(form, fg_color="transparent")
        sub_wrap.pack(fill="x")

        add_row = ctk.CTkFrame(sub_wrap, fg_color="transparent")
        add_row.pack(fill="x", pady=(0, 4))
        new_sub_var = tk.StringVar()
        new_sub_entry = ctk.CTkEntry(add_row, textvariable=new_sub_var,
                                     placeholder_text="Add a sub to-do item…")
        new_sub_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        sub_list = ctk.CTkFrame(sub_wrap, fg_color="transparent")
        sub_list.pack(fill="x")

        subtask_items = []

        def _urg_color(u):
            return URGENCY_COLORS.get(coerce_rating(u), "#ffd43b")

        def render_subtasks():
            for w in sub_list.winfo_children():
                w.destroy()
            for i, it in enumerate(subtask_items):
                rowf = ctk.CTkFrame(sub_list, fg_color="transparent")
                rowf.pack(fill="x", pady=2)
                ctk.CTkCheckBox(rowf, text="", width=28,
                                variable=it["done"]).pack(side="left")
                swatch = ctk.CTkLabel(rowf, text="●", width=16,
                                      text_color=_urg_color(it["u"].get()))
                swatch.pack(side="left", padx=(0, 2))
                ctk.CTkEntry(rowf, textvariable=it["text"], width=180).pack(
                    side="left", fill="x", expand=True, padx=(2, 6))
                ctk.CTkComboBox(rowf, width=110, values=self._cat_values(),
                                variable=it["cat"],
                                command=lambda val, var=it["cat"]:
                                    self._on_pick_category(val, var)).pack(side="left", padx=2)
                ctk.CTkComboBox(rowf, width=110, values=self._subcat_values(),
                                variable=it["sub"],
                                command=lambda val, var=it["sub"]:
                                    self._on_pick_subcategory(val, var)).pack(side="left", padx=2)

                def _on_urg(val, sw=swatch):
                    sw.configure(text_color=_urg_color(val))
                ctk.CTkComboBox(rowf, width=58, values=["1", "2", "3", "4", "5"],
                                variable=it["u"], command=_on_urg).pack(side="left", padx=2)
                ctk.CTkComboBox(rowf, width=58, values=["1", "2", "3", "4", "5"],
                                variable=it["i"]).pack(side="left", padx=2)
                ctk.CTkButton(rowf, text="✕", width=30, fg_color="gray30",
                              hover_color="#a33",
                              command=lambda idx=i: remove_subtask(idx)).pack(side="left", padx=(2, 0))

        def add_subtask(text="", done=False, cat="", sub="", u=3, i=3):
            subtask_items.append({
                "done": tk.BooleanVar(value=done),
                "text": tk.StringVar(value=text),
                "cat": tk.StringVar(value=cat),
                "sub": tk.StringVar(value=sub),
                "u": tk.StringVar(value=str(coerce_rating(u))),
                "i": tk.StringVar(value=str(coerce_rating(i))),
            })
            render_subtasks()

        def remove_subtask(idx):
            if 0 <= idx < len(subtask_items):
                subtask_items.pop(idx)
                render_subtasks()

        def add_from_entry():
            t = new_sub_var.get().strip()
            if t:
                add_subtask(t, cat=v["Category"].get().strip(),
                            sub=v["Subcategory"].get().strip())
                new_sub_var.set("")
                new_sub_entry.focus_set()

        ctk.CTkButton(add_row, text="Add", width=60,
                      command=add_from_entry).pack(side="left")
        new_sub_entry.bind("<Return>", lambda e: add_from_entry())

        for _it in parse_subtask_lines(row["Subtasks"]):
            add_subtask(_it["text"], _it["done"], _it.get("cat", ""),
                        _it.get("sub", ""), _it.get("u", 3), _it.get("i", 3))

        ctk.CTkLabel(form, text="Notes", anchor="w").pack(fill="x", pady=(8, 2))
        notes = ctk.CTkTextbox(form, height=110)
        notes.pack(fill="both", expand=True)
        notes.insert("1.0", str(row["Notes"]))

        def open_link():
            self._open_link(v["Link"].get())

        def save_changes():
            if not v["Task"].get().strip():
                messagebox.showwarning("Edit", "Task can't be empty.", parent=win)
                return
            for lbl in ("Start Date", "Due Date", "Date Created", "Date Completed"):
                if not valid_date(v[lbl].get()):
                    messagebox.showwarning("Edit", f"{lbl} must be YYYY-MM-DD or blank.", parent=win)
                    return
            self._snapshot()
            mask = self.df["ID"] == _id
            status = v["Status"].get()
            completed = v["Date Completed"].get().strip()
            if status == "Complete" and not completed:
                completed = today_str()
            if status != "Complete":
                completed = ""
            for c in v:
                if c in ("Date Completed", "Urgency", "Importance", "Horizon",
                         "Motivation"):
                    continue
                self.df.loc[mask, c] = v[c].get().strip()
            self.df.loc[mask, "Urgency"] = coerce_rating(v["Urgency"].get())
            self.df.loc[mask, "Importance"] = coerce_rating(v["Importance"].get())
            self.df.loc[mask, "Horizon"] = coerce_horizon(v["Horizon"].get())
            self.df.loc[mask, "Motivation"] = coerce_motivation(v["Motivation"].get())
            self.df.loc[mask, "Category"] = v["Category"].get().strip() or UNCATEGORIZED
            self.df.loc[mask, "Subcategory"] = v["Subcategory"].get().strip() or UNCATEGORIZED
            self.df.loc[mask, "Date Completed"] = completed
            self.df.loc[mask, "Subtasks"] = serialize_subtasks([
                {"done": it["done"].get(), "text": it["text"].get(),
                 "cat": it["cat"].get().strip(), "sub": it["sub"].get().strip(),
                 "u": it["u"].get(), "i": it["i"].get()}
                for it in subtask_items])
            self.df.loc[mask, "Notes"] = notes.get("1.0", "end").strip()
            if status == "Complete" and str(row["Status"]) != "Complete" \
                    and str(v["Recurrence"].get()).strip():
                task = self.df[mask].iloc[0].to_dict()
                nxt = next_occurrence(task); nxt["ID"] = self._next_id()
                self._append(nxt)
            self._mark_dirty(); self._collect_categories(); self.refresh_all()
            win.destroy()

        ctk.CTkButton(btns, text="Open link", width=90, fg_color="gray30",
                      hover_color="gray40", command=open_link).pack(side="left")
        ctk.CTkButton(btns, text="Cancel", width=80, fg_color="gray30",
                      hover_color="gray40", command=win.destroy).pack(side="right")
        ctk.CTkButton(btns, text="Save Changes", command=save_changes).pack(side="right", padx=8)
        win.bind("<Escape>", lambda e: win.destroy())


if __name__ == "__main__":
    root = ctk.CTk()
    root.withdraw()                      # hide main window during the load page
    splash = show_splash(root)
    app = TaskManager(root)

    def _start():
        try:
            splash.destroy()
        except Exception:  # noqa: BLE001
            pass
        root.deiconify()

    root.after(1800, _start)             # show the start page briefly, then the app
    root.mainloop()