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

## Optional: LLM intent classifier (needs your API key)

The request-intent gate can use an LLM instead of the phrase list. Without a key, the phrase list is used automatically.

1. Get an API key from the Anthropic Console (console.anthropic.com, API Keys). Do not paste it into chats or commit it.
2. Open a terminal in the repository root.
3. Set the key for the current terminal session:
   - Mac or Linux: `export ANTHROPIC_API_KEY="your-key"`
   - Windows PowerShell: `$env:ANTHROPIC_API_KEY="your-key"`
4. Score the classifier on the clean test set:
   `python3 code/evaluation/score_intent.py code/evaluation/custom/third_test_cases.csv`
5. Check the last lines: `mode=llm` means the model was used, and `intent accuracy` gives the score. `mode=phrase_fallback` means no key was found or a call failed.

The classifier uses only the Python standard library and sends the request text to the Anthropic API.
