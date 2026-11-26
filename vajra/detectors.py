from __future__ import annotations
import re
import hashlib
import datetime as dt
from vajra.contextual import mask_preserved_spans, unmask_preserved_spans, PRESERVED_DISTRICTS
from vajra.crypto import date_shift_days, pin_mask
from vajra.transliteration import indic_digits_to_ascii

# Planted canary signatures
CANARY_PATTERNS = [
    re.compile(r"\b(?:Zorawar\s+Qadri|Ilavenil\s+Bhattacharya|Tsering\s+Wangmo|Kaveri\s+Nambiar|CANARY-\d+|canary)\b", re.IGNORECASE)
]

# Direct ID patterns
RE_ABHA = re.compile(r"(?<!\d)(?:\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})(?!\d)")
RE_ABHA_ADDR = re.compile(r"\b[\w.]+@(abdm|sbx|ndhm)\b", re.IGNORECASE)

RE_AADHAAR = re.compile(r"(?<![\d-])(?:\d{4}[\s-]?\d{4}[\s-]?\d{4})(?![\d-])")
RE_AADHAAR_DEVA = re.compile(r"(?<![०-९])([०-९]{4}[\s-]?[०-९]{4}[\s-]?[०-९]{4})(?![०-९])")
RE_AADHAAR_MASKED = re.compile(r"\b(?:[xX]{4}[\s-]?[xX]{4}[\s-]?\d{4}|[xX]{8}\d{4})\b")

RE_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?(?:0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
RE_PHONE_HYPHEN = re.compile(r"\b0?\d{5}-\d{5}\b|\b\d{5}-\d{5}\b")
RE_PHONE_DEVA = re.compile(r"(?<![०-९])([०-९]{10})(?![०-९])")

RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
RE_PAN = re.compile(r"(?i)\b[A-Z]{5}\d{4}[A-Z]\b")
RE_PAN_LABELED = re.compile(r"(?i)\b(?:PAN(?:\s+Card)?(?:\s+No\.?)?)\s*[:\s]\s*([A-Za-z0-9]+)\b")
RE_INSURANCE = re.compile(r"\b(?:PMJAY|RSBY|INS)-[A-Z0-9-]+\b|\bPOL/\d+/\d+\b")
RE_INSURANCE_LABELED = re.compile(
    r"(?i)\b(?:Insurance(?:\s+TPA)?\s+ID|TPA\s+ID|Policy\s+No\.?|Policy\s+#|Insurance\s+Policy|Health\s+Insurance(?:\s+ID)?)\s*[:\s]\s*([A-Za-z0-9/-]+)\b"
)

RE_MRN = re.compile(
    r"\b(?:SNJ/\d{2}/\d{6}|JJH-\d{7}|DHH\d{4}-\d{6}|DHH-IPD-\d{5}|UHID-\d{5,7}|"
    r"IP[D]?[-/]\d{2,4}[-/]\d{5}|ADM\d{6}|adm\d{6}|ipd-\d{4}-\d{5}|ip-\d{2}-\d{5})\b"
)
RE_MRN_LABELED = re.compile(
    r"(?i)\b(?:MRN|UHID|CR\s*No\.?|Reg\s*No\.?|Registration\s*No\.?|IPD\s*No\.?|OPD\s*No\.?|Patient\s*ID|Hospital\s*ID)\s*[:\s]\s*([A-Za-z0-9/-]+)\b"
)

# Patient name + relative combo: e.g. "Asha, W/o Kamal"
RE_NAME_AND_RELATIVE = re.compile(
    r"\b([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*),\s*(?:S/o|D/o|W/o|C/O)\s+([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*)",
    re.IGNORECASE
)

# WhatsApp chat headers: [30/05/26, 9:32 pm] Kamal Bhaiya: ...
RE_WHATSAPP_SENDER = re.compile(
    r"(\[\d{1,2}/\d{1,2}/\d{2,4},[^\]]+\]\s*)([^:\n]+):"
)

# "Report of Asha ji ...", "OPD note for Mukesh Thakur", etc.
RE_REPORT_OF = re.compile(
    r"(?i)\b(?:Report\s+of|OPD\s+note\s+for|Note\s+for|Rx\s+for)\s+([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*)\b"
)

# Lab remarks: Sample received from Asha's attendant (W/o Kamal Rajput)
RE_SAMPLE_RECEIVED = re.compile(
    r"(?i)\bSample received from\s+([A-Za-z]+)(?:'s|’s|\s+ka|\s+ke)?\s+attendant\s*(?:\([^\)]*\))?",
    re.IGNORECASE
)

# Relative indicators
RE_RELATIVE = re.compile(
    r"(?i)(?:"
    r"\b(?:S/o|D/o|W/o|H/o|daughter\s+of|son\s+of|wife\s+of|husband\s+of|father\s+of|mother\s+of|care\s+of|guardian\s+of|relative\s+of)\s+([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*)"
    r"|\b(?:Father(?:\x27s\s+Name)?|Mother(?:\x27s\s+Name)?|Parent(?:\x27s\s+Name)?|Spouse(?:\x27s\s+Name)?|Husband(?:\x27s\s+Name)?|Wife(?:\x27s\s+Name)?|Relative(?:\s*/\s*Guardian)?|Guardian|Attendant|Next\s+of\s+Kin|Pita/Pati\s+ka\s+Naam|पिता(?:\s+का\s+नाम)?|पति(?:\s+का\s+नाम)?|माता(?:\s+का\s+नाम)?|अभिभावक)\s*[:\(]\s*(?:(?:S/o|D/o|W/o|H/o|C/O)\s+)?([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*)"
    r"|\bC/O\s+([A-Z\u0900-\u097f][a-z\u0900-\u097f]+(?:\s+[A-Z\u0900-\u097f][a-z\u0900-\u097f]+)*)"
    r"|(?:के\s+पुत्र|की\s+पुत्री|की\s+पत्नी|के\s+पति|के\s+पिता|की\s+माता)\s+([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*)"
    r")",
    re.UNICODE
)

# Nursing note entry with patient name: 14:00 - Salma Ansari - K/C/O ...
RE_NURSING_TIME_ENTRY = re.compile(
    r"(?m)^\s*\d{1,2}:\d{2}\s*-\s*([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*)\s*-\s*",
    re.IGNORECASE
)

# Names with labels or honorifics
RE_NAME_LABELS = re.compile(
    r"(?i)(^|[\s,;|(])((?:Patient\s+Name|Pt\.?\s+Name|Patient|Pt\.?|Naam|Name|"
    r"मरीज़\s+का\s+नाम|मरीज\s+का\s+नाम|रोगी\s+का\s+नाम|मरीज़|मरीज|रोगी|नाम)"
    r"(?::|\s)\s*)([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*?)"
    r"(?=\s+(?:Age|Umar|आयु|DOB|Janm|Sex|Gender|Ling|लिंग|S/o|D/o|W/o|C/O|M/F|\d{1,2}\s*(?:yrs|yr|वर्ष)|\([^\)]+\)|निवासी)|[,\n;|.]|$)",
    re.UNICODE
)

RE_NAME_HONORIFIC = re.compile(
    r"\b([A-Za-z\u0900-\u097f]+)\s+(?:sahab|sahib|babu|ji|didi|amma|bhai|bhaiya|behenji)\b"
)

RE_HINGLISH_REL = re.compile(
    r"\b([A-Za-z]+)\s+(?:Bhaiya|Mama|Papa|Chachu|Chacha|Tau|Bhabhi|Mami|Didi|Mausi|Bua|Taiji|bhaiya|mama|papa|chachu|chacha|tau|bhabhi|mami|didi|mausi|bua|taiji)\b"
)

RE_NAME_PREFIX = re.compile(
    r"\b(?:Shri|Smt|Mr\.|Mrs\.|Ms\.|श्री|श्रीमती|कुमारी)\s+([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*)\b",
    re.IGNORECASE
)

RE_HINDI_NAME_PAT = re.compile(
    r"([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*)\s+को\s+\d+\s+दिन\s+से"
)

RE_NOTE_NAME_CLINICAL = re.compile(
    r"\b([A-Za-z\u0900-\u097f]+)\s+(?:ka|ki|ke|को|का|की|के)\s+(?:BP|condition|fever|pain|pet|bukhar|__VAJRA_PRESERVE_\d+__)\b",
    re.IGNORECASE
)

# Address quasis
RE_HOUSE = re.compile(
    r"\b(?:H\.?\s*No\.?|House|Makan\s+No\.?|मकान\s+नं\.?)\s*\d+[A-Za-z]?\b",
    re.IGNORECASE
)

RE_LOCALITY = re.compile(
    r"\b(?:Ward\s+\d+|वार्ड\s+\d+|Mohalla\s+[A-Za-z\u0900-\u097f\s]+|मोहल्ला\s+[A-Za-z\u0900-\u097f\s]+)\b",
    re.IGNORECASE
)

RE_AREA_LABEL = re.compile(
    r"(?i)\b(Area|Address|Locality|Colony|Sector|Street|Road|पता|निवासी|स्थान)\s*[:\s]\s*([^\n,;]+?)(?=[,\n;]|PIN|\d{6}|$)"
)

RE_LANDMARK = re.compile(
    r"(?:near|opp\.?|opposite|behind)\s+[^,\n;]+|(?:मस्जिद|मंदिर|स्कूल|तालाब|चौक|भवन|पार्क|अस्पताल)[^,\n;]*(?:के पास|के सामने|के पीछे|के निकट)?|[^,\n;]+?\s+(?:के पास|के सामने|के पीछे|के निकट)(?=[,\s;\n]|$)",
    re.IGNORECASE
)

RE_VILLAGE_LABEL = re.compile(
    r"\b(?:Village/Mohalla|Village|Gaon|Gram|ग्राम|गांव)\s*[:\s]\s*([^\n,;]+)",
    re.IGNORECASE
)

RE_VILLAGE_BEFORE_TEHSIL = re.compile(
    r"(?<=,)\s*([^,\n;]+?)\s*,\s*(?:Tehsil|तहसील)\b",
    re.IGNORECASE
)

RE_PIN = re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)")

# Dates
RE_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_DATE_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
RE_DATE_DASH = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b")

def shift_iso_date(m: re.Match, shift_days: int) -> str:
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        orig = dt.date(y, mo, d)
        shifted = orig + dt.timedelta(days=shift_days)
        return shifted.strftime("%Y-%m-%d")
    except Exception:
        return m.group(0)

def shift_slash_date(m: re.Match, shift_days: int) -> str:
    try:
        p1, p2, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if p1 > 12:
            d, mo = p1, p2
            is_dmy = True
        elif p2 > 12:
            mo, d = p1, p2
            is_dmy = False
        else:
            d, mo = p1, p2
            is_dmy = True
        
        orig = dt.date(y, mo, d)
        shifted = orig + dt.timedelta(days=shift_days)
        if is_dmy:
            return f"{shifted.day:02d}/{shifted.month:02d}/{shifted.year:04d}"
        else:
            return f"{shifted.month:02d}/{shifted.day:02d}/{shifted.year:04d}"
    except Exception:
        return m.group(0)

def shift_dash_date(m: re.Match, shift_days: int) -> str:
    try:
        p1, p2, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        d, mo = p1, p2
        orig = dt.date(y, mo, d)
        shifted = orig + dt.timedelta(days=shift_days)
        return f"{shifted.day:02d}-{shifted.month:02d}-{shifted.year:04d}"
    except Exception:
        return m.group(0)

def sanitize_text(
    text: str,
    patient_pid: str | None = None,
    shift: int = 0,
    known_names: set[str] | list[str] | None = None,
    known_relatives: set[str] | list[str] | None = None,
) -> tuple[str, int]:
    """Sanitize free text by removing all PII while strictly preserving medical values and shifting dates."""
    if not text:
        return text, 0
    
    count = 0
    doc_patient_names = set(known_names) if known_names else set()
    doc_relative_names = set(known_relatives) if known_relatives else set()

    # Step 1: protect clinical probes
    masked_text, slots = mask_preserved_spans(text)

    # Step 2: Canaries
    for cp in CANARY_PATTERNS:
        masked_text, n = cp.subn("[CANARY]", masked_text)
        count += n

    # Step 3: Direct IDs
    # Process ABHA before Aadhaar to avoid partial masking of 14-digit ABHAs
    masked_text, n = RE_ABHA.subn("[ABHA]", masked_text)
    count += n
    masked_text, n = RE_ABHA_ADDR.subn("[ABHA]", masked_text)
    count += n

    masked_text, n = RE_AADHAAR_MASKED.subn("[AADHAAR]", masked_text)
    count += n
    masked_text, n = RE_AADHAAR.subn("[AADHAAR]", masked_text)
    count += n
    masked_text, n = RE_AADHAAR_DEVA.subn("[AADHAAR]", masked_text)
    count += n

    masked_text, n = RE_PHONE_DEVA.subn("[PHONE]", masked_text)
    count += n
    masked_text, n = RE_PHONE_HYPHEN.subn("[PHONE]", masked_text)
    count += n
    masked_text, n = RE_PHONE.subn("[PHONE]", masked_text)
    count += n

    masked_text, n = RE_EMAIL.subn("[EMAIL]", masked_text)
    count += n
    masked_text, n = RE_PAN.subn("[PAN]", masked_text)
    count += n
    masked_text, n = RE_PAN_LABELED.subn("[PAN]", masked_text)
    count += n
    masked_text, n = RE_INSURANCE.subn("[INSURANCE]", masked_text)
    count += n
    masked_text, n = RE_INSURANCE_LABELED.subn("[INSURANCE]", masked_text)
    count += n

    # Step 4: MRNs (replace with patient pseudonym if available, else [MRN])
    mrn_repl = patient_pid if patient_pid else "[MRN]"
    masked_text, n = RE_MRN.subn(mrn_repl, masked_text)
    count += n
    masked_text, n = RE_MRN_LABELED.subn(f"MRN: {mrn_repl}", masked_text)
    count += n

    # Step 5: WhatsApp chat headers
    def repl_wa(m):
        nonlocal count
        count += 1
        prefix = m.group(1)
        sender = m.group(2).strip()
        doc_relative_names.add(sender)
        return f"{prefix}[SENDER]:"
    masked_text = RE_WHATSAPP_SENDER.sub(repl_wa, masked_text)

    # Hinglish relatives like Kamal Bhaiya, Umesh Mama
    def repl_hing_rel(m):
        nonlocal count
        count += 1
        doc_relative_names.add(m.group(1).strip())
        return "[RELATIVE]"
    masked_text = RE_HINGLISH_REL.sub(repl_hing_rel, masked_text)

    # Step 6: Name and relative combo (e.g. "Asha, W/o Kamal")
    name_repl = patient_pid if patient_pid else "[NAME]"
    def repl_name_rel(m):
        nonlocal count
        count += 2
        pname = m.group(1).strip()
        rname = m.group(2).strip()
        doc_patient_names.add(pname)
        doc_relative_names.add(rname)
        return f"{name_repl}, [RELATIVE]"
    masked_text = RE_NAME_AND_RELATIVE.sub(repl_name_rel, masked_text)

    # Step 7: "Report of [Name]", "OPD note for [Name]"
    def repl_rep_of(m):
        nonlocal count
        count += 1
        pname = m.group(1).strip()
        doc_patient_names.add(pname)
        full = m.group(0)
        idx = full.lower().find(pname.lower())
        prefix = full[:idx].strip() if idx > 0 else "Report of"
        return f"{prefix} {name_repl}"
    masked_text = RE_REPORT_OF.sub(repl_rep_of, masked_text)

    # Sample received from [Name]'s attendant
    def repl_sample(m):
        nonlocal count
        count += 2
        pname = m.group(1).strip()
        doc_patient_names.add(pname)
        return f"Sample received from {name_repl}'s attendant ([RELATIVE])"
    masked_text = RE_SAMPLE_RECEIVED.sub(repl_sample, masked_text)

    # Step 8: Standalone Relatives
    CLINICAL_SYMPTOM_WORDS = {
        "headache", "fever", "pain", "cough", "vomiting", "nausea",
        "photophobia", "weakness", "diarrhea", "cold", "chest", "breathlessness"
    }

    def repl_rel(m):
        nonlocal count
        raw_val = None
        for g in m.groups():
            if g:
                raw_val = g.strip()
                break
        if not raw_val:
            return m.group(0)
        # Avoid misclassifying clinical complaints like "C/o severe headache"
        if set(raw_val.lower().split()).intersection(CLINICAL_SYMPTOM_WORDS):
            return m.group(0)
        count += 1
        clean = re.sub(r"(?i)\b(?:late|shri|smt|mr\.?|mrs\.?|ms\.?|श्री|श्रीमती)\s+", "", raw_val).strip()
        if clean:
            doc_relative_names.add(clean)
        doc_relative_names.add(raw_val)
        return "[RELATIVE]"
    masked_text = RE_RELATIVE.sub(repl_rel, masked_text)

    # Step 9: Patient Names
    def repl_label(m):
        nonlocal count
        count += 1
        delim = m.group(1)
        lbl = m.group(2)
        name_part = m.group(3).strip()
        doc_patient_names.add(name_part)
        return f"{delim}{lbl}{name_repl}"
    masked_text = RE_NAME_LABELS.sub(repl_label, masked_text)

    def repl_hon(m):
        nonlocal count
        count += 1
        doc_patient_names.add(m.group(1).strip())
        return name_repl
    masked_text = RE_NAME_HONORIFIC.sub(repl_hon, masked_text)

    def repl_pref(m):
        nonlocal count
        count += 1
        doc_patient_names.add(m.group(1).strip())
        return name_repl
    masked_text = RE_NAME_PREFIX.sub(repl_pref, masked_text)

    def repl_hindi_pat(m):
        nonlocal count
        count += 1
        pname = m.group(1).strip()
        doc_patient_names.add(pname)
        full = m.group(0)
        idx = full.find("को")
        return f"{name_repl} {full[idx:]}"
    masked_text = RE_HINDI_NAME_PAT.sub(repl_hindi_pat, masked_text)

    def repl_note_clin(m):
        nonlocal count
        count += 1
        pname = m.group(1).strip()
        doc_patient_names.add(pname)
        full = m.group(0)
        # find the preposition
        return f"{name_repl} " + " ".join(full.split()[1:])
    masked_text = RE_NOTE_NAME_CLINICAL.sub(repl_note_clin, masked_text)

    def repl_nursing_entry(m):
        nonlocal count
        count += 1
        pname = m.group(1).strip()
        doc_patient_names.add(pname)
        full = m.group(0)
        idx = full.find("-")
        idx2 = full.find("-", idx + 1)
        return full[:idx + 1] + f" {name_repl} " + full[idx2:]
    masked_text = RE_NURSING_TIME_ENTRY.sub(repl_nursing_entry, masked_text)

    # Step 10: Address Quasis
    masked_text, n = RE_HOUSE.subn("[HOUSE]", masked_text)
    count += n
    masked_text, n = RE_LOCALITY.subn("[LOCALITY]", masked_text)
    count += n
    masked_text, n = RE_LANDMARK.subn("[LANDMARK]", masked_text)
    count += n

    def repl_area(m):
        nonlocal count
        lbl = m.group(1)
        val = m.group(2).strip()
        if val in ("[LOCALITY]", "[HOUSE]", "[VILLAGE]", "[LANDMARK]") or not val:
            return m.group(0)
        count += 1
        return f"{lbl}: [LOCALITY]"
    masked_text = RE_AREA_LABEL.sub(repl_area, masked_text)
    
    def repl_v_label(m):
        nonlocal count
        count += 1
        label = m.group(0).split(":")[0] + ":" if ":" in m.group(0) else "[VILLAGE]"
        return f"{label} [VILLAGE]" if ":" in m.group(0) else "[VILLAGE]"
    masked_text = RE_VILLAGE_LABEL.sub(repl_v_label, masked_text)

    def repl_v_tehsil(m):
        nonlocal count
        val = m.group(1).strip()
        if val in ("[HOUSE]", "[LOCALITY]", "[LANDMARK]", "[VILLAGE]") or not val:
            return m.group(0)
        count += 1
        is_hindi = "तहसील" in m.group(0)
        return " [VILLAGE], तहसील" if is_hindi else " [VILLAGE], Tehsil"
    masked_text = RE_VILLAGE_BEFORE_TEHSIL.sub(repl_v_tehsil, masked_text)

    # PIN codes (generalize to 3-digit prefix)
    def repl_pin(m):
        nonlocal count
        count += 1
        return pin_mask(m.group(0))
    masked_text = RE_PIN.sub(repl_pin, masked_text)

    # Step 10b: Propagate all extracted patient and relative names across document
    STOPWORDS = {
        "dr", "doctor", "medicine", "hospital", "patient", "female", "male",
        "review", "weeks", "days", "diet", "discharge", "summary", "report",
        "blood", "sugar", "fever", "hypertension", "diabetes", "routine",
        "admitted", "complaints", "history", "adv", "rx", "years", "year",
        "tablet", "capsule", "syrup", "injection", "dose", "daily", "sos"
    }

    # Find shared tokens (e.g. shared family surnames like 'Verma', 'Sharma')
    p_tokens = {tok.lower() for p in doc_patient_names for tok in p.split()}
    r_tokens = {tok.lower() for r in doc_relative_names for tok in r.split()}
    shared_tokens = p_tokens.intersection(r_tokens)

    # 1. Replace ALL multi-word full names first, ordered by length descending
    all_full_names = []
    for p in doc_patient_names:
        cp = p.strip()
        if len(cp) >= 3 and cp.lower() not in STOPWORDS:
            all_full_names.append((len(cp), cp, name_repl))
    for r in doc_relative_names:
        cr = r.strip()
        if len(cr) >= 3 and cr.lower() not in STOPWORDS:
            all_full_names.append((len(cr), cr, "[RELATIVE]"))
    all_full_names.sort(key=lambda x: x[0], reverse=True)

    for _, name_val, repl_val in all_full_names:
        if any("\u0900" <= c <= "\u097f" for c in name_val):
            masked_text, n = re.subn(re.escape(name_val), repl_val, masked_text)
            count += n
        else:
            masked_text, n = re.subn(r"(?i)\b" + re.escape(name_val) + r"\b", repl_val, masked_text)
            count += n

    # 2. Replace unshared individual tokens
    for pname in doc_patient_names:
        for tok in pname.strip().split():
            low_tok = tok.lower()
            if len(tok) >= 4 and low_tok not in STOPWORDS and low_tok not in shared_tokens:
                if any("\u0900" <= c <= "\u097f" for c in tok):
                    masked_text, n = re.subn(re.escape(tok), name_repl, masked_text)
                    count += n
                else:
                    masked_text, n = re.subn(r"(?i)\b" + re.escape(tok) + r"\b", name_repl, masked_text)
                    count += n

    for rname in doc_relative_names:
        for tok in rname.strip().split():
            low_tok = tok.lower()
            if len(tok) >= 4 and low_tok not in STOPWORDS and low_tok not in shared_tokens:
                if any("\u0900" <= c <= "\u097f" for c in tok):
                    masked_text, n = re.subn(re.escape(tok), "[RELATIVE]", masked_text)
                    count += n
                else:
                    masked_text, n = re.subn(r"(?i)\b" + re.escape(tok) + r"\b", "[RELATIVE]", masked_text)
                    count += n

    # Step 11: Date Shifting (ensures DOB & clinical dates are always shifted)
    eff_shift = shift
    if eff_shift == 0:
        if patient_pid:
            pid_hash = int(hashlib.sha256(patient_pid.encode("utf-8")).hexdigest()[:8], 16)
            eff_shift = (pid_hash % 61) - 30
            if eff_shift == 0:
                eff_shift = 17
        else:
            eff_shift = 17

    masked_text = RE_DATE_ISO.sub(lambda m: shift_iso_date(m, eff_shift), masked_text)
    masked_text = RE_DATE_SLASH.sub(lambda m: shift_slash_date(m, eff_shift), masked_text)
    masked_text = RE_DATE_DASH.sub(lambda m: shift_dash_date(m, eff_shift), masked_text)

    # Step 12: Restore protected clinical spans
    final_text = unmask_preserved_spans(masked_text, slots)
    return final_text, count
