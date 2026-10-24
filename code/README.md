# Ghost Data Still Exists: Deletion Audit Agent

A deterministic audit pipeline that decides whether a user's deletion is COMPLETE, INCOMPLETE, or NOT_APPLICABLE, and produces ordered FINDING, REMEDIATION, and VERIFICATION steps.

## Requirements

- Python 3.10 or newer (standard library only)
- `pdftotext` (poppler-utils) for PDF evidence
- `tesseract` (OCR) for screenshot evidence

On macOS: `brew install poppler tesseract`. On Debian/Ubuntu: `sudo apt-get install poppler-utils tesseract-ocr`.

## Run

From the repository root (the folder that contains `dataset/`):

```bash
python3 code/main.py                       # writes output.csv at the repo root
python3 code/evaluation/evaluate.py        # runs the evaluation workflow
```

`main.py` reads `dataset/deletion_requests.csv` and writes `output.csv` with 518 rows.
Extracted PDF and OCR text is cached in `code/.cache/` and is regenerated on demand.

## Architecture

| Module | Role |
| --- | --- |
| `identity.py` | Resolves a request email (current or historical) to a `user_id` using the identity snapshot, the audit log, and email hashes. Loads data-catalog links. |
| `evidence.py` | Scans every evidence file captured at or before `audit_at`: SQL snapshots (including JSON payload columns), JSON exports, logs, the handover table, PDFs, and screenshots. Propagates trace IDs across log lines. |
| `request_intent.py` | Decides whether a request authorizes deletion. Non-deletion phrasing (access, export, correction, opt-out) returns NOT_APPLICABLE. |
| `rules.py` | Maps resources to policy categories and emits ordered steps in the contract order. |
| `pipeline.py` | Ties the above together for each case. |
| `main.py` | Entry point that writes `output.csv`. |
| `evaluation/evaluate.py` | Scores the sample, measures step and field accuracy, and runs the custom cases. |

## Determinism and constraints

- No model calls and no network access during a run. All output is deterministic.
- Only `dataset/` is read. No organizer-only files, golden labels, or case-specific shortcuts are used.
- Evidence captured after a case's `audit_at` is never used.

## Known limitations

See `evaluation/evaluation_report.md`, section 6.
