"""End-to-end deletion audit: resolve identity, scan evidence, apply rules, emit steps."""
import csv
import json
from collections import defaultdict
from pathlib import Path

from identity import IdentityIndex, load_catalog_links
from request_intent import is_deletion_request
from evidence import Evidence
from rules import classify_resource, build_steps, serialize, RETAIN_CATEGORIES, STATE_OF as _STATE_OF

STATE_OF_VERIFY = _STATE_OF
REDACT_CATEGORIES = {"SUPPORT_MESSAGE", "ACCOUNT_TOMBSTONE", "EMAIL_DELIVERY_LOG"}

DELETE_CATEGORIES = {"USER_PROFILE", "SEARCH_INDEX_ENTRY", "USER_EXPORT", "MARKETING_PROFILE",
                     "SUPPORT_ATTACHMENT", "SUPPORT_MESSAGE", "CACHE_ENTRY", "EMAIL_DELIVERY_LOG"}
ANONYMIZE_CATEGORIES = {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"}


HANDOVER_CATEGORY = {
    "USER_PROFILE": "USER_PROFILE", "SEARCH_INDEX_ENTRY": "SEARCH_INDEX_ENTRY",
    "ANALYTICS_PROFILE": "ANALYTICS_PROFILE", "SUPPORT_MESSAGE": "SUPPORT_MESSAGE",
    "SUPPORT_ATTACHMENT": "SUPPORT_ATTACHMENT", "DATA_FLOW": "DATA_FLOW",
    "BACKUP_ARCHIVE": "BACKUP_ARCHIVE", "ACCOUNT_TOMBSTONE": "ACCOUNT_TOMBSTONE",
    "SECURITY_AUDIT_LOG": "SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD": "LEGAL_HOLD_RECORD",
    "EMAIL_DELIVERY_LOG": "EMAIL_DELIVERY_LOG", "USER_EXPORT": "USER_EXPORT",
    "MARKETING_PROFILE": "MARKETING_PROFILE",
}
EXPOSED_STATES = {"FOUND", "IDENTIFIABLE", "ACTIVE", "PRESENT"}
TREATED_STATES = {"ANONYMIZED", "REDACTED", "BLOCKED", "DISABLED"}
ABSENT_STATES = {"NOT_FOUND", "ABSENT", "DELETED"}


def _case_resources(uid, audit_at, idents, ev, links):
    """Per-resource evidence summary attributable to the user at audit_at."""
    res = defaultdict(lambda: {"file_ids": set(), "exposed": False, "states": [], "category": None})
    for h in ev.find_all(audit_at, idents):
        rid = h.get("resource_id")
        if not rid:
            continue
        info = res[rid]
        info["file_ids"].add(h["file_id"])
        if h.get("source") == "handover":
            info["states"].append((h["state"], h["file_id"]))
            info["category"] = HANDOVER_CATEGORY.get(h["table"], info["category"])
        elif h.get("exposed") or h.get("source") == "json":
            info["exposed"] = True
    for rid, ls in links.items():
        if any(u == uid and t <= audit_at for t, u in ls):
            res[rid]["file_ids"]  # linked resource, presence evaluated below
    return res


def _classify(rid, info):
    """Return (system_id, category)."""
    system, category = classify_resource(rid)
    if info.get("category"):
        category = info["category"]
    return system, category


def decide(request, idx, ev, links, classify_nonde=frozenset()):
    # Deletion must be authorized by the request text; evidence alone never makes a case deletion.
    if not is_deletion_request(request["request_text"]):
        return "NOT_APPLICABLE", []
    matches = sorted(idx.resolve(request["email"]))
    if not matches:
        # Authorized deletion for an email with no identity or evidence: nothing to remove or verify.
        return "COMPLETE", []
    uid = matches[0]
    I = idx.identifiers(uid, request["audit_at"])
    idents = {
        "emails": set(I["emails"]),
        "phones": set(I["phones"]),
        "email_hashes": set(I["email_hashes"]),
        "names": set(I["names"]),
        "user_ids": {uid.lower()},
    }
    res = _case_resources(uid, request["audit_at"], idents, ev, links)

    findings, verifications = [], []
    for rid, info in sorted(res.items()):
        system, category = _classify(rid, info)
        evid = sorted(info["file_ids"])[0] if info["file_ids"] else ""
        state = None
        for st, fid in info["states"]:
            state = st
            evid = fid
        if category in RETAIN_CATEGORIES:
            verifications.append({"phase": "VERIFICATION", "system_id": system, "resource_id": rid,
                                  "operation": "VERIFY_RECORD_PRESENT", "state": "PRESENT",
                                  "evidence_id": evid})
            continue
        if state in ABSENT_STATES:
            verifications.append({"phase": "VERIFICATION", "system_id": system, "resource_id": rid,
                                  "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT",
                                  "evidence_id": evid})
            continue
        exposed = (state in EXPOSED_STATES) if state else info["exposed"]
        if state in TREATED_STATES:
            treated_op = {"ANONYMIZED": "VERIFY_RECORD_ANONYMIZED", "REDACTED": "VERIFY_RECORD_REDACTED",
                          "BLOCKED": "VERIFY_RESTORE_BLOCKED", "DISABLED": "VERIFY_DATA_FLOW_DISABLED"}[state]
            verifications.append({"phase": "VERIFICATION", "system_id": system, "resource_id": rid,
                                  "operation": treated_op, "state": STATE_OF_VERIFY[treated_op],
                                  "evidence_id": evid})
            continue
        if not exposed:
            if category in DELETE_CATEGORIES or category in ANONYMIZE_CATEGORIES or category in REDACT_CATEGORIES:
                verifications.append({"phase": "VERIFICATION", "system_id": system, "resource_id": rid,
                                      "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT",
                                      "evidence_id": evid})
            continue
        # exposed: choose operation by category
        if category == "DATA_FLOW":
            findings.append({"system_id": system, "resource_id": rid,
                             "operation": "REPORT_ACTIVE_DATA_FLOW", "evidence_id": evid})
        elif category == "BACKUP_ARCHIVE":
            findings.append({"system_id": system, "resource_id": rid,
                             "operation": "REPORT_RESTORE_RISK", "evidence_id": evid})
        elif category in ANONYMIZE_CATEGORIES:
            findings.append({"system_id": system, "resource_id": rid, "operation": "REPORT_EXPOSED_PII",
                             "evidence_id": evid, "remedy": "ANONYMIZE_RECORD",
                             "verify": "VERIFY_RECORD_ANONYMIZED"})
        elif category in REDACT_CATEGORIES:
            findings.append({"system_id": system, "resource_id": rid, "operation": "REPORT_EXPOSED_PII",
                             "evidence_id": evid, "remedy": "REDACT_RECORD",
                             "verify": "VERIFY_RECORD_REDACTED"})
        elif category in DELETE_CATEGORIES:
            findings.append({"system_id": system, "resource_id": rid,
                             "operation": "REPORT_REMAINING_RECORD", "evidence_id": evid})

    status = "INCOMPLETE" if findings else "COMPLETE"
    steps = build_steps(findings, verifications, status)
    return status, steps


def run(dataset_dir: Path, requests_csv: Path, out_csv: Path | None = None):
    idx = IdentityIndex(dataset_dir)
    ev = Evidence(dataset_dir)
    links = load_catalog_links(dataset_dir)
    rows = list(csv.DictReader(open(requests_csv, newline="", encoding="utf-8")))
    results = {}
    for r in rows:
        status, steps = decide(r, idx, ev, links)
        results[r["case_id"]] = (status, steps)
    if out_csv:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["case_id", "deletion_status", "steps_json"])
            for cid in sorted(results):
                st, steps = results[cid]
                w.writerow([cid, st, serialize(steps)])
    return results


if __name__ == "__main__":
    import sys
    D = Path(__file__).resolve().parent.parent / "dataset"
    out = run(D, D / "sample_deletion_requests.csv")
    print(len(out), "cases")
