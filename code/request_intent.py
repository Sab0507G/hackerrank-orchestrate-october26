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

# Multilingual and generic non-deletion phrasing (information, copy, export, update, opt-out, keep active)
NON_DELETION += [
    r"\bwelche (persönlichen )?daten\b", r"\bnur wissen\b", r"\bkopie (meiner|der) (daten|bestellungen)\b",
    r"\bne supprimez rien\b", r"\bje souhaite recevoir une copie\b", r"\bcopie de mes données\b",
    r"\bne supprimez pas\b", r"\bmantenha a conta\b", r"\bquero atualizar\b", r"\bnão (apague|exclua)\b",
    r"削除しないで", r"コピー", r"注文履歴",
    r"\bexport (my|the|our)\b", r"\bnot (closing|deleting|cancelling) (my|the) account\b",
    r"\bkeep my account (active|open)\b", r"\bkeep the account active\b", r"\bunsubscribe\b",
]

# Language coverage for non-deletion intent (Italian, Dutch, Turkish, Korean, romanized Hindi)
NON_DELETION += [
    # Italian
    r"\bnon (cancellate|eliminate|cancellare|eliminare|chiudete|chiudere)\b", r"\bvoglio sapere\b",
    r"\bcopia dei miei dati\b", r"\besportare\b", r"\baggiornare\b", r"\btenete (il|l')account\b",
    # Dutch
    r"\bverwijder (mijn account )?niet\b", r"\bniet verwijderen\b", r"\bwil weten\b", r"\bkopie van mijn gegevens\b",
    r"\bexporteren\b", r"\bbijwerken\b", r"\blaat (het|mijn) account\b",
    # Turkish
    r"\bsilmeyin\b", r"\bsilmeyiniz\b", r"\bkapatmayın\b", r"\bbilgi (almak|istiyorum)\b", r"\bkopyasını\b",
    r"\bgüncellemek istiyorum\b", r"\bdışa aktar\b",
    # Korean
    r"삭제하지", r"그대로 두", r"사본", r"정보 (확인|보기)", r"비밀번호 재설정", r"업데이트", r"계정은 유지",
    # Romanized Hindi
    r"\bdelete mat\b", r"\bdelete nahi\b", r"\bband mat\b", r"\bcopy bhejo\b", r"\bdata dekhna\b",
    r"\breset karna\b", r"\bupdate karna\b", r"\bkeep karna\b", r"\bmat karna\b", r"\bjankari chahiye\b",
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
