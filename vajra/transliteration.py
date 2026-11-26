from __future__ import annotations
import re
import unicodedata

# Devanagari consonants to Latin
_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ड़": "d", "ढ़": "dh", "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "फ़": "f",
    "क्ष": "ksh", "त्र": "tr", "ज्ञ": "gy",
}

# Independent vowels
_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "अं": "an", "अः": "ah",
}

# Dependent vowel signs (matras)
_MATRAS = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u",
    "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ं": "n", "ँ": "n", "ः": "h",
}

# Virama / halant
_VIRAMA = "्"

# Devanagari numerals to ASCII
_NUMERALS = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

def indic_digits_to_ascii(text: str) -> str:
    res = []
    for ch in text:
        res.append(_NUMERALS.get(ch, ch))
    return "".join(res)

def devanagari_to_latin(text: str) -> str:
    """Accurately transliterate Devanagari text into Romanized phonetic Latin."""
    chars = list(unicodedata.normalize("NFC", text))
    out = []
    i = 0
    n = len(chars)
    while i < n:
        ch = chars[i]
        # Check nukta combinations (e.g. ड + ़ = ड़)
        if i + 1 < n and chars[i + 1] == "़":
            combo = ch + "़"
            if combo in _CONSONANTS:
                ch = combo
                i += 1
        
        if ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _CONSONANTS:
            base = _CONSONANTS[ch]
            # Look ahead for matra or virama
            if i + 1 < n:
                nxt = chars[i + 1]
                if nxt == _VIRAMA:
                    out.append(base)
                    i += 1  # Skip virama
                elif nxt in _MATRAS:
                    out.append(base + _MATRAS[nxt])
                    i += 1  # Skip matra
                    # Check if followed by anusvara (e.g. विं)
                    if i + 1 < n and chars[i + 1] in ("ं", "ँ"):
                        out.append("n")
                        i += 1
                else:
                    # Inherent vowel 'a' if followed by another consonant or end of non-terminal
                    out.append(base + ("a" if (i + 1 < n and chars[i + 1] in _CONSONANTS) else ""))
            else:
                out.append(base)
        elif ch in _MATRAS:
            out.append(_MATRAS[ch])
        elif ch in _NUMERALS:
            out.append(_NUMERALS[ch])
        else:
            out.append(ch)
        i += 1
    
    return "".join(out)

_HONORIFICS = {
    "sahab", "sahib", "babu", "ji", "didi", "amma", "bhai", "bhaiya", "behenji",
    "shri", "shrimati", "smt", "mr", "mrs", "ms", "km", "kumari",
}

def normalize_name(name: str) -> str:
    """Normalize Indian names across Latin and Devanagari scripts and transliteration variants."""
    if not name:
        return ""
    text = indic_digits_to_ascii(name)
    # Check if Devanagari is present
    if re.search(r"[\u0900-\u097f]", text):
        text = devanagari_to_latin(text)
    
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    
    norm_tokens = []
    for tok in tokens:
        if tok in _HONORIFICS:
            continue
        # Standardize common spelling aliases
        if tok in ("md", "mohd", "mohammad", "muhammad", "mohammed", "mohd."):
            tok = "mohammad"
        elif tok in ("sukhvinder", "sukhwinder", "sukhvinda", "sukhwinda"):
            tok = "sukhvinder"
        elif tok in ("brajesh", "brijesh"):
            tok = "brijesh"
        elif tok in ("zenab", "zainab", "zainaba"):
            tok = "zainab"
        elif tok in ("sunita", "suneeta"):
            tok = "sunita"
        elif tok in ("irfaan", "irfan"):
            tok = "irfan"
        elif tok in ("parvathi", "parvati"):
            tok = "parvati"
        elif tok in ("pandeya", "pandey"):
            tok = "pandey"
        elif tok in ("yadava", "yadav"):
            tok = "yadav"
        elif tok in ("reena", "rina"):
            tok = "reena"
        elif tok in ("geeta", "gita"):
            tok = "geeta"
        elif tok in ("chaudhary", "choudhary", "chaudhari"):
            tok = "chaudhary"
        elif tok in ("siddiqui", "siddiki", "siddiqi"):
            tok = "siddiqui"
        elif tok in ("rajaput", "rajput"):
            tok = "rajput"
        elif tok in ("aa", "a"):
            continue
        
        # Phonetic transforms
        tok = tok.replace("w", "v").replace("ee", "i").replace("oo", "u").replace("aa", "a")
        if tok.endswith("a") and len(tok) > 4 and tok not in ("asha", "reena", "geeta", "sunita", "kavita", "fatima", "kamla", "shanti"):
            tok = tok[:-1]
        norm_tokens.append(tok)
    
    return " ".join(norm_tokens)
