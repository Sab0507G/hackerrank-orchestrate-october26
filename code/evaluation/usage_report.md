# Token Usage and Cost Report

## Final full-dataset run that produced output.csv

The solution is a deterministic Python pipeline. It makes no model or API calls during a run.

| Item | Value |
| --- | --- |
| Model providers | None (no LLM or VLM calls) |
| Model names | None |
| Model calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens | 0 |
| Average tokens per request | 0 (518 requests) |
| Estimated cost (total) | $0.00 |
| Estimated cost per request | $0.00 |

Per-model and overall totals are not applicable because no model is used at runtime.

## Local tools used during a run

- `pdftotext` (poppler) extracts text from the PDF evidence.
- `tesseract` (OCR) extracts text from the screenshot evidence. Results are cached in `code/.cache/extracted/`.
- Neither tool calls an external service, and neither has a token cost.

## Development-session usage

Tokens used by the coding assistant while building this solution are not part of the
runtime pipeline and are not included in the figures above. They are not measured here.
