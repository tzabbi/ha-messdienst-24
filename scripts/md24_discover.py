#!/usr/bin/env python3
"""Loggt sich bei legacy.messdienst24.de ein und speichert alle Menüseiten.

Zweck: herausfinden, auf welcher Seite und in welcher Struktur die Zählerwerte
stehen, damit die Home-Assistant-Anbindung gezielt darauf zugreifen kann.

Nur Standardbibliothek. Zugangsdaten kommen aus credentials.ini (siehe
credentials.ini.example). Ausgabe landet in ./dump/ (enthält persönliche Daten!).
"""

import configparser
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://legacy.messdienst24.de"
HERE = Path(__file__).resolve().parent
DUMP = HERE / "dump"

# Aktionen, die etwas verändern/versenden könnten, werden nie aufgerufen.
UNSAFE = re.compile(r"send|lock|create|del|save|upload|logout|lostpw|verball", re.I)


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._stack, self._cell = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._stack[-1].append([])
        elif tag in ("td", "th") and self._stack:
            self._cell = []
        elif tag == "input" and self._cell is not None:
            value = dict(attrs).get("value")
            if value:
                self._cell.append(value)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._stack:
            if not self._stack[-1]:
                self._stack[-1].append([])
            self._stack[-1][-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def main():
    cfg = configparser.ConfigParser()
    if not cfg.read(HERE / "credentials.ini", encoding="utf-8"):
        sys.exit("credentials.ini fehlt (Vorlage: credentials.ini.example)")
    sec = cfg["messdienst24"]
    md = sec.get("md", "ex")

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (md24-discover)"),
        ("X-Requested-With", "XMLHttpRequest"),
    ]

    def get(path, **params):
        url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
        with opener.open(url, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    def post(**data):
        body = urllib.parse.urlencode(data).encode()
        with opener.open(f"{BASE}/", data=body, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    DUMP.mkdir(exist_ok=True)

    get("/", md=md)  # Session-Cookie
    get("/", action="", node="content", acceptds="1")  # Datenschutz akzeptieren
    page = get(
        "/index.htm",
        action="",
        node="page",
        username=sec["username"],
        password=sec["password"],
    )
    (DUMP / "_after_login.html").write_text(page, encoding="utf-8")

    if 'id="login_dialog"' in page or "inppassword" in page:
        sys.exit("Login fehlgeschlagen? Siehe dump/_after_login.html")

    skip = {"datenschutz", "impressum", "login", "usersetting", "usermailsetting"}
    action_re = re.compile(r"""(?:href="\?action=|action:')([a-zA-Z0-9_]+)""")

    def find_actions(html):
        return {a for a in action_re.findall(html) if not UNSAFE.search(a)} - skip

    queue = sorted(find_actions(page))
    seen = set(queue)
    print("Gefundene Aktionen:", ", ".join(queue) or "(keine)")

    while queue:
        action = queue.pop(0)
        html = post(action=action, node="content")
        (DUMP / f"{action}.html").write_text(html, encoding="utf-8")
        for new in sorted(find_actions(html) - seen):
            seen.add(new)
            queue.append(new)
        tp = TableParser()
        tp.feed(html)
        print(f"\n=== {action}: {len(html)} Bytes, {len(tp.tables)} Tabelle(n)")
        for i, table in enumerate(tp.tables):
            rows = [r for r in table if any(c for c in r)]
            print(f"  -- Tabelle {i} ({len(rows)} Zeilen)")
            for row in rows[:8]:
                print("    | " + " | ".join(row))

    print(f"\nRohdaten gespeichert in {DUMP}")


if __name__ == "__main__":
    main()
