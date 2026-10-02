import hashlib
import json
import math
import os
import sqlite3
import threading
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get("DATA_DIR", str(ROOT / ".data"))) / "intake.sqlite3"
LOCK = threading.RLock()


@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE IF NOT EXISTS batches (digest TEXT PRIMARY KEY, report TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS records (batch TEXT, id TEXT, text TEXT, label TEXT, PRIMARY KEY(batch,id))"
    )
    try:
        with db:
            yield db
    finally:
        db.close()


def validate_row(row):
    if not isinstance(row, dict):
        return "record must be an object"
    if not isinstance(row.get("id"), str) or not row["id"].strip():
        return "missing string id"
    if not isinstance(row.get("text"), str) or not row["text"].strip():
        return "missing text"
    if len(row["text"]) > 10000:
        return "text exceeds 10000 characters"
    if not isinstance(row.get("label"), str) or row.get("label") not in {
        "positive",
        "negative",
        "neutral",
    }:
        return "unknown label"
    return None


def js_divergence(left, right):
    categories = set(left) | set(right)
    ltotal, rtotal = sum(left.values()), sum(right.values())
    if not ltotal or not rtotal:
        return None
    total = 0
    for key in categories:
        p, q = left.get(key, 0) / ltotal, right.get(key, 0) / rtotal
        m = (p + q) / 2
        if p:
            total += 0.5 * p * math.log2(p / m)
        if q:
            total += 0.5 * q * math.log2(q / m)
    return total


def ingest(lines):
    if not isinstance(lines, str) or not lines.strip():
        raise ValueError("Provide JSONL records")
    if len(lines.encode()) > 1_000_000 or len(lines.splitlines()) > 5000:
        raise ValueError("Limit: 1 MB and 5000 lines")
    digest = hashlib.sha256(lines.encode()).hexdigest()
    with LOCK, connect() as db:
        existing = db.execute(
            "SELECT report FROM batches WHERE digest=?", (digest,)
        ).fetchone()
        if existing:
            return {**json.loads(existing["report"]), "replayed": True}
        previous = Counter(
            {
                r["label"]: r["n"]
                for r in db.execute(
                    "SELECT label,COUNT(*) n FROM records GROUP BY label"
                )
            }
        )
        accepted, quarantine, seen = [], [], set()
        for number, raw in enumerate(lines.splitlines(), 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
                reason = validate_row(row)
                if not reason and row["id"] in seen:
                    reason = "duplicate id in batch"
                if reason:
                    quarantine.append({"line": number, "reason": reason, "raw": raw})
                else:
                    seen.add(row["id"])
                    accepted.append(row)
            except json.JSONDecodeError:
                quarantine.append(
                    {"line": number, "reason": "invalid JSON", "raw": raw}
                )
        distribution = Counter(r["label"] for r in accepted)
        drift = js_divergence(previous, distribution)
        report = {
            "batch": digest[:12],
            "digest": digest,
            "accepted": len(accepted),
            "rejected": len(quarantine),
            "quarantine": quarantine,
            "distribution": dict(distribution),
            "reference": dict(previous),
            "drift": drift,
            "warning": drift is not None and drift > 0.15,
            "replayed": False,
        }
        db.executemany(
            "INSERT INTO records VALUES(?,?,?,?)",
            [(digest, r["id"], r["text"], r["label"]) for r in accepted],
        )
        db.execute("INSERT INTO batches VALUES(?,?)", (digest, json.dumps(report)))
        return report


def snapshot():
    with LOCK, connect() as db:
        reports = [
            json.loads(r["report"])
            for r in db.execute(
                "SELECT report FROM batches ORDER BY rowid DESC LIMIT 20"
            )
        ]
        distribution = {
            r["label"]: r["n"]
            for r in db.execute("SELECT label,COUNT(*) n FROM records GROUP BY label")
        }
    return {
        "batches": reports,
        "distribution": distribution,
        "total": sum(distribution.values()),
        "sample": (ROOT / "data/sample.jsonl").read_text(),
        "shift": (ROOT / "data/shift.jsonl").read_text(),
    }


def handle(path, body):
    if path != "/api/ingest":
        raise ValueError("Unknown endpoint")
    return ingest(body.get("lines"))
