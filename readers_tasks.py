#!/usr/bin/env python3
"""Reader's Tasks — a black-and-white, text-only desktop client for CalDAV task lists
(Tasks.org Cloud, Nextcloud, Radicale…). One file, PyQt5 + requests, nothing else.
MIT licence."""

import json
import os
import re
import sys
import uuid
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, date
from urllib.parse import urljoin, urlparse

import requests
from PyQt5 import QtCore, QtGui, QtWidgets

APP = "readers-tasks"
VERSION = "1.1.0"
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), APP)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
SYNC_MINUTES = 5

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}


# ------------------------------------------------------------------------------------------
# iCalendar (VTODO only, the little we need)
# ------------------------------------------------------------------------------------------

def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n")).split("\n")


def _prop(lines, name):
    for line in lines:
        key = line.split(":", 1)[0].split(";", 1)[0].upper()
        if key == name:
            return line.split(":", 1)[1] if ":" in line else ""
    return None


def _unescape(v):
    return (v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def _escape(v):
    return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line):
    out, chunk = [], line.encode("utf-8")
    while len(chunk) > 72:
        cut = 72
        while cut > 0 and (chunk[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(chunk[:cut].decode("utf-8")); chunk = b" " + chunk[cut:]
    out.append(chunk.decode("utf-8"))
    return "\r\n".join(out)


def _utcnow():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class Task:
    def __init__(self, href, etag, ics):
        self.href, self.etag, self.ics = href, etag, ics
        lines = _unfold(ics)
        start = next((i for i, l in enumerate(lines) if l.upper().startswith("BEGIN:VTODO")), None)
        end = next((i for i, l in enumerate(lines) if l.upper().startswith("END:VTODO")), None)
        self.todo_lines = lines[start:end + 1] if start is not None and end is not None else lines
        self.uid = _prop(self.todo_lines, "UID") or ""
        self.summary = _unescape(_prop(self.todo_lines, "SUMMARY") or "")
        status = (_prop(self.todo_lines, "STATUS") or "").upper()
        self.completed = status == "COMPLETED" or _prop(self.todo_lines, "COMPLETED") is not None
        self.cancelled = status == "CANCELLED"
        self.due = _parse_date(_prop(self.todo_lines, "DUE"))
        self.created = _prop(self.todo_lines, "CREATED") or _prop(self.todo_lines, "DTSTAMP") or ""
        self.parent = None
        for line in self.todo_lines:
            if line.upper().startswith("RELATED-TO") and ("RELTYPE=CHILD" not in line.upper()):
                self.parent = line.split(":", 1)[1] if ":" in line else None

    def due_label(self):
        if not self.due:
            return ""
        today = date.today()
        delta = (self.due - today).days
        if delta == 0:
            return "today"
        if delta == 1:
            return "tomorrow"
        if delta < 0:
            return f"{-delta} d late"
        if delta < 7:
            return self.due.strftime("%A").lower()
        return self.due.strftime("%-d %b").lower()

    def completed_ics(self):
        """The same VTODO with the completion properties set."""
        lines = _unfold(self.ics)
        out, in_todo = [], False
        for l in lines:
            u = l.upper()
            if u.startswith("BEGIN:VTODO"):
                in_todo = True
            if in_todo and u.split(":", 1)[0].split(";", 1)[0] in ("STATUS", "COMPLETED", "PERCENT-COMPLETE", "LAST-MODIFIED", "DTSTAMP"):
                continue
            if u.startswith("END:VTODO"):
                now = _utcnow()
                out += [f"DTSTAMP:{now}", f"LAST-MODIFIED:{now}", "STATUS:COMPLETED", f"COMPLETED:{now}", "PERCENT-COMPLETE:100"]
                in_todo = False
            out.append(l)
        return "\r\n".join(_fold(l) for l in out) + "\r\n"


def _reopened_ics(task):
    """The same VTODO with the completion properties removed."""
    lines = _unfold(task.ics)
    out, in_todo = [], False
    for l in lines:
        u = l.upper()
        if u.startswith("BEGIN:VTODO"):
            in_todo = True
        if in_todo and u.split(":", 1)[0].split(";", 1)[0] in ("STATUS", "COMPLETED", "PERCENT-COMPLETE", "LAST-MODIFIED", "DTSTAMP"):
            continue
        if u.startswith("END:VTODO"):
            now = _utcnow()
            out += [f"DTSTAMP:{now}", f"LAST-MODIFIED:{now}", "STATUS:NEEDS-ACTION"]
            in_todo = False
        out.append(l)
    return "\r\n".join(_fold(l) for l in out) + "\r\n"


def _parse_date(v):
    if not v:
        return None
    v = v.strip()
    m = re.match(r"(\d{4})(\d{2})(\d{2})", v)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def new_task_ics(summary):
    now = _utcnow()
    uid = str(uuid.uuid4())
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//readers-tasks//EN", "BEGIN:VTODO",
             f"UID:{uid}", f"DTSTAMP:{now}", f"CREATED:{now}", f"LAST-MODIFIED:{now}",
             f"SUMMARY:{_escape(summary)}", "STATUS:NEEDS-ACTION", "END:VTODO", "END:VCALENDAR"]
    return uid, "\r\n".join(_fold(l) for l in lines) + "\r\n"


# ------------------------------------------------------------------------------------------
# CalDAV client: discovery, list, add, complete, delete
# ------------------------------------------------------------------------------------------

class CalDAVError(Exception):
    pass


class CalDAV:
    def __init__(self, url, username, password):
        self.base = url.strip()
        self.s = requests.Session()
        self.s.auth = (username, password)
        self.s.headers["User-Agent"] = f"readers-tasks/{VERSION}"

    def _req(self, method, url, body=None, depth=None, headers=None):
        h = {"Content-Type": "application/xml; charset=utf-8"}
        if depth is not None:
            h["Depth"] = str(depth)
        if headers:
            h.update(headers)
        r = self.s.request(method, url, data=body.encode("utf-8") if isinstance(body, str) else body, headers=h, timeout=30)
        if r.status_code == 401:
            raise CalDAVError("wrong username or app password")
        if r.status_code >= 400:
            raise CalDAVError(f"{method} {url}: HTTP {r.status_code}")
        return r

    def _propfind(self, url, props, depth):
        body = ('<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
                + "".join(f"<{p}/>" for p in props) + "</d:prop></d:propfind>")
        r = self._req("PROPFIND", url, body, depth)
        return ET.fromstring(r.content)

    def _href_of(self, root, path):
        el = root.find(path, NS)
        if el is None:
            return None
        href = el.find("d:href", NS)
        return urljoin(self.base, href.text.strip()) if href is not None and href.text else None

    def task_lists(self):
        """Discover the task collections: [(name, url)]."""
        candidates = [self.base]
        try:
            root = self._propfind(self.base, ["d:current-user-principal", "d:resourcetype", "c:calendar-home-set"], 0)
            principal = self._href_of(root, ".//d:current-user-principal")
            home = self._href_of(root, ".//c:calendar-home-set")
            if not home and principal:
                root2 = self._propfind(principal, ["c:calendar-home-set"], 0)
                home = self._href_of(root2, ".//c:calendar-home-set")
            if home:
                candidates.insert(0, home)
        except CalDAVError:
            pass
        for home in candidates:
            root = self._propfind(home, ["d:displayname", "d:resourcetype", "c:supported-calendar-component-set"], 1)
            lists = []
            for resp in root.findall("d:response", NS):
                href = resp.find("d:href", NS)
                rtype = resp.find(".//d:resourcetype", NS)
                if href is None or rtype is None or rtype.find("c:calendar", NS) is None:
                    continue
                comps = [c.get("name", "").upper() for c in resp.findall(".//c:supported-calendar-component-set/c:comp", NS)]
                if comps and "VTODO" not in comps:
                    continue
                name_el = resp.find(".//d:displayname", NS)
                name = (name_el.text or "").strip() if name_el is not None else ""
                url = urljoin(self.base, href.text.strip())
                lists.append((name or urlparse(url).path.rstrip("/").split("/")[-1], url))
            if lists:
                return lists
        raise CalDAVError("no task list found at this address")

    def tasks(self, list_url):
        body = ('<?xml version="1.0" encoding="utf-8"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                '<d:prop><d:getetag/><c:calendar-data/></d:prop>'
                '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VTODO"/></c:comp-filter></c:filter></c:calendar-query>')
        r = self._req("REPORT", list_url, body, 1)
        root = ET.fromstring(r.content)
        out = []
        for resp in root.findall("d:response", NS):
            href = resp.find("d:href", NS)
            etag = resp.find(".//d:getetag", NS)
            data = resp.find(".//c:calendar-data", NS)
            if href is None or data is None or not data.text:
                continue
            out.append(Task(urljoin(list_url, href.text.strip()), etag.text if etag is not None else None, data.text))
        return out

    def add(self, list_url, summary):
        uid, ics = new_task_ics(summary)
        url = urljoin(list_url.rstrip("/") + "/", f"{uid}.ics")
        self._req("PUT", url, ics, headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})

    def complete(self, task):
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        if task.etag:
            headers["If-Match"] = task.etag
        self._req("PUT", task.href, task.completed_ics(), headers=headers)

    def reopen(self, task):
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        if task.etag:
            headers["If-Match"] = task.etag
        self._req("PUT", task.href, _reopened_ics(task), headers=headers)

    def delete(self, task):
        self._req("DELETE", task.href)


# ------------------------------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------------------------------

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG_FILE)


# ------------------------------------------------------------------------------------------
# UI
# ------------------------------------------------------------------------------------------

class Worker(QtCore.QObject):
    """Runs one CalDAV job off the UI thread."""
    done = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as e:  # network, auth, parse — all end up as one line of text
            self.failed.emit(str(e))


class TaskRow(QtWidgets.QWidget):
    completed = QtCore.pyqtSignal(object)
    reopened = QtCore.pyqtSignal(object)
    deleted = QtCore.pyqtSignal(object)

    def __init__(self, task, big, small, done=False, parent=None):
        super().__init__(parent)
        self.task = task
        self.done = done
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(18)
        self.box = QtWidgets.QLabel("☑" if done else "☐")
        self.box.setFont(big)
        self.box.setCursor(QtCore.Qt.PointingHandCursor)
        self.box.setToolTip("reopen" if done else "complete")
        if done:
            self.box.setObjectName("dim")
        self.box.mousePressEvent = lambda e: (self.reopened if self.done else self.completed).emit(self.task)
        lay.addWidget(self.box, 0)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(0)
        title = QtWidgets.QLabel(task.summary or "…")
        title.setFont(big)
        title.setWordWrap(True)
        if done:
            title.setObjectName("dim")
        col.addWidget(title)
        due = task.due_label()
        if due:
            sub = QtWidgets.QLabel(due)
            sub.setFont(small)
            sub.setObjectName("dim")
            col.addWidget(sub)
        lay.addLayout(col, 1)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _menu(self, pos):
        m = QtWidgets.QMenu(self)
        if self.done:
            m.addAction("reopen", lambda: self.reopened.emit(self.task))
        else:
            m.addAction("complete", lambda: self.completed.emit(self.task))
        m.addAction("delete", lambda: self.deleted.emit(self.task))
        m.exec_(self.mapToGlobal(pos))


class SetupDialog(QtWidgets.QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("reader's tasks")
        form = QtWidgets.QFormLayout(self)
        form.setSpacing(12)
        intro = QtWidgets.QLabel("CalDAV task lists. For Tasks.org Cloud: in the Android app,\n"
                                 "⚙ › App settings › Tasks.org › Generate new password, and copy\n"
                                 "the URL, username and app password shown there.")
        intro.setObjectName("dim")
        form.addRow(intro)
        self.url = QtWidgets.QLineEdit(cfg.get("url", ""))
        self.url.setPlaceholderText("https://caldav.tasks.org/…")
        self.user = QtWidgets.QLineEdit(cfg.get("username", ""))
        self.password = QtWidgets.QLineEdit(cfg.get("password", ""))
        self.password.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("server", self.url)
        form.addRow("username", self.user)
        form.addRow("app password", self.password)
        self.error = QtWidgets.QLabel("")
        self.error.setObjectName("dim")
        self.error.setWordWrap(True)
        form.addRow(self.error)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        cancel = QtWidgets.QPushButton("cancel")
        cancel.clicked.connect(self.reject)
        ok = QtWidgets.QPushButton("connect")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        form.addRow(row)
        self.resize(560, 320)

    def values(self):
        return {"url": self.url.text().strip(), "username": self.user.text().strip(), "password": self.password.text()}


class Main(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.client = None
        self.lists = []          # every list the server has: [(name, url)]
        self.tasks = []          # open tasks of the current list
        self.done_tasks = []     # completed tasks of the current list
        self.show_done = False
        self.threads = []
        self.setWindowTitle("reader's tasks")
        self.resize(760, 900)

        self.font_size = int(self.cfg.get("font_size", 15))
        self.dark = bool(self.cfg.get("dark", False))

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Lists column
        self.lists_widget = QtWidgets.QListWidget()
        self.lists_widget.setObjectName("lists")
        self.lists_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.lists_widget.setFixedWidth(220)
        self.lists_widget.currentRowChanged.connect(self.select_list)
        self.lists_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.lists_widget.customContextMenuRequested.connect(self.lists_menu)
        outer.addWidget(self.lists_widget)

        # Tasks column
        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(32, 24, 32, 16)
        right.setSpacing(0)
        outer.addLayout(right, 1)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.rows_host = QtWidgets.QWidget()
        self.rows = QtWidgets.QVBoxLayout(self.rows_host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.rows.addStretch(1)
        self.scroll.setWidget(self.rows_host)
        right.addWidget(self.scroll, 1)
        # "n done" line: shows / hides the completed tasks (reopen a task ticked by mistake).
        self.done_toggle = QtWidgets.QLabel("")
        self.done_toggle.setObjectName("dim")
        self.done_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self.done_toggle.mousePressEvent = lambda e: self.toggle_done()
        right.addWidget(self.done_toggle)

        self.entry = QtWidgets.QLineEdit()
        self.entry.setPlaceholderText("+ new task")
        self.entry.setFrame(False)
        self.entry.returnPressed.connect(self.add_task)
        right.addWidget(self.entry)
        bottom = QtWidgets.QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("dim")
        bottom.addWidget(self.status, 1)
        self.gear = QtWidgets.QLabel("⚙")
        self.gear.setObjectName("dim")
        self.gear.setToolTip("server settings (Ctrl+,)")
        self.gear.setCursor(QtCore.Qt.PointingHandCursor)
        self.gear.mousePressEvent = lambda e: self.setup()
        bottom.addWidget(self.gear, 0)
        right.addLayout(bottom)

        # Shortcuts
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self, self.toggle_theme)
        QtWidgets.QShortcut(QtGui.QKeySequence("F5"), self, self.sync)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+R"), self, self.sync)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+N"), self, self.entry.setFocus)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+="), self, lambda: self.zoom(1))
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl++"), self, lambda: self.zoom(1))
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+-"), self, lambda: self.zoom(-1))
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+,"), self, self.setup)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+D"), self, self.toggle_done)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, self.close)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.sync)
        self.timer.start(SYNC_MINUTES * 60 * 1000)

        self.apply_style()
        if self.cfg.get("url"):
            self.connect_client()
        else:
            QtCore.QTimer.singleShot(0, self.setup)

    # ---- look ------------------------------------------------------------------------

    def apply_style(self):
        bg, fg = ("#000000", "#ffffff") if self.dark else ("#ffffff", "#000000")
        dim = "rgba(255,255,255,0.55)" if self.dark else "rgba(0,0,0,0.55)"
        rule = "rgba(255,255,255,0.25)" if self.dark else "rgba(0,0,0,0.25)"
        s = self.font_size
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {bg}; color: {fg}; }}
            QLabel#dim {{ color: {dim}; }}
            QListWidget#lists {{ background: {bg}; color: {fg}; border: none; border-right: 1px solid {rule};
                                 font-size: {s}pt; font-weight: 300; padding: 16px 0; outline: none; }}
            QListWidget#lists::item {{ padding: 10px 20px; border: none; }}
            QListWidget#lists::item:selected {{ background: {fg}; color: {bg}; }}
            QLineEdit {{ background: {bg}; color: {fg}; border: none; border-top: 1px solid {rule};
                         padding: 12px 0; font-size: {s + 2}pt; font-weight: 300; }}
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: {bg}; }}
            QScrollBar:vertical {{ background: {bg}; width: 6px; }}
            QScrollBar::handle:vertical {{ background: {rule}; min-height: 24px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QMenu {{ background: {bg}; color: {fg}; border: 1px solid {rule}; font-size: {s}pt; }}
            QMenu::item:selected {{ background: {fg}; color: {bg}; }}
            QDialog QLineEdit {{ border: 1px solid {rule}; padding: 6px; font-size: {s}pt; }}
            QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {fg}; padding: 6px 18px; font-size: {s}pt; }}
            QPushButton:default {{ background: {fg}; color: {bg}; }}
            QToolTip {{ background: {bg}; color: {fg}; border: 1px solid {rule}; }}
        """)
        self.big = QtGui.QFont()
        self.big.setPointSize(self.font_size + 3)
        self.big.setWeight(QtGui.QFont.Light)
        self.small = QtGui.QFont()
        self.small.setPointSize(max(8, self.font_size - 3))
        self.render_tasks()

    def toggle_theme(self):
        self.dark = not self.dark
        self.cfg["dark"] = self.dark
        save_config(self.cfg)
        self.apply_style()

    def zoom(self, delta):
        self.font_size = max(9, min(30, self.font_size + delta))
        self.cfg["font_size"] = self.font_size
        save_config(self.cfg)
        self.apply_style()

    # ---- network -----------------------------------------------------------------------

    def run(self, fn, on_done):
        thread = QtCore.QThread(self)
        worker = Worker(fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(on_done)
        worker.failed.connect(self.show_error)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        # Keep both alive until the thread ends: a collected worker never runs its slot.
        pair = (thread, worker)
        thread.finished.connect(lambda: self.threads.remove(pair) if pair in self.threads else None)
        self.threads.append(pair)
        thread.start()

    def show_error(self, text):
        self.status.setText(text)

    def setup(self):
        dlg = SetupDialog(self.cfg, self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            if not self.cfg.get("url"):
                self.status.setText("not connected — Ctrl+, to set up")
            return
        self.cfg.update(dlg.values())
        save_config(self.cfg)
        self.connect_client()

    def connect_client(self):
        self.client = CalDAV(self.cfg["url"], self.cfg.get("username", ""), self.cfg.get("password", ""))
        self.status.setText("connecting…")
        self.run(self.client.task_lists, self.got_lists)

    def got_lists(self, lists):
        self.lists = lists
        self.refresh_lists(keep=self.cfg.get("list_url"))

    def visible_lists(self):
        hidden = set(self.cfg.get("hidden_lists", []))
        order = self.cfg.get("list_order", [])
        shown = [(n, u) for n, u in self.lists if u not in hidden]
        return sorted(shown, key=lambda x: (order.index(x[1]) if x[1] in order else len(order), x[0].lower()))

    def refresh_lists(self, keep=None):
        shown = self.visible_lists()
        self.lists_widget.blockSignals(True)
        self.lists_widget.clear()
        for name, _ in shown:
            self.lists_widget.addItem(name)
        row = next((i for i, (_, u) in enumerate(shown) if u == keep), 0)
        self.lists_widget.setCurrentRow(row)
        self.lists_widget.blockSignals(False)
        self.select_list(row)

    def current_list(self):
        row = self.lists_widget.currentRow()
        shown = self.visible_lists()
        return shown[row][1] if 0 <= row < len(shown) else None

    def lists_menu(self, pos):
        shown = self.visible_lists()
        item = self.lists_widget.itemAt(pos)
        row = self.lists_widget.row(item) if item else -1
        m = QtWidgets.QMenu(self)
        if 0 <= row < len(shown):
            url = shown[row][1]
            if row > 0:
                m.addAction("move up", lambda: self.move_list(url, -1))
            if row < len(shown) - 1:
                m.addAction("move down", lambda: self.move_list(url, 1))
            m.addAction("hide this list", lambda: self.hide_list(url))
        hidden = [(n, u) for n, u in self.lists if u in set(self.cfg.get("hidden_lists", []))]
        if hidden:
            sub = m.addMenu("show a hidden list")
            for n, u in hidden:
                sub.addAction(n, lambda u=u: self.unhide_list(u))
        m.exec_(self.lists_widget.mapToGlobal(pos))

    def move_list(self, url, delta):
        order = [u for _, u in self.visible_lists()]
        i = order.index(url)
        order.insert(i + delta, order.pop(i))
        self.cfg["list_order"] = order
        save_config(self.cfg)
        self.refresh_lists(keep=self.current_list())

    def hide_list(self, url):
        hidden = [u for u in self.cfg.get("hidden_lists", []) if u != url] + [url]
        if len(hidden) >= len(self.lists):
            return  # keep at least one list on screen
        self.cfg["hidden_lists"] = hidden
        save_config(self.cfg)
        self.refresh_lists(keep=self.current_list() if self.current_list() != url else None)

    def unhide_list(self, url):
        self.cfg["hidden_lists"] = [u for u in self.cfg.get("hidden_lists", []) if u != url]
        save_config(self.cfg)
        self.refresh_lists(keep=url)

    def select_list(self, row):
        url = self.current_list()
        if not url:
            return
        self.cfg["list_url"] = url
        save_config(self.cfg)
        self.sync()

    def sync(self):
        url = self.current_list()
        if not self.client or not url:
            return
        self.status.setText("syncing…")
        self.run(lambda: self.client.tasks(url), self.got_tasks)

    def got_tasks(self, tasks):
        open_tasks = [t for t in tasks if not t.completed and not t.cancelled]
        open_tasks.sort(key=lambda t: (t.due is None, t.due or date.max, t.created))
        self.tasks = open_tasks
        done = [t for t in tasks if t.completed]
        done.sort(key=lambda t: _prop(t.todo_lines, "COMPLETED") or "", reverse=True)
        self.done_tasks = done
        self.render_tasks()
        self.status.setText(f"{len(open_tasks)} open · synced {datetime.now().strftime('%H:%M')}")

    def toggle_done(self):
        self.show_done = not self.show_done
        self.render_tasks()

    def render_tasks(self):
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        i = 0
        for t in self.tasks:
            row = TaskRow(t, self.big, self.small)
            row.completed.connect(self.complete_task)
            row.deleted.connect(self.delete_task)
            self.rows.insertWidget(i, row); i += 1
        if not self.tasks and self.client:
            empty = QtWidgets.QLabel("no open task")
            empty.setObjectName("dim")
            empty.setFont(self.big)
            self.rows.insertWidget(i, empty); i += 1
        if self.show_done:
            for t in self.done_tasks:
                row = TaskRow(t, self.big, self.small, done=True)
                row.reopened.connect(self.reopen_task)
                row.deleted.connect(self.delete_task)
                self.rows.insertWidget(i, row); i += 1
        n = len(self.done_tasks)
        self.done_toggle.setText("" if not n else (f"hide {n} done" if self.show_done else f"show {n} done"))

    def add_task(self):
        text = self.entry.text().strip()
        url = self.current_list()
        if not text or not url or not self.client:
            return
        self.entry.clear()
        self.status.setText("adding…")
        self.run(lambda: self.client.add(url, text), lambda _: self.sync())

    def complete_task(self, task):
        self.tasks = [t for t in self.tasks if t is not task]
        self.render_tasks()
        self.run(lambda: self.client.complete(task), lambda _: self.sync())

    def reopen_task(self, task):
        self.done_tasks = [t for t in self.done_tasks if t is not task]
        self.render_tasks()
        self.run(lambda: self.client.reopen(task), lambda _: self.sync())

    def delete_task(self, task):
        self.tasks = [t for t in self.tasks if t is not task]
        self.done_tasks = [t for t in self.done_tasks if t is not task]
        self.render_tasks()
        self.run(lambda: self.client.delete(task), lambda _: self.sync())


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("reader's tasks")
    app.setDesktopFileName(APP)
    w = Main()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
