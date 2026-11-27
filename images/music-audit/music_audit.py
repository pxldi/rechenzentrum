#!/usr/bin/env python3
"""Compare every audio file's tags with what its audio fingerprint says it is.

`music-audit scan` walks MUSIC_ROOT, fingerprints each file with fpcalc, asks
AcoustID which MusicBrainz recordings that fingerprint belongs to, and records
whether the file's own tags agree. It never writes to MUSIC_ROOT. Results go
to an SQLite database in STATE_DIR, so a run that is stopped picks up where it
left off and a file that has not changed is not fingerprinted twice.

`music-audit report` prints what the last scan found: a summary, the albums
with problems, and one line per problem file.

Statuses:
  ok              the tags name a recording the fingerprint matches
  mbid_differs    title and artist match, but the MusicBrainz recording id in
                  the tags is a different recording (often another version)
  artist_differs  the title matches a fingerprint match, the artist does not
  mismatch        the audio is a different song from the one the tags name
  unidentified    AcoustID knows no recording for this audio
  untagged        the file has no title tag to compare
  unreadable      fpcalc could not decode the file
"""
from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import mutagen

AUDIO = {".flac", ".mp3", ".m4a", ".mp4", ".aac", ".ogg", ".oga", ".opus",
         ".wav", ".aif", ".aiff", ".wma", ".ape", ".wv", ".alac"}
API = "https://api.acoustid.org/v2/lookup"
# AcoustID allows three requests a second per application key.
MIN_INTERVAL = 0.34
# Below this AcoustID's own score is a guess, not a match.
MIN_SCORE = 0.5
PROBLEMS = ("mismatch", "artist_differs", "mbid_differs", "unidentified",
            "untagged", "unreadable")

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    size INTEGER, mtime INTEGER,
    status TEXT,
    tag_artist TEXT, tag_title TEXT, tag_album TEXT, tag_mbid TEXT,
    fp_artist TEXT, fp_title TEXT, fp_mbid TEXT, score REAL,
    detail TEXT, checked_at INTEGER
)
"""


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def norm(text: str) -> str:
    """Lowercase, no accents, no bracketed extras like (feat. X) or [Clean]."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", text)
    text = re.sub(r"\b(feat|ft|featuring)\b.*", " ", text)
    text = re.sub(r"\s-\s.*(remaster|version|edit|mix|live).*$", " ", text)
    text = text.replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def similar(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def first(tags, key: str) -> str:
    try:
        value = tags.get(key)
    except (KeyError, ValueError):
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def read_tags(path: Path) -> dict:
    try:
        audio = mutagen.File(path, easy=True)
    except Exception as exc:  # mutagen raises many kinds on a broken header
        return {"error": f"tags: {exc}"}
    if audio is None or audio.tags is None:
        return {}
    tags = audio.tags
    return {
        "artist": first(tags, "artist") or first(tags, "albumartist"),
        "title": first(tags, "title"),
        "album": first(tags, "album"),
        "mbid": first(tags, "musicbrainz_trackid"),
    }


def fingerprint(path: Path) -> tuple[int, str] | str:
    try:
        out = subprocess.run(["fpcalc", "-json", "-length", "120", str(path)],
                             capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "fpcalc timed out"
    if out.returncode != 0:
        return (out.stderr or out.stdout).strip()[:300] or f"fpcalc exit {out.returncode}"
    data = json.loads(out.stdout)
    return int(data["duration"]), data["fingerprint"]


class AcoustID:
    def __init__(self, key: str):
        self.key = key
        self.last = 0.0

    def lookup(self, duration: int, fp: str) -> list:
        body = urllib.parse.urlencode({
            "client": self.key, "format": "json", "meta": "recordings",
            "duration": duration, "fingerprint": fp,
        }).encode()
        for attempt in range(6):
            wait = self.last + MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                with urllib.request.urlopen(urllib.request.Request(API, data=body), timeout=30) as r:
                    data = json.load(r)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                code = getattr(exc, "code", None)
                if code == 400:
                    raise SystemExit(f"AcoustID refused the request (400). Is ACOUSTID_KEY right? {exc}")
                time.sleep(min(60, 2 ** attempt))
                continue
            if data.get("status") != "ok":
                err = data.get("error", {})
                if err.get("code") in (4, 5):  # invalid or missing application key
                    raise SystemExit(f"AcoustID rejected the key: {err}")
                time.sleep(min(60, 2 ** attempt))
                continue
            return data.get("results", [])
        raise RuntimeError("AcoustID did not answer after 6 attempts")


def classify(tags: dict, results: list) -> dict:
    recordings = []
    for result in results:
        if result.get("score", 0) < MIN_SCORE:
            continue
        for rec in result.get("recordings", []) or []:
            if rec.get("title"):
                artists = " & ".join(a.get("name", "") for a in rec.get("artists", []) or [])
                recordings.append((result["score"], rec["id"], rec["title"], artists))
    if not tags.get("title"):
        status = "untagged" if recordings else "unidentified"
        best = recordings[0] if recordings else (None, "", "", "")
        return {"status": status, "score": best[0], "fp_mbid": best[1],
                "fp_title": best[2], "fp_artist": best[3]}
    if not recordings:
        best = max((r.get("score", 0) for r in results), default=None)
        return {"status": "unidentified", "score": best}

    def rank(rec):
        return (similar(tags["title"], rec[2]), similar(tags["artist"], rec[3]), rec[0])

    best = max(recordings, key=rank)
    title_ok = similar(tags["title"], best[2]) >= 0.85
    artist_ok = not tags["artist"] or similar(tags["artist"], best[3]) >= 0.6
    ids = {r[1] for r in recordings}
    if tags.get("mbid") and tags["mbid"] in ids:
        status = "ok"
        best = next(r for r in recordings if r[1] == tags["mbid"])
    elif title_ok and artist_ok:
        status = "mbid_differs" if tags.get("mbid") else "ok"
    elif title_ok:
        status = "artist_differs"
    else:
        status = "mismatch"
        best = max(recordings, key=lambda r: r[0])
    return {"status": status, "score": best[0], "fp_mbid": best[1],
            "fp_title": best[2], "fp_artist": best[3]}


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if Path(name).suffix.lower() in AUDIO:
                yield Path(dirpath) / name


def scan(args) -> None:
    key = os.environ.get("ACOUSTID_KEY", "").strip()
    if not key or key == "REPLACE_ME":
        raise SystemExit("ACOUSTID_KEY is not set")
    root = Path(args.root)
    db = sqlite3.connect(Path(args.state) / "audit.sqlite")
    db.execute(SCHEMA)
    known = {row[0]: (row[1], row[2], row[3]) for row in
             db.execute("SELECT path, size, mtime, status FROM files")}
    todo = []
    seen = set()
    for path in walk(root):
        rel = str(path.relative_to(root))
        seen.add(rel)
        st = path.stat()
        prev = known.get(rel)
        if prev and prev[0] == st.st_size and prev[1] == int(st.st_mtime) and prev[2] != "error":
            continue
        todo.append((path, rel, st))
    gone = set(known) - seen
    if gone:
        db.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in gone])
        db.commit()
    log(f"{len(seen)} audio files under {root}, {len(todo)} to check, {len(gone)} gone since last scan")
    if args.limit:
        todo = todo[:args.limit]

    api = AcoustID(key)
    counts: dict[str, int] = {}
    started = time.monotonic()

    def prepare(item):
        path, rel, st = item
        return item, read_tags(path), fingerprint(path)

    def prepared():
        # fpcalc runs ahead of the lookups that need it, one chunk at a time,
        # so a fast disc cannot pile up fingerprints in memory.
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for i in range(0, len(todo), 50):
                yield from pool.map(prepare, todo[i:i + 50])

    for n, ((path, rel, st), tags, fp) in enumerate(prepared(), 1):
        row = {"tag_artist": tags.get("artist", ""), "tag_title": tags.get("title", ""),
               "tag_album": tags.get("album", ""), "tag_mbid": tags.get("mbid", ""),
               "detail": tags.get("error", "")}
        if isinstance(fp, str):
            row.update(status="unreadable", detail=fp)
        else:
            try:
                row.update(classify(tags, api.lookup(*fp)))
            except RuntimeError as exc:
                row.update(status="error", detail=str(exc))
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        db.execute(
            "INSERT OR REPLACE INTO files VALUES (:path,:size,:mtime,:status,:tag_artist,"
            ":tag_title,:tag_album,:tag_mbid,:fp_artist,:fp_title,:fp_mbid,:score,:detail,:now)",
            {"fp_artist": "", "fp_title": "", "fp_mbid": "", "score": None, **row,
             "path": rel, "size": st.st_size, "mtime": int(st.st_mtime), "now": int(time.time())})
        if n % 100 == 0 or n == len(todo):
            db.commit()
        if n % 500 == 0 or n == len(todo):
            rate = n / max(1.0, time.monotonic() - started)
            left = (len(todo) - n) / rate / 3600 if rate else 0
            log(f"{n}/{len(todo)} checked, {rate:.1f}/s, ~{left:.1f} h left, {counts}")
    db.commit()
    report(args)


def report(args) -> None:
    db = sqlite3.connect(Path(args.state) / "audit.sqlite")
    db.execute(SCHEMA)
    total = db.execute("SELECT count(*) FROM files").fetchone()[0]
    print(f"\n== Summary: {total} files")
    for status, n in db.execute("SELECT status, count(*) FROM files GROUP BY status ORDER BY 2 DESC"):
        print(f"{status:15} {n}")

    print("\n== Albums with mismatches (folder, mismatched/total)")
    albums = {}
    for path, status in db.execute("SELECT path, status FROM files"):
        folder = str(Path(path).parent)
        bad, all_ = albums.get(folder, (0, 0))
        albums[folder] = (bad + (status in ("mismatch", "artist_differs")), all_ + 1)
    for folder, (bad, all_) in sorted(albums.items(), key=lambda x: (-x[1][0] / x[1][1], x[0])):
        if bad:
            print(f"{bad}/{all_}\t{folder}")

    print("\n== Problem files (status, path, tags say, fingerprint says, score)")
    marks = ",".join("?" * len(PROBLEMS))
    for row in db.execute(
            f"SELECT status, path, tag_artist, tag_title, fp_artist, fp_title, score, detail "
            f"FROM files WHERE status IN ({marks}) OR status = 'error' ORDER BY status, path", PROBLEMS):
        status, path, ta, tt, fa, ft, score, detail = row
        said = f"{fa} - {ft}" if ft else (detail or "")
        print(f"{status}\t{path}\t{ta} - {tt}\t{said}\t{score if score is not None else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["scan", "report"])
    parser.add_argument("--root", default=os.environ.get("MUSIC_ROOT", "/music"))
    parser.add_argument("--state", default=os.environ.get("STATE_DIR", "/state"))
    parser.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "2")))
    parser.add_argument("--limit", type=int, default=int(os.environ.get("LIMIT", "0")),
                        help="check at most this many files (0: all)")
    args = parser.parse_args()
    scan(args) if args.mode == "scan" else report(args)


if __name__ == "__main__":
    sys.exit(main())
