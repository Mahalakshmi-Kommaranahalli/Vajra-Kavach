from __future__ import annotations
import re
from collections import defaultdict
from vajra.transliteration import normalize_name, indic_digits_to_ascii
from vajra.crypto import pseudonym

RE_PHONE_CORE = re.compile(r"(?<!\d)(?:(?:\+?91[\s-]?)?0?)?([6-9]\d{9})(?!\d)")
RE_AADHAAR_CORE = re.compile(r"\b(?:\d{4}[\s-]\d{4}[\s-]\d{4}|\d{12})\b")
RE_ABHA_CORE = re.compile(r"\b(91[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b")

DISEASE_WORDS = {
    "dm", "htn", "fever", "pain", "hypothyroidism", "dengue", "tb", "cough",
    "weakness", "burning", "micturition", "loose", "stools", "treatment", "address",
    "near", "ward", "opp", "bell", "palsy", "asthma", "rabies", "typhoid", "malaria",
    "type", "attendant", "informed", "advised", "reviewed", "patient"
}

class DisjointSet:
    def __init__(self):
        self.parent = {}
    
    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            return x
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[ry] = rx

def extract_clues_from_record(text: str, file_rel: str) -> dict:
    """Extract all available linkage clues from raw text and file context."""
    if file_rel.startswith(("misc/", "clean/")) or file_rel.startswith("notes/visitor_log"):
        return {
            "phones": set(),
            "aadhaar": set(),
            "abha": set(),
            "mrns": set(),
            "patient_names": set(),
            "relative_names": set(),
            "dob": None,
            "age": None,
        }

    ascii_text = indic_digits_to_ascii(text)
    
    # 1. Phone numbers
    phones = set()
    for m in RE_PHONE_CORE.finditer(ascii_text):
        phones.add(m.group(1))
    for m in re.finditer(r"\b0?([6-9]\d{4})-?(\d{5})\b", ascii_text):
        phones.add(m.group(1) + m.group(2))
    
    # Check filename for phone
    for m in re.finditer(r"\b([6-9]\d{9})\b", file_rel):
        phones.add(m.group(1))

    # 2. Aadhaar
    aadhaar = set()
    for m in RE_AADHAAR_CORE.finditer(ascii_text):
        cand = re.sub(r"[\s-]", "", m.group(0))
        if len(cand) == 12 and not cand.startswith("0000"):
            aadhaar.add(cand)

    # 3. ABHA
    abha = set()
    for m in RE_ABHA_CORE.finditer(ascii_text):
        clean_abha = re.sub(r"[\s-]", "", m.group(1))
        if len(clean_abha) == 14:
            abha.add(clean_abha)

    # 4. MRNs
    mrns = set()
    for m in re.finditer(
        r"\b(SNJ/\d{2}/\d{6}|JJH-\d{7}|DHH\d{4}-\d{6}|DHH-IPD-\d{5}|UHID-\d{5,7}|"
        r"IP[D]?[-/]\d{2}[-/]\d{5}|ADM\d{6}|adm\d{6}|ipd-\d{4}-\d{5}|ip-\d{2}-\d{5})\b",
        text
    ):
        mrns.add(m.group(1).upper().replace("/", "-"))
    
    # Check filename for MRN
    for m in re.finditer(
        r"(SNJ-\d{2}-\d{6}|JJH-\d{7}|DHH\d{4}-\d{6}|DHH-IPD-\d{5}|UHID-\d{5,7}|"
        r"IPD?-\d{2,4}-\d{5}|ADM\d{6})",
        file_rel, re.I
    ):
        mrns.add(m.group(1).upper().replace("/", "-"))

    # 5. Names (Patient and Relative)
    patient_names = set()
    relative_names = set()
    
    # Check name labels
    for m in re.finditer(r"(?i)(?:Patient Name|Name|Patient|Pt|नाम|मरीज|Naam):\s*([^\n,;|]+)", text):
        norm = normalize_name(m.group(1).strip())
        if norm and len(norm) > 2 and norm not in DISEASE_WORDS:
            patient_names.add(norm)
    
    # Check honorifics: e.g. Shahid sahab, Parvati ji, Brijesh babu
    for m in re.finditer(r"\b([A-Za-z\u0900-\u097f]+)\s+(?:sahab|sahib|babu|ji|didi|amma|bhai|bhaiya|behenji)\b", text):
        norm = normalize_name(m.group(1).strip())
        if norm and len(norm) > 2 and norm not in ("dr", "doctor") and norm not in DISEASE_WORDS:
            patient_names.add(norm)

    # Check relatives (S/o, D/o, W/o, C/O)
    for m in re.finditer(r"(?i)\b(?:S/o|D/o|W/o|C/O)\s+([A-Za-z\u0900-\u097f]+(?:\s+[A-Za-z\u0900-\u097f]+)*)", text):
        val = m.group(1).strip()
        norm = normalize_name(val)
        # Filter out medical terms and short abbreviations
        tokens = [t for t in norm.split() if t not in DISEASE_WORDS]
        if tokens and len(" ".join(tokens)) > 3:
            relative_names.add(" ".join(tokens))
    
    # Attendant
    for m in re.finditer(r"(?i)\bAttendant\s*\((?:S/o|D/o|W/o)\s+([^\)]+)\)", text):
        norm = normalize_name(m.group(1).strip())
        tokens = [t for t in norm.split() if t not in DISEASE_WORDS]
        if tokens and len(" ".join(tokens)) > 3:
            relative_names.add(" ".join(tokens))
            
    # Check filename for patient name (e.g. Discharge_Summary_Reena_Nishad_...)
    for m in re.finditer(r"Discharge_Summary_([A-Za-z]+)_([A-Za-z]+)_", file_rel):
        full = f"{m.group(1)} {m.group(2)}"
        norm = normalize_name(full)
        if norm:
            patient_names.add(norm)

    # 6. DOB and Age
    dob = None
    m_dob = re.search(r"(?i)(?:DOB|Janm Tithi|जन्म तिथि):\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2})", text)
    if m_dob:
        dob = m_dob.group(1)

    age = None
    m_age = re.search(r"(?i)(?:Age|Umar|आयु):\s*(\d{1,2})\s*(?:वर्ष|yrs|years)?", text)
    if m_age:
        try:
            age = int(m_age.group(1))
        except ValueError:
            pass

    return {
        "phones": phones,
        "aadhaar": aadhaar,
        "abha": abha,
        "mrns": mrns,
        "patient_names": patient_names,
        "relative_names": relative_names,
        "dob": dob,
        "age": age,
    }

def cluster_records(record_clues: dict[str, dict]) -> dict[str, str | None]:
    """Cluster records into patient identities using conservative, homonym-safe linking."""
    ds = DisjointSet()
    
    # 1. Block on strong keys (Phones, Aadhaar, ABHA, MRNs)
    by_phone = defaultdict(list)
    by_aadhaar = defaultdict(list)
    by_abha = defaultdict(list)
    by_mrn = defaultdict(list)
    by_name = defaultdict(list)
    
    for rid, clues in record_clues.items():
        for p in clues["phones"]:
            by_phone[p].append(rid)
        for a in clues["aadhaar"]:
            by_aadhaar[a].append(rid)
        for ab in clues["abha"]:
            by_abha[ab].append(rid)
        for m in clues["mrns"]:
            by_mrn[m].append(rid)
        for n in clues["patient_names"]:
            by_name[n].append(rid)

    # Union on unambiguous strong identifiers
    for p, rids in by_phone.items():
        for i in range(1, len(rids)):
            ds.union(rids[0], rids[i])
            
    for a, rids in by_aadhaar.items():
        for i in range(1, len(rids)):
            ds.union(rids[0], rids[i])

    for ab, rids in by_abha.items():
        for i in range(1, len(rids)):
            ds.union(rids[0], rids[i])

    for m, rids in by_mrn.items():
        for i in range(1, len(rids)):
            ds.union(rids[0], rids[i])

    # 2. Soft matching with Homonym Protection
    for name, rids in by_name.items():
        tokens = name.split()
        is_full_name = len(tokens) >= 2
        
        # For single token given names (e.g. 'zainab'), ONLY link if there is a matching relative
        for i in range(len(rids)):
            r1 = rids[i]
            c1 = record_clues[r1]
            root1 = ds.find(r1)
            
            for j in range(i + 1, len(rids)):
                r2 = rids[j]
                c2 = record_clues[r2]
                root2 = ds.find(r2)
                if root1 == root2:
                    continue  # Already linked
                
                # Check for homonym conflicts:
                # 1. Different phones
                if c1["phones"] and c2["phones"] and not (c1["phones"] & c2["phones"]):
                    continue
                
                # 2. Conflicting hospital MRNs from the same hospital system
                hosp1 = {m.split("-")[0] for m in c1["mrns"] if "-" in m}
                hosp2 = {m.split("-")[0] for m in c2["mrns"] if "-" in m}
                if (hosp1 & hosp2) and not (c1["mrns"] & c2["mrns"]):
                    continue
                
                # 3. Relative check
                clean_rel1 = {r for r in c1["relative_names"] if len(r) > 3 and r not in DISEASE_WORDS}
                clean_rel2 = {r for r in c2["relative_names"] if len(r) > 3 and r not in DISEASE_WORDS}
                rel_match = bool(clean_rel1 & clean_rel2)
                
                # If both have relatives but they conflict, do not merge!
                if clean_rel1 and clean_rel2 and not rel_match:
                    continue
                
                # 4. DOB / Age check
                dob_match = bool(c1["dob"] and c2["dob"] and c1["dob"] == c2["dob"])
                age_match = bool(c1["age"] is not None and c2["age"] is not None and abs(c1["age"] - c2["age"]) <= 1)
                
                # If it's a single first name (e.g. 'zainab' or 'sunil'), require strict relative match or exact DOB
                if not is_full_name:
                    if rel_match or (dob_match and age_match):
                        ds.union(r1, r2)
                        root1 = ds.find(r1)
                else:
                    # Full name (e.g. 'brijesh yadav'): require relative match or dob/age match or no conflict
                    if rel_match or dob_match or (age_match and (not clean_rel1 or not clean_rel2)):
                        ds.union(r1, r2)
                        root1 = ds.find(r1)

    # 3. Build clusters and assign pseudonyms
    clusters = defaultdict(list)
    for rid in record_clues:
        root = ds.find(rid)
        clusters[root].append(rid)

    pseudonyms = {}
    for root, members in clusters.items():
        has_clues = any(
            record_clues[m]["phones"] or record_clues[m]["aadhaar"] or
            record_clues[m]["abha"] or record_clues[m]["mrns"] or
            record_clues[m]["patient_names"]
            for m in members
        )
        if not has_clues:
            for m in members:
                pseudonyms[m] = None
            continue
        
        canon_key = sorted(members)[0]
        strong_key = ""
        for m in sorted(members):
            c = record_clues[m]
            if c["aadhaar"]:
                strong_key = sorted(c["aadhaar"])[0]
                break
            elif c["abha"]:
                strong_key = sorted(c["abha"])[0]
                break
            elif c["phones"]:
                strong_key = sorted(c["phones"])[0]
                break
            elif c["mrns"]:
                strong_key = sorted(c["mrns"])[0]
                break
        
        cluster_id = f"{strong_key}|{canon_key}" if strong_key else canon_key
        pid = pseudonym(cluster_id)
        for m in members:
            pseudonyms[m] = pid

    return pseudonyms
