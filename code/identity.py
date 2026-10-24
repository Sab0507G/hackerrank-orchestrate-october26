"""Identity resolution for the deletion audit.

Resolves a request email (current or historical) to a stable user_id and
collects every identifier that user has ever had, so later evidence scans
can match on any of them.
"""
import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def norm_email(email: str) -> str:
    return (email or "").strip().lower()


def norm_phone(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


class IdentityIndex:
    def __init__(self, dataset_dir: Path):
        self.dataset_dir = Path(dataset_dir)
        self.users = {}                      # user_id -> current row
        self.email_to_users = defaultdict(set)  # normalized email/hash -> user_ids
        self.history = defaultdict(list)     # user_id -> list of audit events
        self._load()

    def _load(self):
        with open(self.dataset_dir / "user_identities.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                uid = row["user_id"]
                self.users[uid] = row
                self.email_to_users[norm_email(row["email"])].add(uid)
                self.email_to_users[row["email_hash"].lower()].add(uid)

        with open(self.dataset_dir / "user_audit_log.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                uid = row["user_id"]
                self.history[uid].append(row)
                if row["field_name"] == "email":
                    for val in (row["old_value"], row["new_value"]):
                        if val:
                            self.email_to_users[norm_email(val)].add(uid)
                if row["field_name"] == "email_hash":
                    for val in (row["old_value"], row["new_value"]):
                        if val:
                            self.email_to_users[val.lower()].add(uid)

    def resolve(self, email: str) -> set:
        """Return all user_ids that this email (current or historical) can belong to."""
        key = norm_email(email)
        matches = set(self.email_to_users.get(key, set()))
        matches |= set(self.email_to_users.get(sha256_hex(key), set()))
        return matches

    def identifiers(self, user_id: str, as_of: str | None = None) -> dict:
        """All identifiers ever associated with user_id, up to as_of (ISO timestamp)."""
        cur = self.users[user_id]
        emails = {norm_email(cur["email"])}
        phones = {norm_phone(cur["phone"])}
        hashes = {cur["email_hash"].lower()}
        names = {cur["name"].strip().lower()}
        for ev in self.history.get(user_id, []):
            if as_of and ev["event_time"] > as_of:
                continue
            f = ev["field_name"]
            if f == "email":
                emails.add(norm_email(ev["old_value"]))
            elif f == "phone":
                phones.add(norm_phone(ev["old_value"]))
            elif f == "email_hash":
                hashes.add(ev["old_value"].lower())
        for e in list(emails):
            hashes.add(sha256_hex(e))
        emails.discard("")
        phones.discard("")
        return {
            "user_id": user_id,
            "emails": sorted(emails),
            "phones": sorted(phones),
            "email_hashes": sorted(hashes),
            "names": sorted(names),
        }


LINK_DETAIL_RE = re.compile(r"linked\s+\S+\s+\((\S+)\)\s+to\s+(\S+)\s+and\s+(user_\d+)", re.IGNORECASE)


def load_catalog_links(dataset_dir: Path):
    """resource_id -> list of (event_time, user_id) from data_catalog LINK_RESOURCE_IDENTITY events."""
    links = defaultdict(list)
    with open(Path(dataset_dir) / "system_activity.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["event_type"] != "LINK_RESOURCE_IDENTITY" or row["reported_result"] != "SUCCESS":
                continue
            m = LINK_DETAIL_RE.search(row["details"])
            if m:
                links[row["resource_id"]].append((row["event_time"], m.group(3)))
    return links
