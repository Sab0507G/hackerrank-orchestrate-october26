"""Score the request-intent classifier on a labelled CSV.

Usage (from repo root):
    python3 code/evaluation/score_intent.py code/evaluation/custom/third_test_cases.csv
Reports whether the LLM or the phrase-list fallback was used for each case.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llm_intent import is_deletion_request  # noqa: E402


def main(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    correct, modes = 0, {}
    for r in rows:
        want_deletion = r["expected_status"] != "NOT_APPLICABLE"
        got, mode = is_deletion_request(r["request_text"])
        modes[mode] = modes.get(mode, 0) + 1
        ok = got == want_deletion
        correct += ok
        print(f"{r['case_id']} expected={'DELETE' if want_deletion else 'NOT_DELETE'} "
              f"got={'DELETE' if got else 'NOT_DELETE'} mode={mode} {'PASS' if ok else 'FAIL'}")
    print(f"intent accuracy: {correct}/{len(rows)}  modes used: {modes}")


if __name__ == "__main__":
    main(sys.argv[1])
