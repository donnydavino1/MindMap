"""
Mind Map ©
==========
"A map is not the territory."

A CustomTkinter + pandas to-do / mind-map manager.

Views (tabs)
    List       sortable/filterable tree. Tasks nest to any depth; drag a task
               onto another to make it a subtask. Smart-list sidebar + category
               check-boxes.
    Map        sunburst "disk-usage" style chart of your whole task tree.
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
import math
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

# Flat, neutral look: every widget is grey; only ACCENT buttons carry colour.
BTN_BG = ("#e5e7eb", "#2b2f37")
BTN_HOVER = ("#d1d5db", "#3a3f4a")
BTN_TEXT = ("#1f2937", "#dce4ee")
ON_BG = "#4b5563"                     # "selected / switched on" grey
ACCENT = dict(fg_color="#1f6aa5", hover_color="#2785cf", text_color="white")


def apply_flat_theme():
    """Re-skin CustomTkinter's default (bright blue) theme as flat greys."""
    try:
        th = ctk.ThemeManager.theme
        th["CTkButton"].update({"fg_color": BTN_BG, "hover_color": BTN_HOVER,
                                "text_color": BTN_TEXT, "corner_radius": 6})
        th["CTkOptionMenu"].update({"fg_color": BTN_BG, "button_color": BTN_HOVER,
                                    "button_hover_color": ("#c4c8cf", "#4b5563"),
                                    "text_color": BTN_TEXT})
        th["CTkSegmentedButton"].update({
            "fg_color": ("#d9dce1", "#23262d"), "selected_color": ON_BG,
            "selected_hover_color": ("#6b7280", "#5b6573"),
            "unselected_color": ("#d9dce1", "#23262d"),
            "unselected_hover_color": BTN_HOVER, "text_color": BTN_TEXT})
        th["CTkCheckBox"].update({"fg_color": ("#6b7280", "#6b7280"),
                                  "hover_color": ("#7b8494", "#7b8494")})
    except Exception:  # noqa: BLE001
        pass


apply_flat_theme()

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
CSV_COLUMNS = ["ID", "Task", "Category", "Subcategory", "Tags", "Urgency",
               "Importance", "Horizon", "Motivation", "Status", "Start Date",
               "Due Date", "Date Created", "Date Completed", "Recurrence",
               "Estimate", "Actual", "Blocked By", "Subtasks", "Link", "Notes",
               "Archived", "Parent"]
# NOTE: "Subtasks" is a legacy column (old text-based subtasks). On load those
# lines are converted into real child tasks (via "Parent") and the column is
# emptied.  "Start Date" now doubles as "don't start before" (waiting) and
# "Blocked By" as "wait until these tasks are complete (or deleted)".
TREE_COLUMNS = ["Category", "Subcategory", "Tags", "Urgency", "Importance",
                "Horizon", "Motivation", "Status", "Due Date", "Progress", "Link"]
TREE_WIDTHS = {"Task": 270, "Category": 98, "Subcategory": 100, "Tags": 104,
               "Urgency": 68, "Importance": 78, "Horizon": 100, "Motivation": 96,
               "Status": 90, "Due Date": 94, "Progress": 70, "Link": 140}
STATUSES = ["Open", "In Progress", "Complete"]
RECURRENCES = ["", "daily", "weekly", "biweekly", "monthly"]
HORIZONS = ["", "Short-term", "Medium-term", "Long-term"]
# "Need to do" vs "fun to do": obligation vs intrinsic enjoyment.
MOTIVATIONS = ["", "Obligation", "Joy"]
SMART_LISTS = ["All", "Not Complete", "Today", "This Week", "Overdue",
               "In Progress", "High Priority", "Ready", "Waiting", "No Date",
               "Completed", "Archived"]
ADD_NEW_CATEGORY = "➕ Add category…"
ADD_NEW_SUBCATEGORY = "➕ Add subcategory…"
UNCATEGORIZED = "Uncategorized"
TOP_LEVEL = "(top level)"
# Columns shown in the List by default; the rest are one click away (Columns ▾).
DEFAULT_VISIBLE_COLS = ["Category", "Urgency", "Importance", "Motivation",
                        "Status", "Due Date", "Progress", "Link"]
# Slim icon sidebar (hover an icon for the tab name; Ctrl+1..7 jumps to a tab).
TAB_ICONS = {"List": "☰", "Map": "◎", "Board": "▥", "Matrix": "⊞",
             "Goals": "⚑", "Values": "❖", "Analytics": "◷"}
DATE_FMT = "%Y-%m-%d"
DATE_INPUT_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y")
DATE_COLS = ("Start Date", "Due Date", "Date Created", "Date Completed")
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".mind_map.json")
FILE_TYPES = [("Documents", "*.doc *.docx *.txt *.odt"), ("All files", "*.*")]

URGENCY_COLORS = {1: "#ff6b6b", 2: "#ffa94d", 3: "#ffd43b", 4: "#a9e34b", 5: "#69db7c"}
MOTIVATION_COLORS = {"Obligation": "#5c7cfa", "Joy": "#ffa94d", "": "#6b727d"}
CATEGORY_PALETTE = ["#4dabf7", "#ffa94d", "#69db7c", "#da77f2", "#ff8787",
                    "#3bc9db", "#ffd43b", "#a9e34b", "#f783ac", "#9775fa",
                    "#63e6be", "#ffc078"]
MAP_BG = "#1b1d22"
MAP_EDGE = "#15171c"

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


def parse_id(v):
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return None


def parse_id_list(s):
    out = []
    for x in re.split(r"[;,\s]+", str(s or "")):
        i = parse_id(x)
        if i is not None and i not in out:
            out.append(i)
    return out


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


def blend(c1, c2, t):
    """Mix hex colour c1 toward c2 by fraction t (0..1)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def text_on(color):
    r, g, b = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#111318" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#f1f3f5"


# --------------------------------------------------------------------------- #
# Task tree helpers (Parent column)
# --------------------------------------------------------------------------- #
def children_map(df):
    """{parent_id: [child_ids]} for every row whose Parent points at a real row."""
    if df.empty:
        return {}
    ids = {int(i) for i in df["ID"]}
    kids = {}
    for i, p in zip(df["ID"], df["Parent"]):
        pid = parse_id(p)
        if pid is not None and pid in ids and pid != int(i):
            kids.setdefault(pid, []).append(int(i))
    return kids


def descendants(kids, _id):
    out, seen, stack = [], {_id}, list(kids.get(_id, []))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
        stack.extend(kids.get(n, []))
    return out


def clean_parents(df):
    """Drop dangling / self / cyclic Parent links."""
    if df.empty:
        return df
    ids = {int(i) for i in df["ID"]}
    par = {int(i): parse_id(p) for i, p in zip(df["ID"], df["Parent"])}
    for i in list(par):
        p = par[i]
        if p is not None and (p not in ids or p == i):
            par[i] = None
    for i in list(par):
        seen, p = {i}, par[i]
        while p is not None:
            if p == i:
                par[i] = None
                break
            if p in seen:
                break
            seen.add(p)
            p = par.get(p)
    df = df.copy()
    df["Parent"] = [("" if par[int(i)] is None else str(par[int(i)])) for i in df["ID"]]
    return df


def effective_frame(df):
    """Copy of df where every unfinished parent shows the Urgency/Importance of
    its most urgent / most important unfinished subtask (recursively)."""
    out = df.copy()
    if out.empty:
        return out
    kids = children_map(df)
    ids = [int(i) for i in df["ID"]]
    own = {i: (coerce_rating(u), coerce_rating(m))
           for i, u, m in zip(ids, df["Urgency"], df["Importance"])}
    done = {i: (s == "Complete") for i, s in zip(ids, df["Status"])}
    memo = {}

    def eff(i):
        if i in memo:
            return memo[i]
        memo[i] = own[i]                       # also guards against cycles
        live = [c for c in kids.get(i, []) if not done.get(c, False)]
        if live and not done[i]:
            vals = [eff(c) for c in live]
            memo[i] = (min(v[0] for v in vals), min(v[1] for v in vals))
        return memo[i]

    out["Urgency"] = [eff(i)[0] for i in ids]
    out["Importance"] = [eff(i)[1] for i in ids]
    return out


def progress_map(df, kids=None):
    """{parent_id: (done_descendants, total_descendants)}"""
    kids = kids if kids is not None else children_map(df)
    stat = {int(i): s for i, s in zip(df["ID"], df["Status"])}
    out = {}
    for i in kids:
        d = descendants(kids, i)
        out[i] = (sum(1 for x in d if stat.get(x) == "Complete"), len(d))
    return out


def _incomplete_id_set(df):
    """IDs that still 'block' anything waiting on them.  Archived rows don't;
    a finished parent still counts while any of its subtasks is unfinished."""
    stat = {int(i): (s, a) for i, s, a in zip(df["ID"], df["Status"], df["Archived"])}
    inc = {i for i, (s, a) in stat.items() if s != "Complete" and a != "Yes"}
    kids = children_map(df)
    for i, (s, a) in stat.items():
        if i not in inc and a != "Yes" and any(d in inc for d in descendants(kids, i)):
            inc.add(i)
    return inc


def is_blocked(row, df=None, incomplete=None):
    ids = parse_id_list(row.get("Blocked By", ""))
    if not ids:
        return False
    if incomplete is None:
        incomplete = _incomplete_id_set(df) if df is not None else set()
    return any(b in incomplete for b in ids)


def waiting_ids(df, base=None):
    """IDs that are 'waiting': blocked by an unfinished task, or with a Start
    Date still in the future -- and everything underneath such a task."""
    base = base or today()
    if df.empty:
        return set()
    inc = _incomplete_id_set(df)
    direct = set()
    for i, bb, sd, st in zip(df["ID"], df["Blocked By"], df["Start Date"], df["Status"]):
        if st == "Complete":
            continue
        d = parse_date(sd)
        if (d is not None and d > base) or is_blocked({"Blocked By": bb}, incomplete=inc):
            direct.add(int(i))
    kids = children_map(df)
    out = set(direct)
    for i in direct:
        out.update(descendants(kids, i))
    return out


# --------------------------------------------------------------------------- #
# Legacy subtask text -> real child tasks
# --------------------------------------------------------------------------- #
SUB_DEFAULTS = {"cat": "", "sub": "", "u": 3, "i": 3}
_SUB_FIELD_RE = re.compile(r"\|\s*([a-zA-Z]+)\s*=\s*([^|]*)")


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


def migrate_subtasks(df):
    """Turn every legacy 'Subtasks' text line into a real child row."""
    has = df["Subtasks"].astype(str).str.strip() != ""
    if not has.any():
        return df
    df = df.copy()
    rows = []
    nxt = int(df["ID"].max()) + 1
    for idx in df.index[has]:
        r = df.loc[idx]
        for it in parse_subtask_lines(r["Subtasks"]):
            row = {c: "" for c in CSV_COLUMNS}
            row.update({
                "ID": nxt, "Task": it["text"],
                "Category": it["cat"] or r["Category"],
                "Subcategory": it["sub"] or r["Subcategory"],
                "Urgency": it["u"], "Importance": it["i"],
                "Motivation": r["Motivation"],
                "Status": "Complete" if it["done"] else "Open",
                "Date Created": r["Date Created"],
                "Date Completed": (r["Date Completed"] or today_str()) if it["done"] else "",
                "Parent": str(int(r["ID"])), "Archived": r["Archived"]})
            rows.append(row)
            nxt += 1
        df.at[idx, "Subtasks"] = ""
    if rows:
        df = pd.concat([df, pd.DataFrame(rows, columns=CSV_COLUMNS)], ignore_index=True)
    return df


# --------------------------------------------------------------------------- #
# Quick-add parsing, filtering, sorting
# --------------------------------------------------------------------------- #
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
    keep = []
    for t in str(text).split():
        if re.fullmatch(r"!([1-5])", t):
            out["Urgency"] = int(t[1])
        elif re.fullmatch(r"\*([1-5])", t):
            out["Importance"] = int(t[1])
        elif t.startswith("#") and len(t) > 1:
            out["Tags"].append(t[1:])
        elif t.startswith("@") and len(t) > 1:
            name = t[1:]
            out["Category"] = next((c for c in categories if c.lower() == name.lower()), name)
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
    if name in ("Waiting", "Ready"):
        ws = waiting_ids(df, base)
        is_w = df["ID"].map(lambda i: int(i) in ws).astype(bool)
        if name == "Waiting":
            return active & is_w
        kids = children_map(df)
        stat = {int(i): s for i, s in zip(df["ID"], df["Status"])}
        has_live = {p for p, cs in kids.items() if any(stat.get(c) != "Complete" for c in cs)}
        leaf = df["ID"].map(lambda i: int(i) not in has_live).astype(bool)
        return active & ~is_w & leaf
    return ~archived


def filter_view(df, search="", categories=None, smart="All", base=None):
    if df.empty:
        return df
    view = df[smart_mask(df, smart, base)]
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


def sort_view(view, col, ascending, progress=None):
    """Sort by `col`, then always alphabetically by Task name (A-Z)."""
    if view.empty:
        return view
    name = view["Task"].astype(str).str.strip().str.lower()
    if not col:
        return (view.assign(_n=name)
                    .sort_values("_n", ascending=True, kind="mergesort")
                    .drop(columns="_n"))

    def _progress_key(i):
        d, t = (progress or {}).get(int(i), (0, 0))
        return (d / t) if t else -1

    if col == "Progress":
        key = view["ID"].map(_progress_key)
    elif col in ("Urgency", "Importance"):
        key = view[col].map(coerce_rating)
    elif col in DATE_COLS:
        key = pd.to_datetime(view[col], errors="coerce")
    elif col == "Task":
        key = name
    else:
        key = view[col].astype(str).str.lower()
    return (view.assign(_k=key, _n=name)
                .sort_values(["_k", "_n"], ascending=[ascending, True],
                             na_position="last", kind="mergesort")
                .drop(columns=["_k", "_n"]))


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
    ids, seen, nxt = [], set(), 0
    for v in df["ID"]:
        i = parse_id(v)
        if i is None or i in seen:
            i = nxt
        seen.add(i)
        nxt = max(nxt, i) + 1
        ids.append(i)
    df["ID"] = ids
    df["Parent"] = df["Parent"].map(lambda s: "" if parse_id(s) is None else str(parse_id(s)))
    df = clean_parents(df.reset_index(drop=True))
    df = migrate_subtasks(df)
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
    nxt["Subtasks"] = ""
    return nxt


def export_markdown(df):
    lines = [f"# Tasks (exported {today_str()})", ""]
    pmap = {int(i): parse_id(p) for i, p in zip(df["ID"], df["Parent"])}

    def depth(i):
        d, p, guard = 0, pmap.get(i), 0
        while p is not None and guard < 50:
            d += 1
            p = pmap.get(p)
            guard += 1
        return d

    for cat, grp in df.groupby(df["Category"].replace("", UNCATEGORIZED)):
        lines.append(f"## {cat}")
        gids = set(int(i) for i in grp["ID"])
        by_parent = {}
        for _, r in grp.iterrows():
            p = pmap.get(int(r["ID"]))
            by_parent.setdefault(p if p in gids else None, []).append(r)

        def emit(r):
            box = "x" if r["Status"] == "Complete" else " "
            extra = []
            if str(r["Due Date"]).strip():
                extra.append(f"due {r['Due Date']}")
            extra.append(f"U{coerce_rating(r['Urgency'])}/I{coerce_rating(r['Importance'])}")
            lines.append(f"{'  ' * depth(int(r['ID']))}- [{box}] {r['Task']}  ({', '.join(extra)})")
            for ch in by_parent.get(int(r["ID"]), []):
                emit(ch)

        for r in by_parent.get(None, []):
            emit(r)
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
# Small widgets
# --------------------------------------------------------------------------- #
class Tooltip:
    """Tiny hover label shown to the right of a widget."""

    def __init__(self, widget, text):
        self.w, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _e=None):
        if self.tip is not None:
            return
        try:
            self.tip = tk.Toplevel(self.w)
            self.tip.overrideredirect(True)
            x = self.w.winfo_rootx() + self.w.winfo_width() + 6
            y = self.w.winfo_rooty() + self.w.winfo_height() // 2 - 13
            self.tip.geometry(f"+{x}+{y}")
            tk.Label(self.tip, text=self.text, bg="#0b0c0e", fg="#f1f3f5",
                     padx=9, pady=3, font=("Segoe UI", 10)).pack()
        except Exception:  # noqa: BLE001
            self.tip = None

    def _hide(self, _e=None):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:  # noqa: BLE001
                pass
            self.tip = None


class IconTabs:
    """Replacement for CTkTabview: a slim sidebar of icon buttons + a content area.

    API mirrors the bits of CTkTabview the app uses: add / tab / get / set.
    `set()` fires `command` when the tab really changes (so views refresh).
    """

    def __init__(self, parent, icons, command=None):
        self.icons, self.command = icons, command
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.bar = ctk.CTkFrame(self.frame, corner_radius=8,
                                fg_color=("#e5e7eb", "#1f2228"))
        self.bar.pack(side="left", fill="y", padx=(0, 8), pady=2)
        self.body = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.body.pack(side="left", fill="both", expand=True)
        self._frames, self._btns, self._current = {}, {}, None

    def pack(self, **kw):
        self.frame.pack(**kw)

    def add(self, name):
        f = ctk.CTkFrame(self.body, fg_color="transparent")
        self._frames[name] = f
        b = ctk.CTkButton(self.bar, text=self.icons.get(name, name[:1]), width=40, height=40,
                          corner_radius=8, fg_color="transparent",
                          hover_color=BTN_HOVER, text_color=("#6b7280", "#8b93a1"),
                          font=ctk.CTkFont(size=18), command=lambda n=name: self.set(n))
        b.pack(padx=7, pady=(10 if not self._btns else 2, 2))
        Tooltip(b, name)
        self._btns[name] = b
        if self._current is None:
            self._show(name)
        return f

    def tab(self, name):
        return self._frames[name]

    def get(self):
        return self._current or ""

    def set(self, name, notify=True):
        if name not in self._frames or name == self._current:
            return
        self._show(name)
        if notify and self.command:
            self.command()

    def _show(self, name):
        for f in self._frames.values():
            f.pack_forget()
        self._frames[name].pack(fill="both", expand=True)
        for n, b in self._btns.items():
            on = (n == name)
            b.configure(fg_color=(BTN_BG if on else "transparent"),
                        text_color=(("#111827", "#ffffff") if on else ("#6b7280", "#8b93a1")))
        self._current = name


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
        self.categories = []
        self.subcategories = [UNCATEGORIZED]
        self.smart = self.settings.get("smart", "All")
        if self.smart not in SMART_LISTS:
            self.smart = "All"
        self._sort_col, self._sort_asc = "Urgency", True
        self._subtasks_open = True
        self._open_map = {}
        self._drag = None
        self._undo, self._redo = [], []
        self._autosave_job = None
        self._last_backup_ts = 0.0
        # Map-tab state
        self._map_focus = ("root",)
        self._map_sel = None
        self._map_layers = set()
        self._map_all = False
        self._map_hit = []
        self._map_hover = None
        self._map_geo = (0, 0, 0)
        self._map_job = None
        self._map_zoom_ts = 0.0
        self._map_legend_mode = None
        self._map_layer_btns = {}
        self.details_open = bool(self.settings.get("details_open", False))
        self.ui_scale = float(self.settings.get("ui_scale", 1.0))
        try:
            ctk.set_widget_scaling(self.ui_scale)
        except Exception:  # noqa: BLE001
            pass

        self.df = normalize_frame(pd.DataFrame(columns=CSV_COLUMNS))
        self._recompute()

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
        for i, name in enumerate(TAB_ICONS, 1):
            self.root.bind(f"<Control-Key-{i}>", lambda e, n=name: self.tabs.set(n))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        for seq, fn in (("<Control-s>", self.save_csv), ("<Control-o>", self.open_csv),
                        ("<Control-n>", self.new_file), ("<Control-z>", self.undo),
                        ("<Control-y>", self.redo), ("<Control-f>", self._focus_search)):
            self.root.bind(seq, lambda e, f=fn: f())

    # ---------- derived data (recomputed after every change) ---------- #
    def _recompute(self):
        self.vdf = effective_frame(self.df)          # parents show their hottest child
        self._kids = children_map(self.df)
        self._progress = progress_map(self.df, self._kids)
        self._waiting = waiting_ids(self.df)
        self._names = {int(i): str(t) for i, t in zip(self.df["ID"], self.df["Task"])}
        self._pmap = {int(i): parse_id(p) for i, p in zip(self.df["ID"], self.df["Parent"])}

    def _path_prefix(self, _id):
        names, p, guard = [], self._pmap.get(_id), 0
        while p is not None and guard < 50:
            names.append(self._names.get(p, "?"))
            p = self._pmap.get(p)
            guard += 1
        return " › ".join(reversed(names))

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
                "ui_scale": getattr(self, "ui_scale", 1.0),
                "details_open": bool(getattr(self, "details_open", False))}
        if hasattr(self, "_col_vars"):
            data["visible_cols"] = [c for c in TREE_COLUMNS if self._col_vars[c].get()]
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

    # ---------- pop-up sizing ---------- #
    @staticmethod
    def _window_scale(win):
        for getter in (lambda: ctk.ScalingTracker.get_window_scaling(win),
                       lambda: win._get_window_scaling(),
                       lambda: win._window_scaling):
            try:
                s = float(getter())
                if s > 0:
                    return s
            except Exception:  # noqa: BLE001
                continue
        return 1.0

    def _fit_dialog(self, win, want_w, want_h, min_w=420, min_h=340):
        scale = self._window_scale(win)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        avail_w = max(320, (sw * 0.94) / scale)
        avail_h = max(300, (sh * 0.86) / scale)
        w = int(min(want_w, avail_w))
        h = int(min(want_h, avail_h))
        x = int(max(0, (sw - w * scale) / 2))
        y = int(max(0, (sh - h * scale) / 2 - 12))
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.minsize(int(min(min_w, w)), int(min(min_h, h)))
        win.resizable(True, True)
        win.after(220, lambda: self._clamp_to_screen(win))

    def _clamp_to_screen(self, win):
        try:
            if not win.winfo_exists():
                return
            win.update_idletasks()
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            w, h = win.winfo_width(), win.winfo_height()
            x, y = win.winfo_rootx(), win.winfo_rooty()
            new_w = min(w, int(sw * 0.96))
            new_h = min(h, int(sh * 0.90))
            new_x = max(0, min(x, sw - new_w - 8))
            new_y = max(0, min(y, sh - new_h - 40))
            if (new_w, new_h, new_x, new_y) == (w, h, x, y):
                return
            scale = self._window_scale(win)
            win.geometry(f"{int(new_w / scale)}x{int(new_h / scale)}+{new_x}+{new_y}")
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
                        font=self.tree_font, indent=22)
        style.configure("Treeview.Heading", background="#2b2f37", foreground="#dce4ee",
                        relief="flat", font=self.tree_head_font)
        style.map("Treeview", background=[("selected", "#33445a")],
                  foreground=[("selected", "white")])
        style.map("Treeview.Heading", background=[("active", "#3a3f4a")])

    def _wf(self, size):
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
        self.ui_scale = round(min(2.2, max(0.7, self.ui_scale + delta)), 2)
        try:
            ctk.set_widget_scaling(self.ui_scale)
        except Exception:  # noqa: BLE001
            pass
        self._apply_tree_scale()
        if hasattr(self, "web_canvas"):
            self.refresh_web()

    def _popup(self, widget, items):
        """Drop a small menu under `widget`.  items = [(label, fn) | None]."""
        m = tk.Menu(self.root, tearoff=0)
        for it in items:
            if it is None:
                m.add_separator()
            else:
                m.add_command(label=it[0], command=it[1])
        try:
            m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())
        finally:
            m.grab_release()

    # ---------- UI ---------- #
    def _build_ui(self):
        self._build_header()
        self._build_tabs()
        self.status_lbl = ctk.CTkLabel(self.root, text="", anchor="w", text_color="#9aa0aa")
        self.status_lbl.pack(fill="x", padx=16, pady=(0, 8))

    def _build_header(self):
        bar = ctk.CTkFrame(self.root, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=(10, 2))

        self.file_btn = ctk.CTkButton(
            bar, text="File ▾", width=70,
            command=lambda: self._popup(self.file_btn, [
                ("New\tCtrl+N", self.new_file), ("Open…\tCtrl+O", self.open_csv),
                ("Save\tCtrl+S", self.save_csv), ("Save As…", self.save_as), None,
                ("Export Markdown checklist…", lambda: self._do_export("md")),
                ("Export calendar (.ics)…", lambda: self._do_export("ics"))]))
        self.file_btn.pack(side="left", padx=(0, 4), pady=4)
        ctk.CTkButton(bar, text="↶", width=36, command=self.undo).pack(side="left", padx=2)
        ctk.CTkButton(bar, text="↷", width=36, command=self.redo).pack(side="left", padx=2)
        ctk.CTkButton(bar, text="Add many…", width=88,
                      command=self._add_many).pack(side="left", padx=(10, 3))
        self.template_var = tk.StringVar(value="Template…")
        ctk.CTkOptionMenu(bar, variable=self.template_var, width=150,
                          values=list(TEMPLATES.keys()),
                          command=self._insert_template).pack(side="left", padx=3)

        self.gear_btn = ctk.CTkButton(
            bar, text="⚙", width=36,
            command=lambda: self._popup(self.gear_btn, [
                ("Dark theme", lambda: ctk.set_appearance_mode("dark")),
                ("Light theme", lambda: ctk.set_appearance_mode("light")),
                ("System theme", lambda: ctk.set_appearance_mode("system")), None,
                ("Text larger\tCtrl +", lambda: self._bump_text(0.1)),
                ("Text smaller\tCtrl -", lambda: self._bump_text(-0.1))]))
        self.gear_btn.pack(side="right", padx=2)

        q = ctk.CTkFrame(self.root, fg_color="transparent")
        q.pack(fill="x", padx=10, pady=2)

        top = ctk.CTkFrame(q, fg_color="transparent")
        top.pack(fill="x")
        self.quick_var = tk.StringVar()
        e = ctk.CTkEntry(top, textvariable=self.quick_var,
                         placeholder_text="Quick add:  fix XRD ~tomorrow !1 *2 #urgent @PLD")
        e.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=(2, 4))
        e.bind("<Return>", lambda ev: self._quick_add())
        ctk.CTkButton(top, text="Add Task", width=96, command=self._quick_add,
                      **ACCENT).pack(side="left", padx=(4, 0), pady=(2, 4))
        self.details_btn = ctk.CTkButton(
            top, text="Details ▴" if self.details_open else "Details ▾", width=84,
            command=self._toggle_details)
        self.details_btn.pack(side="left", padx=(6, 0), pady=(2, 4))

        # Category / Subcategory / Urgency / Importance: hidden until "Details".
        sel = ctk.CTkFrame(q, fg_color="transparent")
        self.details_frame = sel

        ctk.CTkLabel(sel, text="Category", text_color="#9aa0aa").pack(side="left", padx=(0, 4))
        self.qcat_var = tk.StringVar(value=UNCATEGORIZED)
        self.qcat_box = ctk.CTkComboBox(sel, width=140, variable=self.qcat_var,
                                        values=self._cat_values(),
                                        command=lambda v: self._on_pick_category(v, self.qcat_var))
        self.qcat_box.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(sel, text="Subcategory", text_color="#9aa0aa").pack(side="left", padx=(0, 4))
        self.qsub_var = tk.StringVar(value=UNCATEGORIZED)
        self.qsub_box = ctk.CTkComboBox(sel, width=140, variable=self.qsub_var,
                                        values=self._subcat_values(),
                                        command=lambda v: self._on_pick_subcategory(v, self.qsub_var))
        self.qsub_box.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(sel, text="Urgency", text_color="#9aa0aa").pack(side="left", padx=(0, 4))
        self.qurg_var = tk.StringVar(value="3")
        self.qurg_seg = ctk.CTkSegmentedButton(sel, values=["1", "2", "3", "4", "5"],
                                               variable=self.qurg_var)
        self.qurg_seg.pack(side="left", padx=(0, 10))
        self.qurg_seg.set("3")

        ctk.CTkLabel(sel, text="Importance", text_color="#9aa0aa").pack(side="left", padx=(0, 4))
        self.qimp_var = tk.StringVar(value="3")
        self.qimp_seg = ctk.CTkSegmentedButton(sel, values=["1", "2", "3", "4", "5"],
                                               variable=self.qimp_var)
        self.qimp_seg.pack(side="left", padx=(0, 8))
        self.qimp_seg.set("3")
        if self.details_open:
            sel.pack(fill="x", pady=(0, 4))

    def _toggle_details(self):
        self.details_open = not self.details_open
        if self.details_open:
            self.details_frame.pack(fill="x", pady=(0, 4))
        else:
            self.details_frame.pack_forget()
        self.details_btn.configure(text="Details ▴" if self.details_open else "Details ▾")
        self._save_settings()

    def _build_tabs(self):
        self.tabs = IconTabs(self.root, TAB_ICONS, command=self._on_tab_change)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(4, 4))
        for name in TAB_ICONS:
            self.tabs.add(name)
        self._build_list_tab(self.tabs.tab("List"))
        self._build_web_tab(self.tabs.tab("Map"))
        self._build_board_tab(self.tabs.tab("Board"))
        self._build_matrix_tab(self.tabs.tab("Matrix"))
        self._build_goals_tab(self.tabs.tab("Goals"))
        self._build_values_tab(self.tabs.tab("Values"))
        self._build_analytics_tab(self.tabs.tab("Analytics"))

    # ---------- List tab ---------- #
    def _build_list_tab(self, tab):
        side = ctk.CTkScrollableFrame(tab, width=170, label_text="Smart lists")
        side.pack(side="left", fill="y", padx=(0, 8), pady=4)
        self.smart_buttons = {}
        for name in SMART_LISTS:
            b = ctk.CTkButton(side, text=name, anchor="w",
                              command=lambda n=name: self._set_smart(n))
            b.pack(fill="x", pady=2)
            self.smart_buttons[name] = b

        ctk.CTkLabel(side, text="Categories", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x", pady=(12, 2))
        ctk.CTkButton(side, text="Clear category filter", height=24,
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
        self.search_entry = ctk.CTkEntry(flt, textvariable=self.search_var, width=200,
                                         placeholder_text="title, tags, notes…")
        self.search_entry.pack(side="left", padx=4)
        ctk.CTkButton(flt, text="Edit", width=52, command=self.edit_selected).pack(side="left", padx=(12, 3))
        ctk.CTkButton(flt, text="Bulk", width=52, command=self._bulk_edit).pack(side="left", padx=3)
        ctk.CTkButton(flt, text="+ Sub", width=60, command=self._add_subtask).pack(side="left", padx=3)
        ctk.CTkButton(flt, text="✓ Done", width=70,
                      command=lambda: self._bulk_status("Complete")).pack(side="left", padx=(8, 1))
        ctk.CTkButton(flt, text="↺ Reopen", width=76,
                      command=lambda: self._bulk_status("Open")).pack(side="left", padx=(1, 3))
        ctk.CTkButton(flt, text="Archive", width=64,
                      command=self._bulk_archive).pack(side="left", padx=3)
        ctk.CTkButton(flt, text="Delete", width=60, text_color="#ff8787",
                      command=self._bulk_delete).pack(side="left", padx=3)
        ctk.CTkButton(flt, text="⊟", width=34,
                      command=lambda: self._set_all_subtasks_open(False)
                      ).pack(side="left", padx=(12, 2))
        ctk.CTkButton(flt, text="⊞", width=34,
                      command=lambda: self._set_all_subtasks_open(True)
                      ).pack(side="left", padx=2)
        self.cols_btn = ctk.CTkButton(flt, text="Columns ▾", width=88,
                                      command=self._columns_menu)
        self.cols_btn.pack(side="right", padx=(6, 8))

        saved = self.settings.get("visible_cols")
        vis = [c for c in (saved or DEFAULT_VISIBLE_COLS) if c in TREE_COLUMNS] or list(DEFAULT_VISIBLE_COLS)
        self._col_vars = {c: tk.BooleanVar(value=(c in vis)) for c in TREE_COLUMNS}

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
        self._apply_columns(save=False)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        for u, col in URGENCY_COLORS.items():
            self.tree.tag_configure(f"u{u}", foreground=col)
        self.tree.tag_configure("done", foreground="#6c757d")
        self.tree.tag_configure("overdue", background="#4a2530", foreground="#ff8787")
        self.tree.tag_configure("blocked", foreground="#7d848f")
        self.tree.tag_configure("drop", background="#2f6f4f")
        self.tree.bind("<Double-1>", self._on_tree_double)
        self.tree.bind("<Delete>", lambda e: self._bulk_delete())
        self.tree.bind("<space>", self._on_space)
        self.tree.bind("<Button-3>", self._tree_context)
        # drag a row onto another row to make it a subtask
        self.tree.bind("<ButtonPress-1>", self._drag_press, add="+")
        self.tree.bind("<B1-Motion>", self._drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._drag_release, add="+")

    def _visible_cols(self):
        cols = [c for c in TREE_COLUMNS if self._col_vars[c].get()]
        return cols or ["Category"]

    def _apply_columns(self, save=True):
        if not any(v.get() for v in self._col_vars.values()):
            self._col_vars["Category"].set(True)      # never hide every column
        self.tree.configure(displaycolumns=self._visible_cols())
        if save:
            self._save_settings()

    def _reset_columns(self):
        for c, v in self._col_vars.items():
            v.set(c in DEFAULT_VISIBLE_COLS)
        self._apply_columns()

    def _columns_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        for c in TREE_COLUMNS:
            m.add_checkbutton(label=c, variable=self._col_vars[c], command=self._apply_columns)
        m.add_separator()
        m.add_command(label="Reset to default", command=self._reset_columns)
        try:
            m.tk_popup(self.cols_btn.winfo_rootx(),
                       self.cols_btn.winfo_rooty() + self.cols_btn.winfo_height())
        finally:
            m.grab_release()

    def _build_category_filter(self):
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

    # ---------- Map tab (sunburst, "disk usage" style) ---------- #
    def _build_web_tab(self, tab):
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 2))
        ctk.CTkLabel(top, text="Color", text_color="#9aa0aa").pack(side="left", padx=(4, 4))
        self.web_color_var = tk.StringVar(value="Urgency")
        seg = ctk.CTkSegmentedButton(
            top, values=["Urgency", "Importance", "Category", "Motivation"],
            variable=self.web_color_var, command=lambda v: self.refresh_web())
        seg.pack(side="left")
        seg.set("Urgency")
        ctk.CTkLabel(top, text="Size", text_color="#9aa0aa").pack(side="left", padx=(14, 4))
        self.web_size_var = tk.StringVar(value="Tasks")
        sz = ctk.CTkSegmentedButton(top, values=["Tasks", "Hours"],
                                    variable=self.web_size_var,
                                    command=lambda v: self.refresh_web())
        sz.pack(side="left")
        sz.set("Tasks")
        self.web_done_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(top, text="Show completed", variable=self.web_done_var,
                        checkbox_width=18, checkbox_height=18,
                        command=self.refresh_web).pack(side="left", padx=(14, 0))
        self.map_legend = ctk.CTkFrame(top, fg_color="transparent")
        self.map_legend.pack(side="right", padx=4)

        lab = ctk.CTkFrame(tab, fg_color="transparent")
        lab.pack(fill="x", padx=8, pady=(0, 2))
        ctk.CTkLabel(lab, text="Labels", text_color="#9aa0aa").pack(side="left", padx=(4, 6))
        self._map_all_btn = ctk.CTkButton(lab, text="Label all", width=78, command=self._map_label_all)
        self._map_all_btn.pack(side="left", padx=2)
        ctk.CTkLabel(lab, text="ring", text_color="#9aa0aa").pack(side="left", padx=(10, 3))
        for k in range(1, 9):
            b = ctk.CTkButton(lab, text=str(k), width=30,
                              command=lambda kk=k: self._map_toggle_layer(kk))
            b.pack(side="left", padx=1)
            self._map_layer_btns[k] = b
        ctk.CTkButton(lab, text="Clear", width=54,
                      command=self._map_clear_labels).pack(side="left", padx=(8, 2))
        ctk.CTkButton(lab, text="⤒ Up", width=54,
                      command=self._map_zoom_out).pack(side="left", padx=(8, 2))
        self.map_info = ctk.CTkLabel(lab, text="", anchor="w", text_color="#9aa0aa")
        self.map_info.pack(side="left", padx=10, fill="x", expand=True)

        self.web_canvas = tk.Canvas(tab, bg=MAP_BG, highlightthickness=0)
        self.web_canvas.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.web_canvas.bind("<Configure>", lambda e: self._map_schedule())
        self.web_canvas.bind("<Button-1>", self._on_map_click)
        self.web_canvas.bind("<Double-1>", self._on_map_double)
        self.web_canvas.bind("<Button-3>", self._on_map_menu)
        self.web_canvas.bind("<Motion>", self._on_map_motion)
        self.web_canvas.bind("<Leave>", lambda e: self.web_canvas.delete("tip"))

    # -- label controls -- #
    def _map_label_all(self):
        self._map_all = not self._map_all
        self.refresh_web()

    def _map_toggle_layer(self, k):
        self._map_all = False
        if k in self._map_layers:
            self._map_layers.discard(k)
        else:
            self._map_layers.add(k)
        self.refresh_web()

    def _map_clear_labels(self):
        self._map_all = False
        self._map_layers.clear()
        self._map_sel = None
        self.refresh_web()

    def _map_zoom_out(self):
        node = getattr(self, "_map_focus_node", None)
        if node and node.get("parent"):
            self._map_focus = node["parent"]
            self._map_sel = None
            self._map_zoom_ts = time.time()
            self.refresh_web()

    def _map_schedule(self):
        if self._map_job:
            try:
                self.root.after_cancel(self._map_job)
            except Exception:  # noqa: BLE001
                pass
        self._map_job = self.root.after(80, self.refresh_web)

    def _sync_map_controls(self, mode):
        for k, b in self._map_layer_btns.items():
            b.configure(fg_color=ON_BG if (self._map_all or k in self._map_layers) else BTN_BG)
        self._map_all_btn.configure(fg_color=ON_BG if self._map_all else BTN_BG)
        if mode == self._map_legend_mode:
            return
        self._map_legend_mode = mode
        for w in self.map_legend.winfo_children():
            w.destroy()
        if mode in ("Urgency", "Importance"):
            lead = f"each ring shows its most {mode.lower()} item:"
            entries = [(URGENCY_COLORS[k], ("1 (top)" if k == 1 else "5 (low)" if k == 5 else str(k)))
                       for k in range(1, 6)]
        elif mode == "Motivation":
            lead = ""
            entries = [(MOTIVATION_COLORS["Obligation"], "Obligation"),
                       (MOTIVATION_COLORS["Joy"], "Joy"), (MOTIVATION_COLORS[""], "unset")]
        else:
            lead, entries = "each category has its own hue", []
        if lead:
            ctk.CTkLabel(self.map_legend, text=lead, text_color="#9aa0aa").pack(side="left", padx=(0, 6))
        for color, text in entries:
            ctk.CTkLabel(self.map_legend, text="●", text_color=color, width=12).pack(side="left")
            ctk.CTkLabel(self.map_legend, text=text, text_color="#9aa0aa").pack(side="left", padx=(0, 6))

    # -- tree building -- #
    def _map_build_tree(self):
        vdf = self.vdf
        use_hours = self.web_size_var.get() == "Hours"
        incl_done = bool(self.web_done_var.get())
        act = vdf[vdf["Archived"] != "Yes"]
        if not incl_done:
            act = act[act["Status"] != "Complete"]
        rows = {int(r["ID"]): r for _, r in act.iterrows()}
        nodes = {}
        for i, r in rows.items():
            hrs = 1.0
            if use_hours:
                try:
                    hrs = float(str(r["Estimate"]).strip())
                except ValueError:
                    hrs = 1.0
                if hrs <= 0:
                    hrs = 1.0
            mot = coerce_motivation(r["Motivation"])
            nodes[i] = {"key": ("task", i), "kind": "task", "id": i, "name": str(r["Task"]),
                        "children": [], "u": coerce_rating(r["Urgency"]),
                        "i": coerce_rating(r["Importance"]), "done": r["Status"] == "Complete",
                        "mot": {mot: 1}, "leaf_w": hrs, "status": r["Status"],
                        "due": str(r["Due Date"]).strip()}
        root = {"key": ("root",), "kind": "root", "name": "All", "children": [],
                "parent": None, "done": False}
        cats = {}

        def nearest(i):
            p, seen = self._pmap.get(i), set()
            while p is not None and p not in seen:
                if p in nodes:
                    return p
                seen.add(p)
                p = self._pmap.get(p)
            return None

        for i, n in nodes.items():
            p = nearest(i)
            if p is not None:
                nodes[p]["children"].append(n)
                n["parent"] = ("task", p)
            else:
                cname = str(rows[i]["Category"]).strip() or UNCATEGORIZED
                c = cats.get(cname)
                if c is None:
                    c = {"key": ("cat", cname), "kind": "cat", "name": cname, "children": [],
                         "parent": ("root",), "done": False}
                    cats[cname] = c
                c["children"].append(n)
                n["parent"] = c["key"]
        root["children"] = list(cats.values())

        def agg(n):
            kids = n["children"]
            if not kids:
                n["w"] = n.get("leaf_w", 1.0)
                n.setdefault("u", 3)
                n.setdefault("i", 3)
                n.setdefault("mot", {})
                return
            for c in kids:
                agg(c)
            n["w"] = sum(c["w"] for c in kids)
            live = [c for c in kids if not c["done"]] or kids
            n["u"] = min(c["u"] for c in live)
            n["i"] = min(c["i"] for c in live)
            mot = {}
            for c in kids:
                for k, v in c["mot"].items():
                    mot[k] = mot.get(k, 0) + v
            n["mot"] = mot
            kids.sort(key=lambda c: (-c["w"], c["name"].lower()))

        agg(root)
        cat_color = {name: idx for idx, name in enumerate(sorted(cats))}
        index = {}

        def walk(n, absd, cidx):
            n["abs"] = absd
            if n["kind"] == "cat":
                cidx = cat_color[n["name"]]
            n["cidx"] = cidx
            index[n["key"]] = n
            for c in n["children"]:
                walk(c, absd + 1, cidx)

        walk(root, 0, 0)
        return root, index

    def _map_color(self, n, mode):
        if mode == "Urgency":
            base = URGENCY_COLORS[n["u"]]
        elif mode == "Importance":
            base = URGENCY_COLORS[n["i"]]
        elif mode == "Motivation":
            mot = n.get("mot", {})
            obl, joy = mot.get("Obligation", 0), mot.get("Joy", 0)
            if obl == 0 and joy == 0:
                base = MOTIVATION_COLORS[""]
            else:
                base = MOTIVATION_COLORS["Obligation" if obl >= joy else "Joy"]
        else:
            base = CATEGORY_PALETTE[n["cidx"] % len(CATEGORY_PALETTE)]
            base = blend(base, "#000000", min(0.55, 0.11 * (n["abs"] - 1)))
        if n.get("done"):
            base = blend(base, MAP_BG, 0.55)
        return base

    @staticmethod
    def _annulus(cx, cy, r_in, r_out, a0, a1):
        steps = max(2, int((a1 - a0) / (math.pi / 90)) + 2)
        pts = []
        for k in range(steps + 1):
            a = a0 + (a1 - a0) * k / steps
            pts += [cx + r_out * math.cos(a), cy + r_out * math.sin(a)]
        for k in range(steps, -1, -1):
            a = a0 + (a1 - a0) * k / steps
            pts += [cx + r_in * math.cos(a), cy + r_in * math.sin(a)]
        return pts

    @staticmethod
    def _fit_text(font, s, avail):
        if avail < 14:
            return ""
        if font.measure(s) <= avail:
            return s
        for k in range(len(s) - 1, 1, -1):
            t = s[:k].rstrip() + "…"
            if font.measure(t) <= avail:
                return t
        return ""

    def _map_fmt(self, w):
        if self.web_size_var.get() == "Hours":
            return f"{w:g} h"
        n = int(round(w))
        return f"{n} task{'s' if n != 1 else ''}"

    def refresh_web(self):
        if not hasattr(self, "web_canvas") or self._current_tab() != "Map":
            return
        cv = self.web_canvas
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 80 or h < 80:
            self.root.after(80, self.refresh_web)
            return
        cv.delete("all")
        self._map_hit = []
        self._map_hover = None
        mode = self.web_color_var.get()
        self._sync_map_controls(mode)
        root, index = self._map_build_tree()
        if not root["children"]:
            cv.create_text(w / 2, h / 2, fill="#80868f", font=("Segoe UI", self._wf(14)),
                           text="No tasks yet — add some and your map appears here.\n"
                                "Subtasks become outer rings.")
            self.map_info.configure(text="")
            return
        focus = index.get(self._map_focus)
        if focus is None or not focus["children"]:
            focus = root
            self._map_focus = root["key"]
        self._map_focus_node = focus
        self._map_index = index

        font = tkfont.Font(family="Segoe UI", size=self._wf(9))
        fh = font.metrics("linespace")
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 12
        r0 = max(36.0, R * 0.17)

        def depth(n):
            return 0 if not n["children"] else 1 + max(depth(c) for c in n["children"])

        maxd = depth(focus)
        thick = min(R * 0.24, (R - r0) / max(1, maxd))
        self._map_geo = (cx, cy, r0)

        arcs = []

        def lay(n, a0, a1, d):
            if d >= 1:
                n["g"] = (r0 + (d - 1) * thick, r0 + d * thick, a0, a1)
                n["d"] = d
                arcs.append(n)
            tot = sum(c["w"] for c in n["children"]) or 1.0
            a = a0
            for c in n["children"]:
                span = (a1 - a0) * c["w"] / tot
                lay(c, a, a + span, d + 1)
                a += span

        lay(focus, -math.pi / 2, 3 * math.pi / 2, 0)

        cv.create_oval(cx - r0, cy - r0, cx + r0, cy + r0, fill="#2b2f37",
                       outline="#4b5563", width=2)
        for n in arcs:
            r_in, r_out, a0, a1 = n["g"]
            if (a1 - a0) * (r_in + r_out) / 2 < 1.0:
                n["item"] = None
                n["vis"] = False
                continue
            n["vis"] = True
            n["fill"] = self._map_color(n, mode)
            n["item"] = cv.create_polygon(self._annulus(cx, cy, r_in, r_out, a0, a1),
                                          fill=n["fill"], outline=MAP_EDGE, width=1)
            self._map_hit.append(n)
        cv.create_text(cx, cy, fill="#e8edf4", font=("Segoe UI", self._wf(9), "bold"),
                       width=r0 * 1.7, justify="center",
                       text=f"{focus['name']}\n{self._map_fmt(focus['w'])}")

        self._map_draw_labels(cv, arcs, font, fh, cx, cy, w, h)
        sel = index.get(self._map_sel)
        if sel and sel.get("item"):
            cv.itemconfigure(sel["item"], outline="#ffffff", width=2)

        chain, k = [], focus["key"]
        while k is not None and k in index:
            chain.append(index[k]["name"])
            k = index[k]["parent"]
        info = " › ".join(reversed(chain))
        if sel:
            info += (f"    |    selected: {sel['name']} — {self._map_fmt(sel['w'])}, "
                     f"top urgency U{sel['u']}, top importance I{sel['i']}")
        else:
            info += "    |    click = select · double-click = zoom in / edit · centre = zoom out · right-click = menu"
        self.map_info.configure(text=info)

    def _map_wants_label(self, n):
        return self._map_all or n["d"] in self._map_layers or n["key"] == self._map_sel

    def _map_draw_labels(self, cv, arcs, font, fh, cx, cy, w, h):
        outside = []
        for n in arcs:
            if not n.get("vis") or not self._map_wants_label(n):
                continue
            r_in, r_out, a0, a1 = n["g"]
            rm, am = (r_in + r_out) / 2, (a0 + a1) / 2
            arc_px = (a1 - a0) * rm
            txt = ""
            if arc_px >= fh + 2:
                txt = self._fit_text(font, n["name"], (r_out - r_in) - 8)
            if txt:
                ang = -math.degrees(am)
                if math.cos(am) < 0:
                    ang += 180
                cv.create_text(cx + rm * math.cos(am), cy + rm * math.sin(am), text=txt,
                               angle=ang, fill=text_on(n["fill"]), font=font, tags="lbl")
            else:
                n["ax"], n["ay"] = cx + rm * math.cos(am), cy + rm * math.sin(am)
                outside.append(n)
        # leader-line labels at the window edges, spread out so they don't overlap
        sp = fh + 6
        cap = max(1, int((h - 20) / sp))
        for side in ("L", "R"):
            group = [n for n in outside if (n["ax"] < cx) == (side == "L")]
            if len(group) > cap:
                group = sorted(group, key=lambda n: -n["w"])[:cap]
            group.sort(key=lambda n: n["ay"])
            last = -1e9
            for n in group:
                n["ly"] = max(n["ay"], last + sp, 10)
                last = n["ly"]
            limit = h - 10
            for n in reversed(group):
                n["ly"] = min(n["ly"], limit)
                limit = n["ly"] - sp
            for n in group:
                if n["ly"] < 6:
                    continue
                name = n["name"] if len(n["name"]) <= 30 else n["name"][:29] + "…"
                if side == "L":
                    t = cv.create_text(6, n["ly"], text=name, anchor="w", fill="#e8edf4",
                                       font=font, tags="lbl")
                else:
                    t = cv.create_text(w - 6, n["ly"], text=name, anchor="e", fill="#e8edf4",
                                       font=font, tags="lbl")
                bb = cv.bbox(t)
                ex = bb[2] + 3 if side == "L" else bb[0] - 3
                cv.create_line(n["ax"], n["ay"], ex, n["ly"], fill="#8a919c", tags="lbl")
                cv.create_oval(n["ax"] - 2, n["ay"] - 2, n["ax"] + 2, n["ay"] + 2,
                               fill="#e8edf4", outline="", tags="lbl")
                r = cv.create_rectangle(bb[0] - 3, bb[1] - 1, bb[2] + 3, bb[3] + 1,
                                        fill="#0b0c0e", outline="", tags="lbl")
                cv.tag_lower(r, t)
        cv.tag_raise("lbl")

    # -- map interaction -- #
    def _map_hit_test(self, x, y):
        cx, cy, r0 = self._map_geo
        dx, dy = x - cx, y - cy
        r = math.hypot(dx, dy)
        if r <= r0:
            return "center"
        rel = (math.atan2(dy, dx) + math.pi / 2) % (2 * math.pi)
        for n in self._map_hit:
            r_in, r_out, a0, a1 = n["g"]
            if r_in <= r <= r_out and (a0 + math.pi / 2) <= rel < (a1 + math.pi / 2):
                return n
        return None

    def _map_style(self, n, hover=False):
        if not n or not n.get("item"):
            return
        if hover or n["key"] == self._map_sel:
            self.web_canvas.itemconfigure(n["item"], outline="#ffffff", width=2)
            self.web_canvas.tag_raise(n["item"])
            self.web_canvas.tag_raise("lbl")
        else:
            self.web_canvas.itemconfigure(n["item"], outline=MAP_EDGE, width=1)

    def _on_map_motion(self, e):
        if not self._map_hit:
            return
        cv = self.web_canvas
        hit = self._map_hit_test(e.x, e.y)
        node = hit if isinstance(hit, dict) else None
        cv.delete("tip")
        if node is not self._map_hover:
            self._map_style(self._map_hover)
            self._map_hover = node
            self._map_style(node, hover=True)
        cv.configure(cursor="hand2" if (node or (hit == "center" and self._map_focus != ("root",))) else "")
        if not node:
            return
        if node["kind"] == "task" and not node["children"]:
            sub = f"U{node['u']} · I{node['i']} · {node['status']}"
            if node["due"]:
                sub += f" · due {node['due']}"
        else:
            sub = (f"{self._map_fmt(node['w'])} · most urgent U{node['u']} · "
                   f"most important I{node['i']}")
        t = cv.create_text(e.x + 14, e.y + 14, anchor="nw", fill="#f1f3f5",
                           font=("Segoe UI", self._wf(9)), text=f"{node['name']}\n{sub}",
                           tags="tip")
        bb = cv.bbox(t)
        dx = min(0, cv.winfo_width() - bb[2] - 8)
        dy = min(0, cv.winfo_height() - bb[3] - 8)
        if dx or dy:
            cv.move(t, dx, dy)
            bb = cv.bbox(t)
        r = cv.create_rectangle(bb[0] - 5, bb[1] - 3, bb[2] + 5, bb[3] + 3,
                                fill="#0b0c0e", outline="#4b5563", tags="tip")
        cv.tag_lower(r, t)

    def _on_map_click(self, e):
        hit = self._map_hit_test(e.x, e.y)
        if hit == "center":
            if time.time() - self._map_zoom_ts > 0.45:
                self._map_zoom_out()
            return
        self._map_sel = hit["key"] if isinstance(hit, dict) else None
        self.refresh_web()

    def _on_map_double(self, e):
        hit = self._map_hit_test(e.x, e.y)
        if not isinstance(hit, dict):
            return
        if hit["children"]:
            self._map_focus = hit["key"]
            self._map_sel = None
            self._map_zoom_ts = time.time()
            self.refresh_web()
        elif hit["kind"] == "task":
            self._edit_by_id(hit["id"])

    def _on_map_menu(self, e):
        hit = self._map_hit_test(e.x, e.y)
        node = hit if isinstance(hit, dict) else None
        m = tk.Menu(self.root, tearoff=0)
        if node:
            if node["children"]:
                m.add_command(label="Zoom into this", command=lambda: self._map_zoom_to(node))
            if node["kind"] == "task":
                m.add_command(label="Edit task…", command=lambda: self._edit_by_id(node["id"]))
            m.add_command(label="Show in List", command=lambda: self._map_show_in_list(node))
            m.add_separator()
        if self._map_focus != ("root",):
            m.add_command(label="Zoom out", command=self._map_zoom_out)
        m.add_command(label="Label all rings", command=self._map_label_all)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _map_zoom_to(self, node):
        self._map_focus = node["key"]
        self._map_sel = None
        self._map_zoom_ts = time.time()
        self.refresh_web()

    def _map_show_in_list(self, n):
        try:
            self.tabs.set("List")
        except Exception:  # noqa: BLE001
            pass
        if n["kind"] == "cat":
            for c, var in self.cat_filter_vars.items():
                var.set(c == n["name"])
        self.refresh_all()
        if n["kind"] == "task":
            iid = str(n["id"])
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)

    def _edit_by_id(self, _id):
        mask = self.df["ID"] == _id
        if mask.any():
            self._open_edit_dialog(_id, self.df[mask].iloc[0])

    # ---------- Analytics tab ---------- #
    def _build_analytics_tab(self, tab):
        self.analytics_text = ctk.CTkTextbox(tab, height=160)
        self.analytics_text.pack(fill="x", padx=8, pady=8)
        self.analytics_chart = ctk.CTkFrame(tab, fg_color="transparent")
        self.analytics_chart.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ---------- category dropdown (add-new lives inside) ---------- #
    def _cat_values(self):
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
                    "Date Created": today_str(), "Archived": "", "Parent": ""})
        row.update(kw)
        row["Urgency"] = coerce_rating(row["Urgency"])
        row["Importance"] = coerce_rating(row["Importance"])
        row["Horizon"] = coerce_horizon(row.get("Horizon", ""))
        row["Motivation"] = coerce_motivation(row.get("Motivation", ""))
        row["Category"] = str(row.get("Category", "")).strip() or UNCATEGORIZED
        row["Subcategory"] = str(row.get("Subcategory", "")).strip() or UNCATEGORIZED
        return row

    def _append(self, row):
        self.df.loc[len(self.df)] = [row.get(c, "") for c in CSV_COLUMNS]

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
        self.qcat_var.set(UNCATEGORIZED)
        self.qsub_var.set(UNCATEGORIZED)
        self._mark_dirty()
        self._collect_categories()
        self.refresh_all()

    def _add_subtask(self):
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Add subtask", "Select a task in the list first.")
            return
        pid = ids[0]
        dlg = ctk.CTkInputDialog(
            text=f"New subtask under “{self._names.get(pid, '')}”\n"
                 "(quick-add tokens work:  ~tomorrow  !1  *2  #tag)",
            title="Add subtask")
        text = (dlg.get_input() or "").strip()
        if not text:
            return
        self._snapshot()
        prow = self.df[self.df["ID"] == pid].iloc[0]
        p = parse_quick_add(text, self.categories)
        self._append(self._new_task(
            Task=p["Task"] or text, Parent=str(pid),
            Category=p["Category"] or prow["Category"], Subcategory=prow["Subcategory"],
            Horizon=prow["Horizon"], Motivation=prow["Motivation"], Tags=p["Tags"],
            Urgency=p["Urgency"] or 3, Importance=p["Importance"] or 3,
            **{"Due Date": p["Due Date"]}))
        self._open_map[str(pid)] = True
        self._mark_dirty()
        self._collect_categories()
        self.refresh_all()

    def _add_many(self):
        win = ctk.CTkToplevel(self.root)
        win.title("Add many tasks")
        win.transient(self.root)
        self._fit_dialog(win, 680, 620, min_w=520, min_h=360)
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
                win.destroy()
                return
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
            self._mark_dirty()
            self._collect_categories()
            self.refresh_all()
            win.destroy()

        ctk.CTkButton(btns, text="Cancel",
                      command=win.destroy).pack(side="right")
        ctk.CTkButton(btns, text="Add tasks", command=add, **ACCENT).pack(side="right", padx=8)
        win.bind("<Escape>", lambda e: win.destroy())

    def _insert_template(self, name):
        self.template_var.set("Template…")
        items = TEMPLATES.get(name)
        if not items:
            return
        self._snapshot()
        for it in items:
            self._append(self._new_task(**it))
        self._mark_dirty()
        self._collect_categories()
        self.refresh_all()

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
        had_legacy = ("Subtasks" in raw.columns and
                      raw["Subtasks"].astype(str).str.strip().ne("").any())
        self.df = normalize_frame(raw)
        self.current_file = path
        self._last_backup_ts = 0.0
        self._map_focus = ("root",)
        self._map_sel = None
        self._recompute()
        # Old files get their subtasks converted -> save (a backup is written first).
        self._mark_dirty(bool(had_legacy))

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

    def _do_export(self, kind, win=None):
        if win is not None:
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
            b.configure(fg_color=("#3b4252" if n == self.smart else "transparent"))

    def _focus_search(self):
        try:
            self.tabs.set("List")
            self.search_entry.focus_set()
        except Exception:  # noqa: BLE001
            pass

    # ---------- selection / bulk ---------- #
    def _selected_ids(self):
        return [int(i) for i in self.tree.selection() if str(i).isdigit()]

    def _on_space(self, e):
        ids = self._selected_ids()
        if ids:
            stat = dict(zip(self.df["ID"], self.df["Status"]))
            all_done = all(stat.get(i) == "Complete" for i in ids)
            self._bulk_status("Open" if all_done else "Complete")
        return "break"

    def _bulk_status(self, status):
        ids = self._selected_ids()
        if not ids:
            return
        if status == "Complete":
            stat = dict(zip(self.df["ID"], self.df["Status"]))
            extra = []
            for i in ids:
                for d in descendants(self._kids, i):
                    if d not in ids and d not in extra and stat.get(d) != "Complete":
                        extra.append(d)
            if extra:
                ans = messagebox.askyesnocancel(
                    "Complete", f"{len(extra)} unfinished subtask(s) sit under the selection.\n"
                                "Mark them complete too?")
                if ans is None:
                    return
                if ans:
                    ids = ids + extra
        self._snapshot()
        for _id in ids:
            self._apply_status(_id, status, snapshot=False)
        self._mark_dirty()
        self.refresh_all()

    def _apply_status(self, _id, status, snapshot=True):
        if snapshot:
            self._snapshot()
        mask = self.df["ID"] == _id
        if not mask.any():
            return
        task = self.df[mask].iloc[0].to_dict()
        was_done = task["Status"] == "Complete"
        self.df.loc[mask, "Status"] = status
        if status == "Complete":
            self.df.loc[mask, "Date Completed"] = today_str()
            if not was_done and str(task.get("Recurrence", "")).strip():
                nxt = next_occurrence(task)
                nxt["ID"] = self._next_id()
                self._append(nxt)
        else:
            self.df.loc[mask, "Date Completed"] = ""
        if snapshot:
            self._mark_dirty()
            self.refresh_all()

    def _bulk_edit(self):
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Bulk edit", "Select one or more tasks first "
                                             "(Ctrl/Shift-click to multi-select).")
            return
        win = ctk.CTkToplevel(self.root)
        win.title(f"Bulk edit — {len(ids)} task(s)")
        win.transient(self.root)
        self._fit_dialog(win, 460, 560, min_w=400, min_h=340)
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
        start_var = tk.StringVar(value="")
        add_row("Don't start before", lambda p: ctk.CTkEntry(p, textvariable=start_var), start_var)
        tag_var = tk.StringVar(value="")
        add_row("Tags (replace)", lambda p: ctk.CTkEntry(p, textvariable=tag_var), tag_var)

        def apply():
            changes = {f: var for f, (en, var) in rows.items() if en.get()}
            if not changes:
                win.destroy()
                return
            for key in ("Due Date (YYYY-MM-DD)", "Don't start before"):
                if key in changes and not valid_date(changes[key].get()):
                    messagebox.showwarning("Bulk edit",
                                           f"{key} must be YYYY-MM-DD or blank.", parent=win)
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
            if "Don't start before" in changes:
                self.df.loc[mask, "Start Date"] = changes["Don't start before"].get().strip()
            if "Tags (replace)" in changes:
                self.df.loc[mask, "Tags"] = changes["Tags (replace)"].get().strip()
            if "Status" in changes:
                for _id in ids:
                    self._apply_status(_id, changes["Status"].get(), snapshot=False)
            self._mark_dirty()
            self._collect_categories()
            self.refresh_all()
            win.destroy()

        ctk.CTkButton(btns, text="Cancel",
                      command=win.destroy).pack(side="right")
        ctk.CTkButton(btns, text="Apply", command=apply, **ACCENT).pack(side="right", padx=8)
        win.bind("<Escape>", lambda e: win.destroy())

    def _with_subtree(self, ids):
        out = list(ids)
        for i in ids:
            for d in descendants(self._kids, i):
                if d not in out:
                    out.append(d)
        return out

    def _bulk_archive(self):
        ids = self._selected_ids()
        if not ids:
            return
        self._snapshot()
        self.df.loc[self.df["ID"].isin(self._with_subtree(ids)), "Archived"] = "Yes"
        self._mark_dirty()
        self.refresh_all()

    def _bulk_delete(self):
        ids = self._selected_ids()
        if not ids:
            return
        sub = [d for d in self._with_subtree(ids) if d not in ids]
        keep_subs = False
        if sub:
            ans = messagebox.askyesnocancel(
                "Delete", f"Delete {len(ids)} task(s)?\n\n{len(sub)} subtask(s) sit underneath.\n"
                          "Yes = delete them too\nNo = keep them (they move up a level)")
            if ans is None:
                return
            if ans:
                ids = ids + sub
            else:
                keep_subs = True
        elif not messagebox.askyesno("Delete", f"Delete {len(ids)} task(s)?"):
            return
        self._snapshot()
        gone = set(ids)
        if keep_subs:
            for c, p in list(self._pmap.items()):
                if c in gone or p not in gone:
                    continue
                while p in gone:
                    p = self._pmap.get(p)
                self.df.loc[self.df["ID"] == c, "Parent"] = "" if p is None else str(p)
        self.df = self.df[~self.df["ID"].isin(gone)].reset_index(drop=True)
        self._mark_dirty()
        self.refresh_all()

    # ---------- re-parenting (drag & drop, menus) ---------- #
    def _reparent(self, ids, new_parent):
        """Make `ids` children of `new_parent` (None = top level). Refuses cycles."""
        kids = self._kids
        ids = [i for i in ids if i != new_parent and
               (new_parent is None or new_parent not in descendants(kids, i))]
        idset = set(ids)
        # items whose ancestor is also being moved travel with that ancestor
        def has_moving_ancestor(i):
            p, guard = self._pmap.get(i), 0
            while p is not None and guard < 50:
                if p in idset:
                    return True
                p = self._pmap.get(p)
                guard += 1
            return False
        ids = [i for i in ids if not has_moving_ancestor(i)]
        ids = [i for i in ids if self._pmap.get(i) != new_parent]
        if not ids:
            return False
        self._snapshot()
        mask = self.df["ID"].isin(ids)
        self.df.loc[mask, "Parent"] = "" if new_parent is None else str(new_parent)
        if new_parent is not None:
            prow = self.df[self.df["ID"] == new_parent].iloc[0]
            for col in ("Category", "Subcategory"):
                blank = mask & (self.df[col].astype(str).str.strip().isin(["", UNCATEGORIZED]))
                self.df.loc[blank, col] = prow[col]
            self._open_map[str(new_parent)] = True
        self._mark_dirty()
        self._collect_categories()
        self.refresh_all()
        return True

    def _drag_press(self, e):
        self._drag = None
        try:
            if self.tree.identify_region(e.x, e.y) not in ("tree", "cell"):
                return
            iid = self.tree.identify_row(e.y)
            if not iid or not str(iid).isdigit():
                return
            if "indicator" in str(self.tree.identify_element(e.x, e.y)):
                return
        except Exception:  # noqa: BLE001
            return
        sel = [str(i) for i in self.tree.selection() if str(i).isdigit()]
        ids = [int(i) for i in sel] if iid in sel else [int(iid)]
        self._drag = {"ids": ids, "x": e.x, "y": e.y, "active": False,
                      "target": None, "tags": ()}

    def _drag_clear_target(self):
        d = self._drag
        if d and d["target"] and self.tree.exists(d["target"]):
            self.tree.item(d["target"], tags=d["tags"])
        if d:
            d["target"] = None

    def _drag_motion(self, e):
        d = self._drag
        if not d:
            return
        if not d["active"]:
            if abs(e.x - d["x"]) + abs(e.y - d["y"]) < 8:
                return
            d["active"] = True
            self.tree.configure(cursor="hand2")
        tgt = self.tree.identify_row(e.y) or None
        if tgt is not None and not str(tgt).isdigit():
            tgt = None
        if tgt == d["target"]:
            return
        self._drag_clear_target()
        d["target"] = tgt
        if tgt:
            tags = self.tree.item(tgt, "tags")
            tags = tuple(tags.split()) if isinstance(tags, str) else tuple(tags or ())
            d["tags"] = tags
            self.tree.item(tgt, tags=("drop",) + tags)
            self.status_lbl.configure(
                text=f"Drop to make {len(d['ids'])} item(s) a subtask of “{self._names.get(int(tgt), '')}”")
        else:
            self.status_lbl.configure(text="Drop on empty space to make top-level")

    def _drag_release(self, e):
        d = self._drag
        self._drag = None
        if not d or not d["active"]:
            return
        self._drag = d
        self._drag_clear_target()
        self._drag = None
        self.tree.configure(cursor="")
        self._update_status_bar()
        tgt = self.tree.identify_row(e.y)
        if tgt and str(tgt).isdigit():
            self._reparent(d["ids"], int(tgt))
        elif (not tgt and 0 <= e.x <= self.tree.winfo_width()
              and 0 <= e.y <= self.tree.winfo_height()):
            self._reparent(d["ids"], None)

    def _tree_context(self, e):
        row = self.tree.identify_row(e.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        ids = self._selected_ids()
        m = tk.Menu(self.root, tearoff=0)
        if ids:
            m.add_command(label="Edit…", command=self.edit_selected)
            m.add_command(label="Add subtask…", command=self._add_subtask)
            m.add_command(label="Move to top level", command=lambda: self._reparent(ids, None))
            m.add_separator()
            m.add_command(label="Wait for task(s) to finish…", command=self._wait_for_dialog)
            m.add_command(label="Don't start until date…", command=self._wait_until_dialog)
            m.add_command(label="Clear waiting", command=self._clear_waiting)
            m.add_separator()
            m.add_command(label="Mark complete", command=lambda: self._bulk_status("Complete"))
            m.add_command(label="Reopen", command=lambda: self._bulk_status("Open"))
            m.add_command(label="Archive", command=self._bulk_archive)
            m.add_command(label="Delete", command=self._bulk_delete)
        else:
            m.add_command(label="Expand all", command=lambda: self._set_all_subtasks_open(True))
            m.add_command(label="Collapse all", command=lambda: self._set_all_subtasks_open(False))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # ---------- waiting / dependencies ---------- #
    def _pick_tasks_dialog(self, parent, initial, exclude, on_ok):
        win = ctk.CTkToplevel(parent)
        win.title("Wait for…")
        win.transient(parent)
        self._fit_dialog(win, 460, 540, min_w=380, min_h=320)
        win.after(120, win.grab_set)
        ctk.CTkLabel(win, justify="left", wraplength=420,
                     text="This stays “waiting” until every ticked task is complete "
                          "(or deleted).").pack(anchor="w", padx=14, pady=(12, 4))
        q = tk.StringVar()
        ctk.CTkEntry(win, textvariable=q, placeholder_text="filter…").pack(fill="x", padx=14, pady=4)
        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=14, pady=12)
        lst = ctk.CTkScrollableFrame(win)
        lst.pack(fill="both", expand=True, padx=12, pady=4)

        vars_ = {}
        for _, r in self.df.iterrows():
            i = int(r["ID"])
            if i in exclude or r["Archived"] == "Yes":
                continue
            if r["Status"] == "Complete" and i not in initial:
                continue
            path = self._path_prefix(i)
            label = f"{r['Task']}  (#{i})" + (f"   — {path}" if path else "")
            vars_[i] = (tk.BooleanVar(value=i in initial), label)

        def render(*a):
            for w in lst.winfo_children():
                w.destroy()
            ft = q.get().strip().lower()
            for i, (var, label) in vars_.items():
                if ft and ft not in label.lower():
                    continue
                ctk.CTkCheckBox(lst, text=label, variable=var).pack(anchor="w", pady=2)

        q.trace_add("write", render)
        render()

        def close():
            win.destroy()
            if parent is not self.root:
                try:
                    parent.after(60, parent.grab_set)
                except Exception:  # noqa: BLE001
                    pass

        def done():
            ids = [i for i, (var, _) in vars_.items() if var.get()]
            close()
            on_ok(ids)

        ctk.CTkButton(btns, text="Cancel",
                      command=close).pack(side="right")
        ctk.CTkButton(btns, text="OK", command=done, **ACCENT).pack(side="right", padx=8)
        win.bind("<Escape>", lambda e: close())

    def _wait_for_dialog(self):
        ids = self._selected_ids()
        if not ids:
            return
        exclude = set(self._with_subtree(ids))
        first = self.df[self.df["ID"] == ids[0]].iloc[0]
        initial = set(parse_id_list(first["Blocked By"]))

        def apply(chosen):
            self._snapshot()
            self.df.loc[self.df["ID"].isin(ids), "Blocked By"] = ";".join(str(i) for i in chosen)
            self._mark_dirty()
            self.refresh_all()
        self._pick_tasks_dialog(self.root, initial, exclude, apply)

    def _wait_until_dialog(self):
        ids = self._selected_ids()
        if not ids:
            return
        dlg = ctk.CTkInputDialog(
            text="Don't start before… (YYYY-MM-DD, today, tomorrow, +3d, mon…)\n"
                 "Leave blank to clear.", title="Wait until")
        txt = (dlg.get_input() or "").strip()
        date = parse_due_token(txt) if txt else ""
        if txt and not date:
            messagebox.showwarning("Wait until", "Couldn't read that date.")
            return
        self._snapshot()
        self.df.loc[self.df["ID"].isin(ids), "Start Date"] = date
        self._mark_dirty()
        self.refresh_all()

    def _clear_waiting(self):
        ids = self._selected_ids()
        if not ids:
            return
        self._snapshot()
        mask = self.df["ID"].isin(ids)
        self.df.loc[mask, "Blocked By"] = ""
        self.df.loc[mask, "Start Date"] = ""
        self._mark_dirty()
        self.refresh_all()

    # ---------- refresh ---------- #
    def refresh_all(self):
        self._recompute()
        name = self._current_tab()
        if name == "List":
            self.refresh_list()
        elif name == "Map":
            self.refresh_web()
        elif name == "Board":
            self.refresh_board()
        elif name == "Matrix":
            self.refresh_matrix()
        elif name == "Goals":
            self.refresh_goals()
        elif name == "Analytics":
            self.refresh_analytics()
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

    def _row_tag(self, row, today_d=None):
        if row["Status"] == "Complete":
            return "done"
        if int(row["ID"]) in self._waiting:
            return "blocked"
        d = parse_date(row["Due Date"])
        if d and d < (today_d or today()):
            return "overdue"
        return f"u{coerce_rating(row['Urgency'])}"

    def _cell(self, row, col):
        if col == "Progress":
            d, t = self._progress.get(int(row["ID"]), (0, 0))
            return f"{d}/{t}" if t else ""
        v = row[col]
        if col == "Tags":
            return str(v).replace(";", ", ")
        return v

    @staticmethod
    def _is_open(val):
        return str(val).lower() in ("1", "true", "yes")

    def _walk_items(self, parent=""):
        for iid in self.tree.get_children(parent):
            yield iid
            yield from self._walk_items(iid)

    def refresh_list(self):
        if not hasattr(self, "tree"):
            return
        self._list_job = None
        self._set_appearance_buttons()
        prev_sel = [i for i in self.tree.selection()]
        for iid in self._walk_items():
            self._open_map[iid] = self._is_open(self.tree.item(iid, "open"))
        self.tree.delete(*self.tree.get_children())

        checked = [c for c, v in getattr(self, "cat_filter_vars", {}).items() if v.get()]
        search = self.search_var.get()
        view = filter_view(self.vdf, search, checked, self.smart)
        matched = {int(i) for i in view["ID"]}
        show = set(matched)
        for i in matched:                       # keep the path to every match visible
            p, guard = self._pmap.get(i), 0
            while p is not None and guard < 50:
                show.add(p)
                p = self._pmap.get(p)
                guard += 1
        if str(search).strip():                 # a search hit brings its whole subtree
            arch = set(self.df.loc[self.df["Archived"] == "Yes", "ID"].astype(int))
            for i in matched:
                for d in descendants(self._kids, i):
                    if self.smart == "Archived" or d not in arch:
                        show.add(d)

        sub_df = self.vdf[self.vdf["ID"].isin(show)]
        sub_df = sort_view(sub_df, self._sort_col, self._sort_asc, self._progress)
        by_parent = {}
        for _, row in sub_df.iterrows():
            pid = self._pmap.get(int(row["ID"]))
            by_parent.setdefault(pid if pid in show else None, []).append(row)

        today_d = today()
        placed = set()

        def insert(parent_iid, row):
            rid = int(row["ID"])
            if rid in placed:
                return
            placed.add(rid)
            iid = str(rid)
            box = "☑" if row["Status"] == "Complete" else "☐"
            self.tree.insert(parent_iid, "end", iid=iid, text=f"{box}  {row['Task']}",
                             open=self._open_map.get(iid, self._subtasks_open),
                             values=[self._cell(row, c) for c in TREE_COLUMNS],
                             tags=(self._row_tag(row, today_d),))
            for ch in by_parent.get(rid, []):
                insert(iid, ch)

        for r in by_parent.get(None, []):
            insert("", r)

        keep = [i for i in prev_sel if self.tree.exists(i)]
        if keep:
            self.tree.selection_set(keep)

        task_arrow = ("  ▲" if self._sort_asc else "  ▼") if self._sort_col == "Task" else ""
        self.tree.heading("#0", text="Task" + task_arrow)
        for c in TREE_COLUMNS:
            arrow = ("  ▲" if self._sort_asc else "  ▼") if c == self._sort_col else ""
            self.tree.heading(c, text=c + arrow)

    def _set_all_subtasks_open(self, open_):
        """Collapse / expand every branch (nested ones too). The choice sticks."""
        self._subtasks_open = bool(open_)
        self._open_map.clear()
        if not hasattr(self, "tree"):
            return
        for iid in self._walk_items():
            if self.tree.get_children(iid):
                self.tree.item(iid, open=self._subtasks_open)
        if self._subtasks_open:
            sel = [i for i in self.tree.selection() if str(i).isdigit()]
            if sel:
                self.tree.see(sel[0])

    def _sort_column(self, col):
        if col == self._sort_col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col, self._sort_asc = col, True
        self.refresh_list()

    def refresh_board(self):
        if not hasattr(self, "board_cols"):
            return
        active = self.vdf[self.vdf["Archived"] != "Yes"]
        for st, col in self.board_cols.items():
            for w in col.winfo_children():
                w.destroy()
            sub = active[active["Status"] == st]
            sub = sort_view(sub, "Urgency", True, self._progress)
            for _, row in sub.iterrows():
                self._board_card(col, row, st)

    def _card_meta(self, row, extra=""):
        meta = f"{row['Category']}"
        path = self._path_prefix(int(row["ID"]))
        if path:
            meta = f"↳ {path}  ·  " + meta
        if str(row["Due Date"]).strip():
            meta += f"  ·  due {row['Due Date']}"
        d, t = self._progress.get(int(row["ID"]), (0, 0))
        if t:
            meta += f"  ·  {d}/{t}"
        return meta + extra

    def _board_card(self, parent, row, st):
        card = ctk.CTkFrame(parent)
        card.pack(fill="x", pady=4, padx=2)
        urg_color = URGENCY_COLORS[coerce_rating(row["Urgency"])]
        ctk.CTkLabel(card, text=f"● {row['Task']}", anchor="w", text_color=urg_color,
                     wraplength=220, justify="left").pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(card, text=self._card_meta(row), anchor="w", text_color="#9aa0aa",
                     font=ctk.CTkFont(size=11), wraplength=230,
                     justify="left").pack(fill="x", padx=8)
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
                      command=lambda: self._edit_by_id(_id)).pack(side="right", padx=2)

    def refresh_matrix(self):
        if not hasattr(self, "matrix_cells"):
            return
        for cell in self.matrix_cells:
            for w in cell.winfo_children():
                w.destroy()
        stat = dict(zip(self.df["ID"], self.df["Status"]))
        has_live = {p for p, cs in self._kids.items() if any(stat.get(c) != "Complete" for c in cs)}
        v = self.vdf
        # Actionable items only: unfinished leaves (a parent is represented by its subtasks).
        active = v[(v["Archived"] != "Yes") & (v["Status"] != "Complete") &
                   ~v["ID"].map(lambda i: int(i) in has_live)]
        active = sort_view(active, "Urgency", True)
        for _, row in active.iterrows():
            d = parse_date(row["Due Date"])
            urgent = (coerce_rating(row["Urgency"]) <= 2 or
                      (d is not None and d <= today() + dt.timedelta(days=3)))
            important = coerce_rating(row["Importance"]) <= 2
            q = 0 if (urgent and important) else 1 if important else 2 if urgent else 3
            _id = int(row["ID"])
            path = self._path_prefix(_id)
            label = f"{row['Task']}" + (f"   ↳ {path}" if path else "")
            ctk.CTkButton(self.matrix_cells[q], text=label, anchor="w",
                          fg_color="gray25", hover_color="gray35",
                          text_color=("#7d848f" if _id in self._waiting else "#dce4ee"),
                          command=lambda i=_id: self._edit_by_id(i)).pack(fill="x", pady=2)

    def refresh_goals(self):
        if not hasattr(self, "goal_cols"):
            return
        active = self.vdf[self.vdf["Archived"] != "Yes"]
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
        ctk.CTkLabel(card, text=self._card_meta(row, f"  ·  {row['Status']}"), anchor="w",
                     text_color="#9aa0aa", font=ctk.CTkFont(size=11), wraplength=250,
                     justify="left").pack(fill="x", padx=8)
        _id = int(row["ID"])
        ctk.CTkButton(card, text="Edit", width=50,
                      command=lambda: self._edit_by_id(_id)).pack(anchor="e", padx=6, pady=(2, 6))

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
        ax1.set_xticks(range(4))
        ax1.set_xticklabels(["-3", "-2", "-1", "now"])
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
        waiting = len([i for i in self._waiting
                       if i in set(active["ID"].astype(int)) and
                       self.df.loc[self.df["ID"] == i, "Status"].iloc[0] != "Complete"])
        f = os.path.basename(self.current_file) if self.current_file else "untitled.csv"
        self.status_lbl.configure(
            text=f"{f}   •   {total} tasks   "
                 f"({open_c} open, {inprog} in-progress, {done} done, "
                 f"{overdue} overdue, {waiting} waiting)   •   list: {self.smart}")

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
        path = filedialog.askopenfilename(title="Choose a file to attach",
                                          filetypes=FILE_TYPES)
        if path:
            var.set(path)

    def _link_for_iid(self, iid):
        _id = parse_id(iid)
        if _id is None:
            return ""
        mask = self.df["ID"] == _id
        if not mask.any():
            return ""
        return str(self.df[mask].iloc[0]["Link"]).strip()

    def _on_tree_double(self, event):
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if row and col:
            try:
                idx = int(col.replace("#", "")) - 1
            except ValueError:
                idx = -1
            vis = self._visible_cols()          # "#N" counts displayed columns only
            if 0 <= idx < len(vis) and vis[idx] == "Link":
                link = self._link_for_iid(row)
                if link:
                    self._open_link(link)
                    return
        if row and str(row).isdigit():
            self._edit_by_id(int(row))
            return
        self.edit_selected()

    # ---------- edit dialog ---------- #
    def edit_selected(self):
        ids = self._selected_ids()
        if not ids:
            return
        self._edit_by_id(ids[0])

    def _open_edit_dialog(self, _id, row):
        win = ctk.CTkToplevel(self.root)
        win.title(f"Edit Task #{_id}")
        win.transient(self.root)
        self._fit_dialog(win, 680, 780, min_w=520, min_h=360)
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

        # Effective (derived) ratings shown by the app when subtasks are unfinished.
        eff_u = eff_i = None
        er = self.vdf[self.vdf["ID"] == _id]
        if len(er):
            eff_u, eff_i = coerce_rating(er.iloc[0]["Urgency"]), coerce_rating(er.iloc[0]["Importance"])
        has_live_kids = any(self.df.loc[self.df["ID"] == c, "Status"].iloc[0] != "Complete"
                            for c in self._kids.get(_id, []))
        u_note = (f"   → shown as {eff_u} (from its most urgent subtask)"
                  if has_live_kids else "")
        i_note = (f"   → shown as {eff_i} (from its most important subtask)"
                  if has_live_kids else "")

        field("Task", ctk.CTkEntry(form, textvariable=v["Task"]))

        # --- where it sits in the tree --- #
        desc = set(descendants(self._kids, _id))
        opts = [TOP_LEVEL]
        for _, r in self.df.iterrows():
            i = int(r["ID"])
            if i == _id or i in desc or r["Archived"] == "Yes":
                continue
            path = self._path_prefix(i)
            opts.append(f"{i} · {(path + ' › ') if path else ''}{r['Task']}"[:90])
        cur = parse_id(row["Parent"])
        parent_var = tk.StringVar(value=next(
            (o for o in opts if cur is not None and o.split(" · ")[0] == str(cur)), TOP_LEVEL))
        field("Part of (parent task)", ctk.CTkComboBox(form, values=opts, variable=parent_var))

        field("Category", ctk.CTkComboBox(
            form, values=self._cat_values(), variable=v["Category"],
            command=lambda val: self._on_pick_category(val, v["Category"])))
        field("Subcategory", ctk.CTkComboBox(
            form, values=self._subcat_values(), variable=v["Subcategory"],
            command=lambda val: self._on_pick_subcategory(val, v["Subcategory"])))
        field("Tags (semicolon-separated)", ctk.CTkEntry(form, textvariable=v["Tags"]))
        field("Urgency (1=most)" + u_note,
              ctk.CTkComboBox(form, values=["1", "2", "3", "4", "5"], variable=v["Urgency"]))
        field("Importance (1=most)" + i_note,
              ctk.CTkComboBox(form, values=["1", "2", "3", "4", "5"], variable=v["Importance"]))
        field("Goal horizon (short / medium / long-term)",
              ctk.CTkComboBox(form, values=HORIZONS, variable=v["Horizon"]))
        field("Motivation (Obligation = need-to-do · Joy = fun-to-do)",
              ctk.CTkComboBox(form, values=MOTIVATIONS, variable=v["Motivation"]))
        field("Status", ctk.CTkComboBox(form, values=STATUSES, variable=v["Status"]))
        field("Recurrence", ctk.CTkComboBox(form, values=RECURRENCES, variable=v["Recurrence"]))

        # --- waiting --- #
        field("Don't start before (YYYY-MM-DD) — stays “waiting” until then",
              ctk.CTkEntry(form, textvariable=v["Start Date"]))
        blk_names = tk.StringVar()

        def refresh_blk(*a):
            ids = parse_id_list(v["Blocked By"].get())
            blk_names.set("Waiting for: " + ", ".join(self._names.get(i, f"#{i} (deleted)")
                                                      for i in ids) if ids else "")
        blk_row = ctk.CTkFrame(form, fg_color="transparent")
        ctk.CTkEntry(blk_row, textvariable=v["Blocked By"]).pack(side="left", fill="x", expand=True)

        def pick_blockers():
            self._pick_tasks_dialog(
                win, set(parse_id_list(v["Blocked By"].get())), {_id} | desc,
                lambda ids: v["Blocked By"].set(";".join(str(i) for i in ids)))
        ctk.CTkButton(blk_row, text="Pick…", width=70,
                      command=pick_blockers).pack(side="left", padx=(6, 0))
        field("Wait for these tasks to finish first (IDs, ;-separated)", blk_row)
        ctk.CTkLabel(form, textvariable=blk_names, anchor="w", justify="left",
                     text_color="#9aa0aa", wraplength=560).pack(fill="x")
        v["Blocked By"].trace_add("write", refresh_blk)
        refresh_blk()

        field("Due Date (YYYY-MM-DD)", ctk.CTkEntry(form, textvariable=v["Due Date"]))
        field("Date Created", ctk.CTkEntry(form, textvariable=v["Date Created"]))
        field("Date Completed", ctk.CTkEntry(form, textvariable=v["Date Completed"]))
        field("Estimate (h)", ctk.CTkEntry(form, textvariable=v["Estimate"]))
        field("Actual (h)", ctk.CTkEntry(form, textvariable=v["Actual"]))

        link_row = ctk.CTkFrame(form, fg_color="transparent")
        ctk.CTkEntry(link_row, textvariable=v["Link"]).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(link_row, text="Browse…", width=84,
                      command=lambda: self._browse_file(v["Link"])).pack(side="left", padx=(6, 0))
        field("Link (URL, or a .doc / .docx / .txt / .odt file)", link_row)

        # --- subtasks --- #
        kid_ids = self._kids.get(_id, [])
        if kid_ids:
            lines = []
            for c in kid_ids:
                cr = self.vdf[self.vdf["ID"] == c].iloc[0]
                box = "☑" if cr["Status"] == "Complete" else "☐"
                n_sub = len(self._kids.get(c, []))
                lines.append(f"{box} {cr['Task']}   (U{coerce_rating(cr['Urgency'])}/"
                             f"I{coerce_rating(cr['Importance'])}"
                             + (f", {n_sub} sub" if n_sub else "") + ")")
            kids_txt = "\n".join(lines)
        else:
            kids_txt = "(none yet)"
        ctk.CTkLabel(form, text="Subtasks (edit one by double-clicking it in the List)",
                     anchor="w").pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(form, text=kids_txt, anchor="w", justify="left",
                     text_color="#aab2bd").pack(fill="x")
        ctk.CTkLabel(form, text="Add subtasks — one per line "
                                "(tokens work: !1 *2 ~tomorrow #tag)",
                     anchor="w").pack(fill="x", pady=(8, 2))
        new_subs = ctk.CTkTextbox(form, height=70)
        new_subs.pack(fill="x")

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
                         "Motivation", "Blocked By"):
                    continue
                self.df.loc[mask, c] = v[c].get().strip()
            self.df.loc[mask, "Urgency"] = coerce_rating(v["Urgency"].get())
            self.df.loc[mask, "Importance"] = coerce_rating(v["Importance"].get())
            self.df.loc[mask, "Horizon"] = coerce_horizon(v["Horizon"].get())
            self.df.loc[mask, "Motivation"] = coerce_motivation(v["Motivation"].get())
            self.df.loc[mask, "Category"] = v["Category"].get().strip() or UNCATEGORIZED
            self.df.loc[mask, "Subcategory"] = v["Subcategory"].get().strip() or UNCATEGORIZED
            self.df.loc[mask, "Date Completed"] = completed
            self.df.loc[mask, "Blocked By"] = ";".join(
                str(i) for i in parse_id_list(v["Blocked By"].get()) if i != _id)
            pv = parent_var.get()
            self.df.loc[mask, "Parent"] = ("" if pv == TOP_LEVEL
                                           else str(parse_id(pv.split(" · ")[0]) or ""))
            self.df.loc[mask, "Notes"] = notes.get("1.0", "end").strip()
            # new subtasks typed into the box
            for ln in [l.strip() for l in new_subs.get("1.0", "end").splitlines() if l.strip()]:
                p = parse_quick_add(ln, self.categories)
                self._append(self._new_task(
                    Task=p["Task"] or ln, Parent=str(_id),
                    Category=p["Category"] or v["Category"].get().strip() or UNCATEGORIZED,
                    Subcategory=v["Subcategory"].get().strip() or UNCATEGORIZED,
                    Horizon=v["Horizon"].get(), Motivation=v["Motivation"].get(),
                    Tags=p["Tags"], Urgency=p["Urgency"] or 3,
                    Importance=p["Importance"] or 3, **{"Due Date": p["Due Date"]}))
                self._open_map[str(_id)] = True
            if status == "Complete" and str(row["Status"]) != "Complete" \
                    and str(v["Recurrence"].get()).strip():
                task = self.df[mask].iloc[0].to_dict()
                nxt = next_occurrence(task)
                nxt["ID"] = self._next_id()
                self._append(nxt)
            self._mark_dirty()
            self._collect_categories()
            self.refresh_all()
            win.destroy()

        ctk.CTkButton(btns, text="Open link", width=90, command=open_link).pack(side="left")
        ctk.CTkButton(btns, text="Cancel", width=80, command=win.destroy).pack(side="right")
        ctk.CTkButton(btns, text="Save Changes", command=save_changes, **ACCENT).pack(side="right", padx=8)
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<Control-s>", lambda e: save_changes())
        win.bind("<Control-Return>", lambda e: save_changes())


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