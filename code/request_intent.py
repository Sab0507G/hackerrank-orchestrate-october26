"""Decide whether a request text authorizes deletion (multilingual, rule-based).

Non-deletion phrasing overrides deletion phrasing, so "I am not asking for deletion"
or "do not close the account" returns False.
"""
import re

NON_DELETION = [
    r"not (asking|requesting|a request) (for )?(deletion|to erase|to delete|to close)",
    r"not a request to (erase|delete|close)",
    r"\b(do not|don'?t|please don'?t|dont) (delete|erase|remove|close|cancel|change|touch)",
    r"\bwithout removing\b", r"\bkeep the account\b", r"\bleave my (profile|purchase|account)\b",
    r"\bplease keep the account\b", r"\bplease keep (it|everything|my)\b", r"\bstill (want|need|use)\b", r"\bi still use\b", r"\bi still need\b",
    r"\binformation request\b", r"\bsend me a copy\b", r"\bneed a copy of\b", r"\bcopy of (last year|the invoices|my invoices|my records|the information)\b", r"\bi (would like|want|need) to download\b", r"\bdownload my (account|personal) (information|data)\b", r"\bportable format\b",
    r"\bcorrect (it|my|the)\b", r"\bmisspelled\b", r"\breset(ting)? the (login|password)\b",
    r"\bchange the email\b", r"\bpromotional\b", r"\bmarketing lists?\b", r"\bunsubscribe\b",
    r"\bcan'?t access\b", r"\bwhat personal information\b", r"\bsend me a copy\b",
    r"\bhelp resetting\b", r"\bopt.?out\b",
    r"\bno (borres|elimines|cierres|cambies)\b", r"\bdescargar mis\b", r"\bquiero (una )?copia\b",
]

DELETION = [
    r"\bdelete\b", r"\berase\b", r"\bremove (my|the|this) (account|profile|data|personal)",
    r"\bclose (my|the|this) account\b", r"\bpermanent(ly)? (account )?deletion\b",
    r"\bclosed\b", r"\bforget me\b", r"\bright to be forgotten\b",
    r"\bsupprim", r"\bsuppression\b", r"\beliminar\b", r"\bborrar\b", r"\blöschen\b", r"\bcancel(l)?ing my account\b",
    r"\bdelete my\b", r"\bremove all\b",
]


def is_deletion_request(text: str) -> bool:
    """Authorized unless the text clearly asks for something other than deletion.

    Deletion-verb matching alone is too narrow: audit and verification requests about an
    already-requested deletion are still deletion authorizations.
    """
    t = (text or "").lower()
    return not any(re.search(p, t) for p in NON_DELETION)
