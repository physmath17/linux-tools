#!/usr/bin/env python3
"""Card Tracker - a tiny Linux desktop app (Python + Tkinter, standard library only).

Columns: Credit Card | Due Date | Last Month | Current Month | Next Month (rolls automatically).
Cards with an unpaid amount come first: the soonest due date (or the most overdue) is at the top.

  * Click an empty month cell      -> enter the amount due
  * Click a month cell with amount -> toggle paid (turns green)
  * Right-click a month cell       -> edit amount / mark paid / clear
  * Click Due Date                 -> set the day of month
  * Click a card name              -> rename; right-click for delete
  * ctrl+z, ctrl-Z                 -> undo the last change
  * ctrl+n, ctrl-N                 -> add new card 

Command line:
  card_tracker.py                     open the app
  card_tracker.py --remind            show a desktop pop-up for payments due soon, then exit (cron uses this)
  card_tracker.py --remind --dry-run  print the reminder instead of showing a pop-up
  card_tracker.py --test-popup        show a test pop-up, to check notifications work

Data is stored locally in ~/.local/share/card-tracker/data.json
"""

import argparse
import calendar
import html
import json
import os
import shutil
import subprocess
import sys
import copy
import tkinter as tk
from datetime import date
from tkinter import messagebox, simpledialog

APP_NAME = "card-tracker"
DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), APP_NAME
)
DATA_FILE = os.path.join(DATA_DIR, "data.json")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PNG = os.path.join(SCRIPT_DIR, "card-tracker.png")

SOON_DAYS = 5  # "approaching": due within this many days (overdue counts too)
CURRENCY = "₹"  # change to "$", "€", etc.

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Colours
BG = "#f5f6fa"
SURFACE = "#ffffff"
TEXT = "#1a1a2e"
MUTED = "#6b7280"
HEADER_BG = "#e8eaf6"
EMPTY_BG, EMPTY_FG = "#eef0f4", "#9aa0ad"
PENDING_BG, PENDING_FG = "#dc2626", "#ffffff"
PAID_BG, PAID_FG = "#22c55e", "#ffffff"
OVERDUE_FG = "#b42318"
SOON_FG = "#92400e"


# ---------- storage ----------

def load_cards():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_cards(cards):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cards, f, indent=2)
        os.replace(tmp, DATA_FILE)  # atomic: never leaves a half-written file
    except OSError as e:
        messagebox.showerror("Could not save", str(e))


# ---------- helpers ----------

def visible_months(today=None):
    """Last month, current month and next month, computed from today's date."""
    today = today or date.today()
    base = today.year * 12 + (today.month - 1)
    out = []
    for offset in (-1, 0, 1):
        y, m0 = divmod(base + offset, 12)
        out.append((y, m0 + 1))
    return out


def month_key(y, m):
    return f"{y}-{m}"


def fmt_amount(a):
    a = float(a)
    return f"{a:,.0f}" if a.is_integer() else f"{a:,.2f}"


def due_date_for(y, m, day):
    """The due date in month m of year y; a due day of 31 becomes the 30th, 28th... as needed."""
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def pending_items(card, today=None):
    """Unpaid amounts in the three visible months, as (days_until_due, key, amount, due_date).

    Negative days mean overdue. Needs a due day on the card. Months that have scrolled out of
    view are ignored, so an old forgotten entry can't pin a card to the top where you can't fix it.
    """
    today = today or date.today()
    day = card.get("dueDay")
    if not day:
        return []
    out = []
    for y, m in visible_months(today):
        key = month_key(y, m)
        entry = card.get("months", {}).get(key)
        if entry and not entry.get("paid"):
            due = due_date_for(y, m, day)
            out.append(((due - today).days, key, entry["amount"], due))
    return out


def next_due_in(card, today=None):
    """Days until the next occurrence of the card's due day (today counts), or None."""
    today = today or date.today()
    day = card.get("dueDay")
    if not day:
        return None
    base = today.year * 12 + (today.month - 1)
    for offset in (0, 1):
        y, m0 = divmod(base + offset, 12)
        due = due_date_for(y, m0 + 1, day)
        if due >= today:
            return (due - today).days
    return None


def sort_key(index, card, today=None):
    """Order cards by urgency.

    1. Cards with an unpaid amount, soonest due date first (overdue ones at the very top).
    2. Cards with nothing unpaid, by how soon their due day comes round next.
    3. Cards with no due day set.
    Ties keep the order the cards were added in.
    """
    today = today or date.today()
    pending = pending_items(card, today)
    if pending:
        return (0, min(p[0] for p in pending), index)
    nxt = next_due_in(card, today)
    if nxt is not None:
        return (1, nxt, index)
    return (2, 0, index)


def due_color(card, today=None):
    pending = pending_items(card, today)
    if not pending:
        return MUTED
    soonest = min(p[0] for p in pending)
    if soonest < 0:
        return OVERDUE_FG
    if soonest <= SOON_DAYS:
        return SOON_FG
    return MUTED


# ---------- reminders (used by cron) ----------

def describe(days, due):
    if days < 0:
        return f"overdue by {-days} day{'s' if days != -1 else ''}"
    if days == 0:
        return "due today"
    if days == 1:
        return "due tomorrow"
    return f"due in {days} days ({due.strftime('%d %b')})"


def reminder_items(cards, today=None, within=SOON_DAYS):
    """Unpaid payments that are overdue or due within `within` days, most urgent first."""
    today = today or date.today()
    items = []
    for card in cards:
        for days, _key, amount, due in pending_items(card, today):
            if days <= within:
                items.append((days, card.get("name", "Card"), amount, due))
    items.sort(key=lambda it: (it[0], it[1]))
    return items


def desktop_env():
    """Cron starts jobs without a desktop session; point notify-send at the user's session."""
    env = dict(os.environ)
    runtime = env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
    env.setdefault("DISPLAY", ":0")
    return env


def notify(title, body, urgent=False, dry_run=False):
    if dry_run:
        print(title)
        print(body)
        return 0
    exe = shutil.which("notify-send")
    if not exe:
        print("notify-send not found. On Arch: sudo pacman -S libnotify", file=sys.stderr)
        return 1
    cmd = [exe, "-a", "Card Tracker", "-u", "critical" if urgent else "normal"]
    if os.path.exists(ICON_PNG):
        cmd += ["-i", ICON_PNG]
    cmd += [title, html.escape(body, quote=False)]
    try:
        subprocess.run(cmd, env=desktop_env(), check=True, timeout=15)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"Could not show the notification: {e}", file=sys.stderr)
        return 1
    return 0


def run_reminder(dry_run=False):
    today = date.today()
    items = reminder_items(load_cards(), today)
    if not items:
        return 0  # nothing due soon: stay silent
    lines = [f"• {name}: {CURRENCY}{fmt_amount(amount)} - {describe(days, due)}"
             for days, name, amount, due in items[:8]]
    if len(items) > 8:
        lines.append(f"...and {len(items) - 8} more")
    n = len(items)
    title = f"{n} credit card payment{'s' if n != 1 else ''} due soon"
    return notify(title, "\n".join(lines), urgent=items[0][0] < 0, dry_run=dry_run)


# ---------- app ----------

class App(tk.Tk):
    def __init__(self):
        super().__init__(className="CardTracker")
        self.title("Card Tracker")
        self.configure(bg=BG)
        self.minsize(780, 260)
        try:
            self._icon = tk.PhotoImage(file=ICON_PNG)  # keep a reference so it isn't freed
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass  # icon file missing: the window just gets the default icon
        self.cards = load_cards()
        self.history = []                          # earlier states, for undo
        self._snapshot = copy.deepcopy(self.cards)  # the state as it is now

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(top, text="Card Tracker", bg=BG, fg=TEXT,
                 font=("TkDefaultFont", 14, "bold")).pack(side="left")
        tk.Button(top, text="+ Add card  (Ctrl+N)", command=self.add_card,
                  relief="flat", bg="#4f46e5", fg="white",
                  activebackground="#4338ca", activeforeground="white",
                  padx=10, pady=4).pack(side="right")
        tk.Label(top, text="click = enter / mark paid  ·  right-click = more",
                 bg=BG, fg=MUTED).pack(side="right", padx=14)

        self.grid_frame = tk.Frame(self, bg=BG)
        self.grid_frame.pack(fill="both", expand=True, padx=14, pady=(6, 14))

        self.bind("<Control-n>", lambda e: self.add_card())
        self.bind("<Control-N>", lambda e: self.add_card())
        self.bind("<Control-z>", self.undo)
        self.bind("<Control-Z>", self.undo)
        self.render()
        self.after(60 * 60 * 1000, self.tick)  # re-check the date every hour

    def tick(self):
        self.render()  # picks up a new month or day if the app was left open
        self.after(60 * 60 * 1000, self.tick)

    def commit(self):
        self.history.append(self._snapshot)          # remember the state before this change
        self.history = self.history[-50:]            # keep the last 50 changes
        self._snapshot = copy.deepcopy(self.cards)
        save_cards(self.cards)
        self.render()

    def undo(self, event=None):
        if not self.history:
            return
        self.cards = self.history.pop()
        self._snapshot = copy.deepcopy(self.cards)
        save_cards(self.cards)
        self.render()

    # ----- rendering -----

    def make_cell(self, row, col, text, bg, fg, on_click=None, on_right=None,
                  bold=False, anchor="center", cursor="hand2"):
        lbl = tk.Label(
            self.grid_frame, text=text, bg=bg, fg=fg, anchor=anchor,
            font=("TkDefaultFont", 10, "bold" if bold else "normal"),
            padx=10, pady=8, cursor=cursor if on_click else "",
        )
        lbl.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
        if on_click:
            lbl.bind("<Button-1>", lambda e: on_click())
        if on_right:
            lbl.bind("<Button-3>", lambda e: on_right(e))
        return lbl

    def render(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()

        today = date.today()
        months = visible_months(today)
        headers = ["Credit Card", "Due Date"] + [MONTHS[m - 1] for _, m in months]
        for c, h in enumerate(headers):
            self.make_cell(0, c, h, HEADER_BG, MUTED, bold=True,
                           anchor="w" if c == 0 else "center")
        self.grid_frame.columnconfigure(0, weight=1, minsize=180)
        for c in range(1, len(headers)):
            self.grid_frame.columnconfigure(c, weight=0, minsize=84)

        if not self.cards:
            tk.Label(self.grid_frame, text="No cards yet - click \"+ Add card\".",
                     bg=BG, fg=MUTED, pady=40).grid(
                row=1, column=0, columnspan=len(headers))
            return

        # Display order only: the saved file keeps the order the cards were added in.
        ordered = [c for _, c in sorted(enumerate(self.cards),
                                        key=lambda ic: sort_key(ic[0], ic[1], today))]
        for r, card in enumerate(ordered, start=1):
            self.make_cell(
                r, 0, card["name"], SURFACE, TEXT, anchor="w", bold=True,
                on_click=lambda c=card: self.rename_card(c),
                on_right=lambda e, c=card: self.card_menu(e, c),
            )
            dcolor = due_color(card, today)
            self.make_cell(
                r, 1, card.get("dueDay") or "-", SURFACE, dcolor, bold=dcolor != MUTED,
                on_click=lambda c=card: self.edit_day(c, "dueDay", "Due date"),
            )
            for i, (y, m) in enumerate(months):
                key = month_key(y, m)
                entry = card["months"].get(key)
                if entry is None:
                    text, bg, fg = "+", EMPTY_BG, EMPTY_FG
                elif entry["paid"]:
                    text, bg, fg = fmt_amount(entry["amount"]) + "  ✓", PAID_BG, PAID_FG
                else:
                    text, bg, fg = fmt_amount(entry["amount"]), PENDING_BG, PENDING_FG
                self.make_cell(
                    r, 2 + i, text, bg, fg, bold=True,
                    on_click=lambda c=card, k=key: self.month_click(c, k),
                    on_right=lambda e, c=card, k=key: self.month_menu(e, c, k),
                )

    # ----- actions -----

    def add_card(self):
        name = simpledialog.askstring("New card", "Card name (e.g. Visa 1234):",
                                      parent=self)
        if not name or not name.strip():
            return
        self.cards.append({"name": name.strip(), "dueDay": 0, "months": {}})
        self.commit()

    def rename_card(self, card):
        name = simpledialog.askstring("Rename card", "Card name:",
                                      initialvalue=card["name"], parent=self)
        if name and name.strip():
            card["name"] = name.strip()
            self.commit()

    def delete_card(self, card):
        if messagebox.askyesno("Delete card",
                               f"Delete \"{card['name']}\" and all its data?",
                               parent=self):
            self.cards.remove(card)
            self.commit()

    def card_menu(self, event, card):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Rename", command=lambda: self.rename_card(card))
        menu.add_command(label="Delete", command=lambda: self.delete_card(card))
        menu.tk_popup(event.x_root, event.y_root)

    def edit_day(self, card, field, title):
        current = card.get(field) or None
        day = simpledialog.askinteger(title, "Day of month (1-31):", parent=self,
                                      minvalue=1, maxvalue=31, initialvalue=current)
        if day is not None:
            card[field] = day
            self.commit()

    def ask_amount(self, initial=None):
        return simpledialog.askfloat("Amount due", "Amount:", parent=self,
                                     minvalue=0, initialvalue=initial)

    def month_click(self, card, key):
        entry = card["months"].get(key)
        if entry is None:
            amt = self.ask_amount()
            if amt is None:
                return
            card["months"][key] = {"amount": amt, "paid": False}
        else:
            entry["paid"] = not entry["paid"]
        self.commit()

    def edit_amount(self, card, key):
        entry = card["months"].get(key)
        amt = self.ask_amount(entry["amount"] if entry else None)
        if amt is None:
            return
        card["months"][key] = {"amount": amt, "paid": entry["paid"] if entry else False}
        self.commit()

    def toggle_paid(self, card, key):
        entry = card["months"].get(key)
        if entry:
            entry["paid"] = not entry["paid"]
            self.commit()

    def clear_month(self, card, key):
        card["months"].pop(key, None)
        self.commit()

    def month_menu(self, event, card, key):
        entry = card["months"].get(key)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Edit amount", command=lambda: self.edit_amount(card, key))
        if entry:
            menu.add_command(
                label="Mark unpaid" if entry["paid"] else "Mark paid",
                command=lambda: self.toggle_paid(card, key))
            menu.add_separator()
            menu.add_command(label="Clear", command=lambda: self.clear_month(card, key))
        menu.tk_popup(event.x_root, event.y_root)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="card-tracker", description="Credit card due-date tracker.")
    parser.add_argument("--remind", action="store_true",
                        help="show a desktop pop-up for payments due soon, then exit (used by cron)")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --remind: print the reminder instead of showing a pop-up")
    parser.add_argument("--test-popup", action="store_true",
                        help="show a test pop-up to check that notifications work, then exit")
    args = parser.parse_args(argv)

    if args.test_popup:
        return notify("Card Tracker", "Pop-ups are working. Reminders will look like this.")
    if args.remind:
        return run_reminder(dry_run=args.dry_run)
    App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
