"""LLM-based deletion-intent classifier with phrase-list fallback.

Uses the Anthropic Messages API via the standard library (no SDK needed).
Reads ANTHROPIC_API_KEY from the environment only; never stores or logs it.
If the key is missing or a call fails, falls back to request_intent.is_deletion_request.
"""
import json
import os
import urllib.error
import urllib.request

from request_intent import is_deletion_request as phrase_is_deletion

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-5-5"
PROMPT = (
    "You classify a customer's privacy request. Answer with exactly one word.\n"
    "DELETE: the person asks for their account or personal data to be deleted, erased, removed, "
    "closed, or wiped, or asks to check that a deletion was completed.\n"
    "NOT_DELETE: the person asks for anything else (information, copy, export, correction, "
    "address or email change, password reset, unsubscribe, keeping the account), or explicitly "
    "says not to delete.\n\nRequest:\n"
)


def llm_is_deletion(text: str, api_key: str, timeout: float = 30.0) -> bool:
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": PROMPT + text}],
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    answer = "".join(block.get("text", "") for block in data.get("content", [])).strip().upper()
    if answer.startswith("NOT_DELETE"):
        return False
    if answer.startswith("DELETE"):
        return True
    raise ValueError(f"unexpected classifier output: {answer!r}")


def is_deletion_request(text: str) -> tuple:
    """Return (is_deletion, mode) where mode is 'llm' or 'phrase_fallback'."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return phrase_is_deletion(text), "phrase_fallback"
    try:
        return llm_is_deletion(text, key), "llm"
    except (urllib.error.URLError, ValueError, KeyError, json.JSONDecodeError):
        return phrase_is_deletion(text), "phrase_fallback"
