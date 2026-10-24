"""End-to-end deletion audit: resolve identity, scan evidence, apply rules, emit steps."""
import csv
import json
from collections import defaultdict
from pathlib import Path

from identity import IdentityIndex, load_catalog_links
from evidence import Evidence
from rules import classify_resource, build_steps, serialize, RETAIN_CATEGORIES

DELETE_CATEGORIES = {"USER_PROFILE", "SEARCH_INDEX_ENTRY", "USER_EXPORT", "MARKETING_PROFILE",
                     "SUPPORT_ATTACHMENT", "SUPPORT_MESSAGE", "CACHE_ENTRY", "EMAIL_DELIVERY_LOG"}
ANONYMIZE_CATEGORIES = {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"}


def _case_resources(uid, audit_at, idents, ev, links):
    """Resources attributable to the user at audit_at, with the evidence that proves each."""
    res = defaultdict(lambda: {"file_ids": set(), "exposed": False})
    for h in ev.find_all(audit_at, idents):
        rid = h.get("resource_id")
        if not rid:
            continue
        res[rid]["file_ids"].add(h["file_id"])
        if h.get("source") in ("sql", "json"):
            res[rid]["exposed"] = True
    for rid, ls in links.items():
        if any(u == uid and t <= audit_at for t, u in ls):
            res[rid]  # ensure present
    return res


def decide(request, idx, ev, links, classify_nonde=frozenset()):
    uid = sorted(idx.resolve(request["email"]))[0]
    I = idx.identifiers(uid, request["audit_at"])
    idents = {
        "emails": set(I["emails"]),
        "phones": set(I["phones"]),
        "email_hashes": set(I["email_hashes"]),
        "user_ids": {uid.lower()},
    }
    res = _case_resources(uid, request["audit_at"], idents, ev, links)

    findings, verifications = [], []
    for rid, info in sorted(res.items()):
        system, category = classify_resource(rid)
        evid = sorted(info["file_ids"])[0] if info["file_ids"] else ""
        if category in RETAIN_CATEGORIES:
            verifications.append({"phase": "VERIFICATION", "system_id": system, "resource_id": rid,
                                  "operation": "VERIFY_RECORD_PRESENT", "state": "PRESENT",
                                  "evidence_id": evid})
        elif category in ANONYMIZE_CATEGORIES:
            if info["exposed"]:
                findings.append({"system_id": system, "resource_id": rid,
                                 "operation": "REPORT_EXPOSED_PII", "evidence_id": evid,
                                 "remedy": "ANONYMIZE_RECORD", "verify": "VERIFY_RECORD_ANONYMIZED"})
            else:
                verifications.append({"phase": "VERIFICATION", "system_id": system, "resource_id": rid,
                                      "operation": "VERIFY_RECORD_ANONYMIZED", "state": "ANONYMIZED",
                                      "evidence_id": evid})
        elif category in DELETE_CATEGORIES:
            if info["exposed"]:
                findings.append({"system_id": system, "resource_id": rid,
                                 "operation": "REPORT_REMAINING_RECORD", "evidence_id": evid})
            else:
                verifications.append({"phase": "VERIFICATION", "system_id": system, "resource_id": rid,
                                      "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT",
                                      "evidence_id": evid})

    status = "INCOMPLETE" if findings else "COMPLETE"
    if not res:
        status = "NOT_APPLICABLE"
    # Findings carry evidence for COMPLETE/INCOMPLETE; verification carries evidence too.
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
