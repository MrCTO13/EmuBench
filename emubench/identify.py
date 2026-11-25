"""Offline edition lookup using opt-in, revision-pinned No-Intro metadata."""
from contextlib import closing
import hashlib
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

from . import downloads, engines

COMMIT = "f89f09cbe13f9f7863ecf20d0ebf2c5ce53be029"
CATALOGS = {"gba": ("Game Boy Advance","6b54ff4f66f3ffdca0dd0dd4fc2bb855e016faf2dd58a5017db20c7b30171b06"),
            "snes": ("Super Nintendo Entertainment System","c46a41df05343c66c0a4d40cb13570ea9806a8539318667656fcbc835ae1c568")}


def install(console):
    name, digest = CATALOGS[console]
    url = f"https://raw.githubusercontent.com/libretro/libretro-database/{COMMIT}/metadat/no-intro/" + quote("Nintendo - "+name+".dat")
    raw = downloads.fetch_bytes(url, 16*1024**2)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Catalog failed its published digest check")
    rows = []
    for block in raw.decode().split("\ngame (")[1:]:
        title = re.search(r'^\s*name "([^"\n]+)"', block)
        hashes = re.findall(r'\bsha1 ([A-Fa-f0-9]{40})\b', block)
        if title and len(hashes)==1:
            rows.append((console, hashes[0].lower(), title[1]))
    if not rows:
        raise ValueError("No single-cartridge entries in catalog")
    root = engines.home()
    root.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(root/"editions.sqlite")) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS editions(console TEXT, digest TEXT, title TEXT, PRIMARY KEY(console,digest))")
        db.execute("DELETE FROM editions WHERE console=?", (console,))
        db.executemany("INSERT OR IGNORE INTO editions VALUES(?,?,?)",rows)
    return len(rows)


def match(console, data):
    path = engines.home()/"editions.sqlite"
    if not path.is_file():
        return None
    if console=="snes" and len(data)%32768==512:
        data=data[512:]
    with closing(sqlite3.connect(path)) as db:
        entry=db.execute("SELECT title FROM editions WHERE console=? AND digest=?",
                         (console,hashlib.sha1(data).hexdigest())).fetchone()
    if not entry:
        return None
    name=entry[0]
    # The cross-device edition identifier derives from catalog text, never from the private cartridge bytes.
    token=hashlib.sha256(("no-intro-v1/"+console+"/"+name).encode()).hexdigest()
    public = "".join(c if c.isalnum() or c in " .,'’()+&!_-" else " " for c in name)
    return {"edition":token,"title":" ".join(public.split())[:90]}
