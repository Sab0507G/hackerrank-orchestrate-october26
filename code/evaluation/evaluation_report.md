# Evaluation Report

Generated from `code/evaluation/metrics.json` by `python3 code/evaluation/evaluate.py`.

## 1. Case-level deletion-status accuracy

Scored against `dataset/sample_output.csv` (32 cases).

| Metric | Value |
| --- | --- |
| Overall status accuracy | 26 / 32 (81.2%) |
| Development set (cases 01-16, used for tuning) | 16 / 16 |
| Held-out set (cases 17-32) | 10 / 16 |

**Caveat on the held-out figure:** cases 17-32 were printed and inspected during development, so this figure is not a clean held-out estimate. A clean estimate needs cases that were never looked at, which the sample does not provide.

Confusion matrix (gold -> predicted):

| Gold | Predicted | Count |
| --- | --- | --- |
| COMPLETE | COMPLETE | 7 |
| COMPLETE | INCOMPLETE | 3 |
| INCOMPLETE | COMPLETE | 3 |
| INCOMPLETE | INCOMPLETE | 19 |

## 2. Step-level and field-level accuracy

Steps are keyed on (phase, operation, system_id, resource_id).

| Metric | Value |
| --- | --- |
| Step precision | 0.770 |
| Step recall | 0.554 |
| Step F1 | 0.645 |
| Field accuracy on matched steps (state, evidence_id) | 0.930 |

Recall is limited mainly by records whose only link to the user is not present in the evidence (see section 6).

## 3. Sequence accuracy

Exact match of the ordered step list per case: 0.031.

Step order follows the contract (phase, then operation order, then system_id, then resource_id). Sequence accuracy is low because the step sets are incomplete, not because of ordering.

## 4. Team-authored custom cases

Four cases are in `code/evaluation/custom/custom_cases.csv`. Expected values were written from the policy and the identity data, not from the pipeline's output.

Passed: 4 / 4.

| Case | Purpose | Expected | Predicted | Result |
| --- | --- | --- | --- | --- |
| custom_01 | Spanish non-deletion phrasing must not be treated as deletion | NOT_APPLICABLE (user user_523) | NOT_APPLICABLE (user user_523) | Pass |
| custom_02 | Unknown email must not crash; no identity or evidence means nothing remains | COMPLETE (user (none)) | COMPLETE (user (none)) | Pass |
| custom_03 | Historical (old) email must resolve to the same user_id; status not hand-labelled | (not hand-labelled) (user user_523) | INCOMPLETE (user user_523) | Pass |
| custom_04 | English access/export request must not be treated as deletion | NOT_APPLICABLE (user user_523) | NOT_APPLICABLE (user user_523) | Pass |

## 5. Failures found and improvements made

1. **Crash on unknown email.** An email matching no user raised an IndexError. Fixed: an authorized deletion with no matching identity returns COMPLETE with no steps. Found while writing custom_02.
2. **Spanish non-deletion phrasing.** "No borren nada" and "descargar mis datos" were treated as deletion. Fixed by adding patterns. Found while writing custom_01. Only English and a few phrases in other languages are covered.
3. **Wrong NOT_APPLICABLE for real deletions.** NOT_APPLICABLE was assigned when no evidence matched, wrongly excluding two authorized deletions (case_525, case_61). Fixed: NOT_APPLICABLE now depends only on request text.
4. **Over-broad non-deletion patterns.** Three sample deletions were blocked by generic phrases ("copy of", "download", "please keep"). Narrowed. This was partly informed by the sample.
5. **Handover statuses ignored.** The shift-handover table's per-resource states were not used. Fixed: parsed as authoritative state.
6. **Direct-identifier exposure.** SQL and JSON rows with only a user_id (tombstones, anonymized records) were treated as exposed. Fixed: exposure requires an email, phone, hash, or name.
7. **PDF and image evidence not read.** Fixed with pdftotext and tesseract, plus document-level resource extraction.
8. **User-id substring matching.** `user_1` matched inside `user_10`. Fixed with whole-word matching.
9. **Data flows classified as secondary identifiers.** `data_flow_` resources were not treated as data flows. Fixed: classified as DATA_FLOW, and a live connector flag (enabled=true or scheduler_registered=true) in a linked log line marks the flow active.
10. **Log lookups that returned rows ignored.** A lookup with rows >= 1, or a deletion marker not found, shows the record still exists. Fixed: treated as presence evidence.

## 6. Known remaining failures

- **Development set:** all 16 cases are correct, but this was reached by tuning against them, so it is an in-sample figure.
- **Held-out cases still wrong (6 of 16):** cases 17, 19, 32 are missed findings (predicted COMPLETE, expected INCOMPLETE). Cases 26, 27, 28 are false findings (predicted INCOMPLETE, expected COMPLETE). These are not being fixed by tuning, since that would use the held-out cases.
- **Deleted-account linkage:** the answer key expects absence checks on some deleted accounts. No principled link from a user to those accounts is derivable from the activity stream, so the pipeline does not guess one.
- **Gold relies on later evidence in one case.** For case_09 the answer key cites a log captured after audit_at. The spec forbids using it, so the pipeline excludes it.
- **Non-English non-deletion requests.** Only a few phrases are covered.
- **Weak step recall.** Recall is about 0.55, so even correct statuses often come with an incomplete step list.
