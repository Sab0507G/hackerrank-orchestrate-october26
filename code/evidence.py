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



def _parse_json_maybe(text):
    if not isinstance(text, str):
        return None
    s = text.strip()
    if not (s.startswith("{") or s.startswith("[")):
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _deep_match(obj, idents, _depth=0) -> bool:
    """True if any leaf value in obj (recursively, including JSON-encoded strings) is an identifier."""
    if _depth > 12:
        return False
    if isinstance(obj, dict):
        return any(_deep_match(v, idents, _depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return any(_deep_match(v, idents, _depth + 1) for v in obj)
    if isinstance(obj, str):
        parsed = _parse_json_maybe(obj)
        if parsed is not None:
            return _deep_match(parsed, idents, _depth + 1)
    return Evidence._matches(obj, idents)

TRACE_RE = re.compile(r'trace_id(?:=|"\s*:\s*")([A-Za-z0-9._-]+)')


def _trace_ids(line: str):
    return set(TRACE_RE.findall(line))

HANDOVER_RE = re.compile(
    r"^-\s*(?P<ts>\S+)\s*\|\s*(?P<system>[^|]+?)\s*\|\s*(?P<rid>[^|]+?)\s*\|\s*(?P<category>[^|]+?)\s*\|\s*(?P<state>[^|]+?)\s*\|\s*(?P<ident>\S+)\s*$"
)

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

    @staticmethod
    def direct_identifier_present(rec, idents) -> bool:
        """True if the record still carries an email, phone, hash, or name (user_id alone does not count)."""
        def scan(obj, depth=0):
            if depth > 12:
                return False
            if isinstance(obj, dict):
                return any(scan(v, depth + 1) for v in obj.values())
            if isinstance(obj, list):
                return any(scan(v, depth + 1) for v in obj)
            if isinstance(obj, str):
                p = _parse_json_maybe(obj)
                if p is not None:
                    return scan(p, depth + 1)
                low = obj.strip().lower()
                if low in idents["emails"] or low in idents["email_hashes"]:
                    return True
                if low and low in idents.get("names", set()):
                    return True
                d = norm_phone(obj)
                return bool(d) and len(d) >= 7 and d in idents["phones"]
            return False
        return scan(rec)

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
                if _deep_match(rec, idents):
                    rid = rec.get("resource_id")
                    exposed = self.direct_identifier_present(rec, idents)
                    if not rid:
                        for v in rec.values():
                            p = _parse_json_maybe(v)
                            if isinstance(p, dict) and p.get("resource_id"):
                                rid = p["resource_id"]
                                break
                    hits.append({
                        "exposed": exposed,
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
            hm = HANDOVER_RE.match(line.strip())
            if hm:
                ident = hm.group("ident").lower()
                if ident in idents["emails"] or ident in idents["email_hashes"]:
                    hits.append({
                        "file_id": file_row["file_id"],
                        "source": "handover",
                        "table": hm.group("category").strip(),
                        "resource_id": hm.group("rid").strip(),
                        "resource_ids": [hm.group("rid").strip()],
                        "state": hm.group("state").strip().upper(),
                        "system": hm.group("system").strip(),
                        "line_no": lineno,
                        "line": line,
                    })
                continue
            low = line.lower()
            found = any(e in low for e in idents["emails"] if e) or any(
                h in low for h in idents["email_hashes"] if h
            ) or any(u in low for u in idents["user_ids"] if u)
            if not found:
                digits_line = norm_phone(line)
                found = any(p and len(p) >= 7 and p in digits_line for p in idents["phones"])
            if not found:
                brace = line.find("{")
                if brace >= 0:
                    parsed = _parse_json_maybe(line[brace:])
                    if parsed is not None and _deep_match(parsed, idents):
                        found = True
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


    def propagate_traces(self, audit_at: str, hits: list) -> list:
        """Log lines sharing a trace_id with a matched line are the same request, so they belong to the same user."""
        text_files = [f for f in self.files_as_of(audit_at)
                      if f["file_path"].endswith((".log", ".txt"))]
        traces = set()
        for h in hits:
            if h.get("source") == "text":
                traces |= _trace_ids(h["line"])
        if not traces:
            return hits
        extra = []
        for f in text_files:
            path = self.dataset_dir / f["file_path"]
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                ids = _trace_ids(line)
                if ids & traces:
                    rids = RESOURCE_ID_RE.findall(line)
                    if rids:
                        extra.append({
                            "file_id": f["file_id"],
                            "source": "text_trace",
                            "table": None,
                            "resource_id": rids[0],
                            "resource_ids": rids,
                            "line_no": lineno,
                            "line": line,
                        })
        return hits + extra

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
        return self.propagate_traces(audit_at, hits)
