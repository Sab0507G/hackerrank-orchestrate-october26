"""Evaluation workflow for the deletion audit.

Run from the repo root:   python3 code/evaluation/evaluate.py

Reports:
  * case-level deletion-status accuracy on dataset/sample_deletion_requests.csv
  * step-level precision, recall, and F1 (key = phase, operation, system_id, resource_id)
  * field-level accuracy on matched steps (state and evidence_id)
  * sequence accuracy (exact ordered step list per case)
  * team-authored custom cases (status, user resolution, no crash)

Writes evaluation/metrics.json next to this file.
"""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent
ROOT = CODE.parent
sys.path.insert(0, str(CODE))

from identity import IdentityIndex  # noqa: E402
from pipeline import run, decide  # noqa: E402
from evidence import Evidence  # noqa: E402
from identity import load_catalog_links  # noqa: E402

DATASET = ROOT / "dataset"


def step_key(s):
    return (s["phase"], s["operation"], s["system_id"], s["resource_id"])


def score_sample():
    gold = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"]))
            for r in csv.DictReader(open(DATASET / "sample_output.csv", encoding="utf-8"))}
    pred = run(DATASET, DATASET / "sample_deletion_requests.csv")

    status_ok = 0
    seq_ok = 0
    tp = fp = fn = 0
    field_total = field_ok = 0
    confusion = {}
    per_case = {}
    for cid, (gs, gsteps) in sorted(gold.items()):
        ps, psteps = pred[cid]
        status_ok += ps == gs
        confusion[f"{gs}->{ps}"] = confusion.get(f"{gs}->{ps}", 0) + 1

        g_keys = [step_key(s) for s in gsteps]
        p_keys = [step_key(s) for s in psteps]
        seq_ok += g_keys == p_keys

        g_map = {step_key(s): s for s in gsteps}
        p_map = {step_key(s): s for s in psteps}
        matched = set(g_map) & set(p_map)
        tp += len(matched)
        fp += len(set(p_map) - set(g_map))
        fn += len(set(g_map) - set(p_map))
        for k in matched:
            for field in ("state", "evidence_id"):
                field_total += 1
                field_ok += g_map[k].get(field) == p_map[k].get(field)
        per_case[cid] = {"gold": gs, "pred": ps, "steps_gold": len(gsteps), "steps_pred": len(psteps)}

    n = len(gold)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "cases": n,
        "status_accuracy": round(status_ok / n, 4),
        "status_correct": status_ok,
        "step_precision": round(precision, 4),
        "step_recall": round(recall, 4),
        "step_f1": round(f1, 4),
        "field_accuracy_on_matched_steps": round(field_ok / field_total, 4) if field_total else 0.0,
        "sequence_accuracy": round(seq_ok / n, 4),
        "status_confusion_gold_to_pred": confusion,
        "per_case": per_case,
    }


def score_custom():
    path = HERE / "custom" / "custom_cases.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    idx = IdentityIndex(DATASET)
    ev = Evidence(DATASET)
    links = load_catalog_links(DATASET)
    results = []
    for r in rows:
        resolved = sorted(idx.resolve(r["email"]))
        resolved_user = resolved[0] if resolved else ""
        try:
            status, steps = decide(r, idx, ev, links)
            crashed = False
        except Exception as exc:  # report, do not hide
            status, steps, crashed = f"ERROR:{type(exc).__name__}", [], True
        user_ok = resolved_user == r["expected_user"]
        status_ok = (r["expected_status"] == "") or (status == r["expected_status"])
        results.append({
            "case_id": r["case_id"],
            "purpose": r["purpose"],
            "expected_status": r["expected_status"] or "(not hand-labelled)",
            "pred_status": status,
            "status_ok": status_ok,
            "expected_user": r["expected_user"] or "(none)",
            "resolved_user": resolved_user or "(none)",
            "user_ok": user_ok,
            "crashed": crashed,
        })
    passed = sum(1 for x in results if x["status_ok"] and x["user_ok"] and not x["crashed"])
    return {"cases": len(results), "passed": passed, "results": results}


def main():
    sample = score_sample()
    custom = score_custom()
    metrics = {"sample": sample, "custom": custom}
    out = HERE / "metrics.json"
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"sample status accuracy: {sample['status_correct']}/{sample['cases']} ({sample['status_accuracy']:.1%})")
    print(f"step precision/recall/F1: {sample['step_precision']:.3f} / {sample['step_recall']:.3f} / {sample['step_f1']:.3f}")
    print(f"field accuracy (matched steps): {sample['field_accuracy_on_matched_steps']:.3f}")
    print(f"sequence accuracy: {sample['sequence_accuracy']:.3f}")
    print(f"custom cases passed: {custom['passed']}/{custom['cases']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
