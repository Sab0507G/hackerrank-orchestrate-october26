"""Policy and step generation for the deletion audit (first pass).

Maps each evidence hit to a deletion_rules.csv category, decides whether the
record is still exposed at audit_at, and emits ordered FINDING, REMEDIATION,
and VERIFICATION steps in the contract order.
"""
import re

# Operation order from problem_statement.md (phase-local ordering)
OP_ORDER = {
    "FINDING": ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII",
                "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"],
    "REMEDIATION": ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD",
                    "REDACT_RECORD", "ANONYMIZE_RECORD"],
    "VERIFICATION": ["VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT",
                     "VERIFY_RECORD_REDACTED", "VERIFY_RECORD_ANONYMIZED",
                     "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"],
}
PHASE_ORDER = ["FINDING", "REMEDIATION", "VERIFICATION"]
STATE_OF = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE", "REPORT_RESTORE_RISK": "ACTIVE",
    "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED", "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED", "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}

# resource_id prefix -> (system_id, policy category)
PREFIX_CATEGORY = [
    ("account_", "account_service", "USER_PROFILE"),
    ("search_", "search_service", "SEARCH_INDEX_ENTRY"),
    ("analytics_", "analytics_platform", "ANALYTICS_PROFILE"),
    ("support_", "support_platform", "SUPPORT_MESSAGE"),
    ("attachment_", "support_platform", "SUPPORT_ATTACHMENT"),
    ("object_", "object_storage", "SUPPORT_ATTACHMENT"),
    ("export_", "export_service", "USER_EXPORT"),
    ("marketing_", "marketing_platform", "MARKETING_PROFILE"),
    ("email_", "email_delivery_service", "EMAIL_DELIVERY_LOG"),
    ("audit_record_", "security_service", "SECURITY_AUDIT_LOG"),
    ("legal_", "legal_service", "LEGAL_HOLD_RECORD"),
    ("backup_", "backup_service", "BACKUP_ARCHIVE"),
    ("data_flow_", "integration_service", "DATA_FLOW"),
    ("cache_", "cache_service", "CACHE_ENTRY"),
]

# Categories whose records are not a deletion target (preserve or read-only)
RETAIN_CATEGORIES = {"SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"}


def classify_resource(resource_id: str):
    """Return (system_id, category) for a resource id using its prefix."""
    rid = (resource_id or "").lower()
    for prefix, system, category in PREFIX_CATEGORY:
        if rid.startswith(prefix):
            return system, category
    return "unknown_service", "UNKNOWN"


def _step(phase, op, system, rid, evidence_id):
    return {
        "phase": phase,
        "system_id": system,
        "resource_id": rid,
        "operation": op,
        "state": STATE_OF[op],
        "evidence_id": evidence_id,
    }


def build_steps(findings, verifications, status):
    """
    findings: list of dicts {system_id, resource_id, operation, evidence_id}
    verifications: list of dicts for COMPLETE verification steps
    status: COMPLETE / INCOMPLETE / NOT_APPLICABLE
    Returns ordered list of step dicts with step_no assigned.
    """
    steps = []
    if status == "NOT_APPLICABLE":
        return []

    def as_finding(f):
        return {"phase": "FINDING", "system_id": f["system_id"], "resource_id": f["resource_id"],
                "operation": f["operation"], "state": STATE_OF[f["operation"]],
                "evidence_id": f["evidence_id"]}

    if status == "COMPLETE":
        steps = list(verifications)
    else:
        steps = [as_finding(f) for f in findings]
        for f in findings:
            steps.extend(_remediation_for(f))
        steps.extend(_verification_for(findings))

    def sort_key(s):
        return (
            PHASE_ORDER.index(s["phase"]),
            OP_ORDER[s["phase"]].index(s["operation"]),
            s["system_id"],
            s["resource_id"],
        )

    steps.sort(key=sort_key)
    for i, s in enumerate(steps, 1):
        s["step_no"] = i
    return steps


def _remediation_for(finding):
    """Map a finding to its ordered remediation steps (future work, no evidence cited)."""
    op = finding["operation"]
    sid, rid = finding["system_id"], finding["resource_id"]
    rem = []
    if op == "REPORT_ACTIVE_DATA_FLOW":
        rem.append(_step("REMEDIATION", "DISABLE_DATA_FLOW", sid, rid, ""))
    elif op == "REPORT_RESTORE_RISK":
        rem.append(_step("REMEDIATION", "BLOCK_RESTORE", sid, rid, ""))
    elif op == "REPORT_REMAINING_RECORD":
        rem.append(_step("REMEDIATION", "DELETE_RECORD", sid, rid, ""))
    elif op == "REPORT_EXPOSED_PII":
        rem.append(_step("REMEDIATION", finding.get("remedy", "REDACT_RECORD"), sid, rid, ""))
    return rem


def _verification_for(findings):
    """Post-remediation checks that must pass, for each finding."""
    ver = []
    for f in findings:
        op = f["operation"]
        sid, rid = f["system_id"], f["resource_id"]
        if op == "REPORT_ACTIVE_DATA_FLOW":
            ver.append(_step("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", sid, rid, ""))
        elif op == "REPORT_RESTORE_RISK":
            ver.append(_step("VERIFICATION", "VERIFY_RESTORE_BLOCKED", sid, rid, ""))
        elif op == "REPORT_REMAINING_RECORD":
            ver.append(_step("VERIFICATION", "VERIFY_RECORD_ABSENT", sid, rid, ""))
        elif op == "REPORT_EXPOSED_PII":
            vop = f.get("verify", "VERIFY_RECORD_REDACTED")
            ver.append(_step("VERIFICATION", vop, sid, rid, ""))
    return ver


def serialize(steps):
    import json
    return json.dumps(steps, ensure_ascii=False, separators=(",", ":"))
