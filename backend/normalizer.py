"""Spoken-number and spoken-identifier normalizer (Hindi, Hinglish, English, Devanagari)."""

import re

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_WORD_DIGITS: dict[str, str] = {
    **dict.fromkeys(["zero", "oh", "shunya", "shoonya", "sifar", "शून्य", "सिफर"], "0"),
    **dict.fromkeys(["one", "ek", "एक"], "1"),
    **dict.fromkeys(["two", "do", "दो"], "2"),
    **dict.fromkeys(["three", "teen", "तीन"], "3"),
    **dict.fromkeys(["four", "char", "chaar", "चार"], "4"),
    **dict.fromkeys(["five", "paanch", "panch", "पाँच", "पांच"], "5"),
    **dict.fromkeys(["six", "chhe", "chhah", "chhay", "छह", "छः", "छे"], "6"),
    **dict.fromkeys(["seven", "saat", "सात"], "7"),
    **dict.fromkeys(["eight", "aath", "आठ"], "8"),
    **dict.fromkeys(["nine", "nau", "नौ"], "9"),
}
_MULTIPLIERS = {"double": 2, "dabal": 2, "triple": 3, "tripal": 3, "डबल": 2, "ट्रिपल": 3}
_SYMBOL_WORDS = {"dot": ".", "period": ".", "at": "@", "underscore": "_", "dash": "-", "hyphen": "-"}
# How Hindi speakers name the letters of the alphabet, used when a code is spelled out in Devanagari.
_LETTER_NAMES = {
    "ए": "A", "बी": "B", "सी": "C", "डी": "D", "ई": "E", "एफ": "F", "जी": "G", "एच": "H", "आई": "I", "जे": "J", "के": "K",
    "एल": "L", "एम": "M", "एन": "N", "ओ": "O", "पी": "P", "क्यू": "Q", "आर": "R", "एस": "S", "टी": "T", "यू": "U",
    "वी": "V", "डब्ल्यू": "W", "एक्स": "X", "वाई": "Y", "जेड": "Z", "ज़ेड": "Z",
}

_AT_THE_RATE = re.compile(r"\bat[\s-]+the[\s-]+rate(?:[\s-]+of)?\b", re.IGNORECASE)
_TOKEN = re.compile(r"[A-Za-z]+|[\u0900-\u097F]+|[0-9]+|\S")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.translate(_DEVANAGARI_DIGITS))


def _is_number(token: str) -> bool:
    return token.isascii() and token.isdigit()


def normalize_digits(text: str) -> str:
    """Return only the digits spoken or written in ``text``; spaces, dashes and dots are ignored."""
    out: list[str] = []
    repeat = 1
    for tok in _tokens(text):
        word = tok.lower()
        if _is_number(tok):
            out.append(tok * repeat if len(tok) == 1 else tok)
        elif word in _MULTIPLIERS:
            repeat = _MULTIPLIERS[word]
            continue
        elif word in _WORD_DIGITS:
            out.append(_WORD_DIGITS[word] * repeat)
        elif word == "o":
            out.append("0" * repeat)
        repeat = 1
    return "".join(out)


def normalize_identifier(text: str) -> str:
    """Turn a spoken UPI ID or IFSC into its written form; already-written values pass through."""
    text = text.strip()
    if not re.search(r"\s", text):
        return text
    text = _AT_THE_RATE.sub(" @ ", text)
    out: list[str] = []
    repeat = 1
    for tok in _tokens(text):
        word = tok.lower()
        if word in _MULTIPLIERS:
            repeat = _MULTIPLIERS[word]
            continue
        if _is_number(tok):
            out.append(tok * repeat if len(tok) == 1 else tok)
        elif word in _WORD_DIGITS:
            out.append(_WORD_DIGITS[word] * repeat)
        elif word in _SYMBOL_WORDS:
            out.append(_SYMBOL_WORDS[word])
        elif tok in _LETTER_NAMES:
            out.append(_LETTER_NAMES[tok])
        else:
            out.append(tok)
        repeat = 1
    return "".join(out)
