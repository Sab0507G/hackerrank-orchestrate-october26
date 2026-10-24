"""Evidence indexing for the deletion audit.

Scans every evidence file captured at or before a case's audit_at and returns
the records that belong to a user, matched by any of the user's identifiers.
Each hit records the file_id that proves it, so findings can cite evidence.

Supported formats: SQLite-compatible SQL snapshots, JSON exports, and text logs.
PDFs and images are not parsed here yet (see README gap list).
"""
import csv
import json
import re
import sqlite3
from pathlib import Path

from identity import norm_email, norm_phone

RESOURCE_ID_RE = re.compile(r"\b([a-z]+(?:_[a-z]+)*_\d+)\b")


class Evidence:
    def __init__(self, dataset_dir: Path):
        self.dataset_dir = Path(dataset_dir)
        self.files = []  # list of dicts: file_id, path, captured_at, origin
        with open(self.dataset_dir / "evidence_files.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.files.append(row)
        self._sql_cache = {}

    def files_as_of(self, audit_at: str):
        """Evidence captured at or before audit_at. Later evidence must not affect the answer."""
        return [f for f in self.files if f["captured_at"] <= audit_at]

    def _sql_db(self, file_id: str, rel_path: str) -> sqlite3.Connection:
        if file_id not in self._sql_cache:
            conn = sqlite3.connect(":memory:")
            script = (self.dataset_dir / rel_path).read_text(encoding="utf-8")
            conn.executescript(script)
            self._sql_cache[file_id] = conn
        return self._sql_cache[file_id]

    @staticmethod
    def _matches(value, idents) -> bool:
        if value is None:
            return False
        s = str(value).strip()
        low = s.lower()
        if low in idents["emails"] or low in idents["email_hashes"] or low in idents["user_ids"]:
            return True
        digits = norm_phone(s)
        if digits and len(digits) >= 7 and digits in idents["phones"]:
            return True
        return False

    def find_sql_hits(self, file_row, idents):
        hits = []
        conn = self._sql_db(file_row["file_id"], file_row["file_path"])
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            if table == "snapshot_scope":
                continue
            cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{table}")')]
            for row in conn.execute(f'SELECT * FROM "{table}"'):
                rec = dict(zip(cols, row))
                if any(self._matches(v, idents) for v in rec.values()):
                    rid = rec.get("resource_id")
                    hits.append({
                        "file_id": file_row["file_id"],
                        "source": "sql",
                        "table": table,
                        "resource_id": rid,
                        "record": rec,
                    })
        return hits

    def find_json_hits(self, file_row, idents):
        hits = []
        path = self.dataset_dir / file_row["file_path"]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return hits

        def walk(node, context):
            if isinstance(node, dict):
                ctx = dict(context)
                for k in ("data_store", "collection", "captured_at", "region"):
                    if k in node:
                        ctx[k] = node[k]
                if "resource_id" in node and any(
                    self._matches(v, idents) for v in node.values() if not isinstance(v, (dict, list))
                ):
                    hits.append({
                        "file_id": file_row["file_id"],
                        "source": "json",
                        "table": ctx.get("collection"),
                        "data_store": ctx.get("data_store"),
                        "captured_at": ctx.get("captured_at"),
                        "resource_id": node.get("resource_id"),
                        "record": node,
                    })
                for v in node.values():
                    walk(v, ctx)
            elif isinstance(node, list):
                for v in node:
                    walk(v, context)

        walk(data, {})
        return hits

    def find_text_hits(self, file_row, idents):
        hits = []
        path = self.dataset_dir / file_row["file_path"]
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return hits
        for lineno, line in enumerate(lines, 1):
            low = line.lower()
            found = any(e in low for e in idents["emails"] if e) or any(
                h in low for h in idents["email_hashes"] if h
            ) or any(u in low for u in idents["user_ids"] if u)
            if not found:
                digits_line = norm_phone(line)
                found = any(p and len(p) >= 7 and p in digits_line for p in idents["phones"])
            if found:
                rids = RESOURCE_ID_RE.findall(line)
                hits.append({
                    "file_id": file_row["file_id"],
                    "source": "text",
                    "table": None,
                    "resource_id": rids[0] if rids else None,
                    "resource_ids": rids,
                    "line_no": lineno,
                    "line": line,
                })
        return hits

    def find_all(self, audit_at: str, idents) -> list:
        hits = []
        for f in self.files_as_of(audit_at):
            p = f["file_path"]
            if p.endswith(".sql"):
                hits.extend(self.find_sql_hits(f, idents))
            elif p.endswith(".json"):
                hits.extend(self.find_json_hits(f, idents))
            elif p.endswith(".log") or p.endswith(".txt"):
                hits.extend(self.find_text_hits(f, idents))
        return hits
