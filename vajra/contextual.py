from __future__ import annotations
import json
import re
from pathlib import Path
from vajra.config import ASSETS_DIR

# Preserved districts (vital for epidemiological research utility)
PRESERVED_DISTRICTS = {
    "rae bareli", "barabanki", "sitapur", "hardoi", "unnao", "sultanpur", "lucknow", "bahraich",
    "रायबरेली", "बाराबंकी", "सीतापुर", "हरदोई", "उन्नाव", "सुल्तानपुर", "लखनऊ", "बहराइच"
}

# Load from local assets if available (offline-first)
try:
    districts_file = ASSETS_DIR / "gazetteers" / "districts.json"
    if districts_file.exists():
        dist_data = json.loads(districts_file.read_text(encoding="utf-8"))
        for d in dist_data.get("approved_research_districts", []):
            PRESERVED_DISTRICTS.add(d.lower())
        for hd in dist_data.get("hindi_districts", {}).keys():
            PRESERVED_DISTRICTS.add(hd)
except Exception:
    pass

# Doctor mentions
RE_DOCTOR = re.compile(
    r"(?i)\b(?:Dr\.?|Doctor|डॉ\.?)\s+[A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*"
    r"(?:\s*\((?:MD|MS|MBBS|DNB|Medicine|Surgery|Pulmonology|Pediatrics)[^\)]*\))?"
)

# Medical complaints (C/O ... or Hindi/Hinglish symptom durations)
RE_COMPLAINT = re.compile(
    r"(?i)\bC/O\s+(?:fever|pain|cough|headache|weakness|breathlessness|vomiting|loose stools|"
    r"pet mein dard|kamzori|chakkar|giddiness|generalised weakness|[^\n,;]+?(?:days|weeks|wks|months|दिन|हफ़्ते))\b|"
    r"\b\d+\s+दिन\s+से\s+(?:बुखार|पेट\s+दर्द)\b|\b\d+\s+हफ़्ते\s+से\s+खांसी\b|"
    r"\bpet\s+mein\s+dard\s+\d+\s+din\s+se\b|\bkamzori\s+\d+\s+hafte\s+se\b|\bchakkar\s+aana\s+\d+\s+din\s+se\b"
)

# Known Case Of / History Of
RE_HISTORY = re.compile(
    r"(?i)\b(?:K/C/O|H/O)\s+[^\n,;.]+"
)

# Doses and frequencies
RE_DOSES = re.compile(
    r"(?i)\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|mL|puffs)\b|\b[0-3]-[0-3]-[0-3]\b|\b(?:BD|TDS|OD|QID|SOS|HS)\b(?:\s*x\s*\d+\s*(?:days|wks|weeks|months))?|\bx\s*\d+\s*(?:days|wks|weeks|months)\b"
)

# Vitals and Lab tests
RE_VITALS = re.compile(
    r"(?i)\b(?:BP\s*\d+/\d+|Pulse\s*\d+(?:/min)?|Bukhar\s*\d+(?:\s*F)?|Temp\s*\d+(?:\.\d+)?|RBS\s*\d+(?:\s*mg/dL)?|SpO2\s*\d+%)\b|"
    r"\b(?:Haemoglobin|Random Blood Sugar|Serum Creatinine|Serum Sodium|Total WBC Count|TSH)\b"
)

# Diagnoses and eponyms
RE_DIAGNOSES = re.compile(
    r"(?i)\b(?:Essential \(primary\) hypertension|Type 2 diabetes mellitus[^\n,;]*|Hypothyroidism[^\n,;]*|"
    r"Tuberculosis of lung|Typhoid fever|Rabies[^\n,;]*|Visceral leishmaniasis[^\n,;]*|Pneumonia[^\n,;]*|"
    r"Asthma[^\n,;]*|Chronic obstructive pulmonary disease[^\n,;]*|Addison's disease|Parkinson's disease|"
    r"Whipple procedure[^\n,;]*|Deep brain stimulation|Laparoscopic cholecystectomy|"
    r"फेफड़ों की टीबी|निमोनिया|मलेरिया|दमा|रेबीज़|सीओपीडी|काला-अज़ार|"
    r"ICD-10|[A-Z]\d{2}(?:\.\d+)?|ASHA worker|Referred by ASHA worker)\b"
)

def mask_preserved_spans(text: str) -> tuple[str, dict[str, str]]:
    """Temporarily replace clinical preserves with safe tokens so PII detectors don't touch them."""
    slots = {}
    counter = 0

    def replace_slot(m):
        nonlocal counter
        tag = f"__VAJRA_PRESERVE_{counter}__"
        slots[tag] = m.group(0)
        counter += 1
        return tag

    text = RE_DOCTOR.sub(replace_slot, text)
    text = RE_COMPLAINT.sub(replace_slot, text)
    text = RE_HISTORY.sub(replace_slot, text)
    text = RE_DIAGNOSES.sub(replace_slot, text)
    text = RE_DOSES.sub(replace_slot, text)
    text = RE_VITALS.sub(replace_slot, text)

    return text, slots

def unmask_preserved_spans(text: str, slots: dict[str, str]) -> str:
    """Restore the protected medical values exactly."""
    for tag, val in slots.items():
        text = text.replace(tag, val)
    return text
