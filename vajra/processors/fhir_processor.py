from __future__ import annotations
import base64
import json
import re
from vajra.crypto import pin_mask, date_shift_days
from vajra.detectors import sanitize_text, shift_iso_date, RE_MRN

def process_fhir_bundle(
    data: dict,
    file_rel: str,
    record_pseudonyms: dict[str, str | None],
) -> tuple[dict, list[dict], int]:
    """Process a FHIR R4 Bundle safely and deterministically, preserving valid syntax and resolvable references."""
    rec_id = f"{file_rel}:doc"
    pid = record_pseudonyms.get(rec_id)
    shift = date_shift_days(pid if pid else rec_id)
    pii_count = 0

    entries = data.get("entry", [])

    # Pass 1: Extract known patient and relative names from Patient resource
    known_patient_names = set()
    known_relative_names = set()
    for e in entries:
        res = e.get("resource", {})
        if res.get("resourceType") == "Patient":
            for n in res.get("name", []):
                if "text" in n and n["text"]:
                    known_patient_names.add(n["text"])
                tokens = n.get("given", []) + ([n["family"]] if "family" in n else [])
                if tokens:
                    known_patient_names.add(" ".join(tokens))
            for c in res.get("contact", []):
                if "name" in c and isinstance(c["name"], dict) and "text" in c["name"]:
                    known_relative_names.add(c["name"]["text"])
            for ext in res.get("extension", []):
                if "valueString" in ext:
                    known_relative_names.add(ext["valueString"])

    # Pass 2: Sanitize all resources
    for e in entries:
        res = e.get("resource", {})
        rtype = res.get("resourceType")

        # Sanitize HTML narrative text div
        if "text" in res and isinstance(res["text"], dict) and "div" in res["text"]:
            if rtype == "Patient":
                res["text"]["div"] = f'<div xmlns="http://www.w3.org/1999/xhtml">{pid if pid else "[NAME]"}</div>'
                pii_count += 1
            else:
                div_val = res["text"]["div"]
                clean_div, nd = sanitize_text(div_val, pid, shift, known_patient_names, known_relative_names)
                res["text"]["div"] = clean_div
                pii_count += nd

        # Sanitize subject/patient displays
        if "subject" in res and isinstance(res["subject"], dict) and "display" in res["subject"]:
            res["subject"]["display"] = pid if pid else "[NAME]"
            pii_count += 1
        if "patient" in res and isinstance(res["patient"], dict) and "display" in res["patient"]:
            res["patient"]["display"] = pid if pid else "[NAME]"
            pii_count += 1

        if rtype == "Patient":
            # Sanitize all identifiers
            if pid:
                res["identifier"] = [{
                    "system": "https://vajra-kavach.in/psn",
                    "value": pid
                }]
                res["name"] = [{
                    "text": pid,
                    "family": pid,
                    "given": [pid],
                }]
            else:
                res["identifier"] = [{
                    "system": "https://vajra-kavach.in/psn",
                    "value": "[MRN]"
                }]
                res["name"] = [{
                    "text": "[NAME]",
                    "family": "[NAME]",
                    "given": ["[NAME]"],
                }]
            pii_count += 3

            # Remove telecom
            if "telecom" in res:
                pii_count += len(res["telecom"])
                res["telecom"] = []

            # Remove/sanitize contact relatives
            if "contact" in res:
                for c in res["contact"]:
                    if "name" in c and isinstance(c["name"], dict):
                        c["name"]["text"] = "[RELATIVE]"
                        pii_count += 1
                    if "telecom" in c:
                        c["telecom"] = []
                        pii_count += 1

            # Sanitize extensions (e.g. mothers-name)
            if "extension" in res and isinstance(res["extension"], list):
                for ext in res["extension"]:
                    if "valueString" in ext:
                        ext["valueString"] = "[RELATIVE]"
                        pii_count += 1

            # Generalize address
            if "address" in res:
                for addr in res["address"]:
                    if "line" in addr:
                        pii_count += len(addr["line"])
                        addr["line"] = ["[ADDRESS]"]
                    if "city" in addr:
                        pii_count += 1
                        addr["city"] = "[VILLAGE]"
                    if "postalCode" in addr:
                        pii_count += 1
                        addr["postalCode"] = pin_mask(addr["postalCode"])

            # Shift birthDate
            if "birthDate" in res:
                m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", res["birthDate"])
                if m:
                    res["birthDate"] = shift_iso_date(m, shift)

        elif rtype == "Encounter":
            if "identifier" in res:
                res["identifier"] = [{
                    "system": "https://vajra-kavach.in/psn",
                    "value": pid if pid else "[MRN]"
                }]
                pii_count += 1

        elif rtype == "DocumentReference":
            for c in res.get("content", []):
                att = c.get("attachment", {})
                if "data" in att and att["data"]:
                    try:
                        raw_bytes = base64.b64decode(att["data"])
                        raw_text = raw_bytes.decode("utf-8", errors="replace")
                        clean_att_text, n = sanitize_text(raw_text, pid, shift, known_patient_names, known_relative_names)
                        pii_count += n
                        att["data"] = base64.b64encode(clean_att_text.encode("utf-8")).decode("ascii")
                    except Exception:
                        pass

        elif rtype == "Binary":
            if "data" in res and res["data"]:
                try:
                    raw_bytes = base64.b64decode(res["data"])
                    raw_text = raw_bytes.decode("utf-8", errors="replace")
                    clean_att_text, n = sanitize_text(raw_text, pid, shift, known_patient_names, known_relative_names)
                    pii_count += n
                    res["data"] = base64.b64encode(clean_att_text.encode("utf-8")).decode("ascii")
                except Exception:
                    pass

        # Date shifting for Encounters, Conditions, Observations
        for date_key in ("effectiveDateTime", "recordedDate", "authoredOn", "date"):
            if date_key in res and isinstance(res[date_key], str):
                m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", res[date_key])
                if m:
                    res[date_key] = shift_iso_date(m, shift) + res[date_key][10:]

        if "period" in res and isinstance(res["period"], dict):
            p = res["period"]
            for pk in ("start", "end"):
                if pk in p and isinstance(p[pk], str):
                    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", p[pk])
                    if m:
                        p[pk] = shift_iso_date(m, shift) + p[pk][10:]

    records = [{
        "file": f"sanitized/{file_rel}",
        "loc": "doc",
        "patient": pid,
    }]

    # Final pass over bundle JSON string to catch residual MRNs and names
    json_str = json.dumps(data, ensure_ascii=False)
    mrn_repl = pid if pid else "[MRN]"
    json_str, n_mrn = RE_MRN.subn(mrn_repl, json_str)
    pii_count += n_mrn

    for pname in known_patient_names:
        if len(pname) >= 3:
            json_str, n_p = re.subn(r"(?i)\b" + re.escape(pname) + r"\b", pid if pid else "[NAME]", json_str)
            pii_count += n_p
            for tok in pname.split():
                if len(tok) >= 4 and tok.lower() not in ("hospital", "patient", "bundle"):
                    json_str, n_tok = re.subn(r"(?i)\b" + re.escape(tok) + r"\b", pid if pid else "[NAME]", json_str)
                    pii_count += n_tok

    for rname in known_relative_names:
        if len(rname) >= 3:
            json_str, n_r = re.subn(r"(?i)\b" + re.escape(rname) + r"\b", "[RELATIVE]", json_str)
            pii_count += n_r
            for tok in rname.split():
                if len(tok) >= 4 and tok.lower() not in ("hospital", "relative", "bundle"):
                    json_str, n_tok = re.subn(r"(?i)\b" + re.escape(tok) + r"\b", "[RELATIVE]", json_str)
                    pii_count += n_tok

    data = json.loads(json_str)
    return data, records, pii_count
