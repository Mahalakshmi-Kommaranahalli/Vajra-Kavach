from __future__ import annotations
import csv
import io
import re
import datetime as dt
from vajra.crypto import age_band, pin_mask, date_shift_days
from vajra.detectors import sanitize_text, shift_slash_date, shift_dash_date, shift_iso_date
from vajra.contextual import PRESERVED_DISTRICTS

# Header role matchers
RE_NAME_COL = re.compile(r"(?i)^(?:patient[-_\s]*name|naam|patient|name|first[-_\s]*name|last[-_\s]*name)$")
RE_REL_COL = re.compile(r"(?i)^(?:relative[-_\s]*name|guardian|pita/pati[-_\s]*ka[-_\s]*naam|attendant|father/husband)$")
RE_MRN_COL = re.compile(r"(?i)^(?:uhid|patient[-_\s]*id|reg[-_\s]*no|mrn|id)$")
RE_AGE_COL = re.compile(r"(?i)^(?:age|umar|आयु|age[-_/]sex)$")
RE_DOB_COL = re.compile(r"(?i)^(?:dob|janm[-_\s]*tithi|जन्म[-_\s]*तिथि).*$")
RE_DATE_COL = re.compile(r"(?i)^(?:reg[-_\s]*date|registered.*|date|admission|discharge|visit[-_\s]*date|collected.*|reported.*)$")
RE_PHONE_COL = re.compile(r"(?i)^(?:mobile|phone|contact|phone[-_\s]*no)$")
RE_AADHAAR_COL = re.compile(r"(?i)^(?:aadhaar.*|aadhar.*)$")
RE_ABHA_COL = re.compile(r"(?i)^(?:abha.*)$")
RE_PIN_COL = re.compile(r"(?i)^(?:pin|zip|postal.*)$")
RE_VILLAGE_COL = re.compile(r"(?i)^(?:village.*|gaon|gram|city|शहर|ग्राम|गांव)$")
RE_DISTRICT_COL = re.compile(r"(?i)^(?:district|jila|जिला)$")
RE_ADDRESS_COL = re.compile(r"(?i)^(?:address|street|pata|पता)$")

def sanitize_header(header: list[str]) -> tuple[list[str], int]:
    """Sanitize CSV/TSV headers if they contain PII (e.g. JJH-0077112 Zainab)."""
    san_header = []
    changes = 0
    for idx, col in enumerate(header):
        if re.search(r"(?:JJH|SNJ|DHH|IPD?|ADM)[-/]?\d+", col):
            changes += 2
            san_header.append(f"vitals_col_{idx}")
            continue
        cleaned, n = sanitize_text(col)
        if n > 0:
            changes += n
            col_clean = re.sub(r"\s+", " ", cleaned).strip()
            san_header.append(col_clean if col_clean else "Column")
        else:
            san_header.append(col)
    return san_header, changes

def process_csv_content(
    text: str,
    delimiter: str,
    file_rel: str,
    record_pseudonyms: dict[str, str | None],
) -> tuple[str, list[dict], int]:
    """Process a CSV/TSV document row by row, returning (sanitized_csv, records_entries, pii_count)."""
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    if not rows:
        return "", [], 0
    
    header = rows[0]
    body = rows[1:]
    san_header, pii_count = sanitize_header(header)
    
    # Classify column roles based on header names
    col_roles = []
    for col_name in header:
        c_low = col_name.strip().lower()
        if RE_MRN_COL.match(c_low):
            col_roles.append("MRN")
        elif RE_NAME_COL.match(c_low):
            col_roles.append("NAME")
        elif RE_REL_COL.match(c_low):
            col_roles.append("RELATIVE")
        elif RE_AGE_COL.match(c_low):
            col_roles.append("AGE")
        elif RE_DOB_COL.match(c_low):
            col_roles.append("DOB")
        elif RE_DATE_COL.match(c_low):
            col_roles.append("DATE")
        elif RE_PHONE_COL.match(c_low):
            col_roles.append("PHONE")
        elif RE_AADHAAR_COL.match(c_low):
            col_roles.append("AADHAAR")
        elif RE_ABHA_COL.match(c_low):
            col_roles.append("ABHA")
        elif RE_PIN_COL.match(c_low):
            col_roles.append("PIN")
        elif RE_VILLAGE_COL.match(c_low):
            col_roles.append("VILLAGE")
        elif RE_DISTRICT_COL.match(c_low):
            col_roles.append("DISTRICT")
        elif RE_ADDRESS_COL.match(c_low):
            col_roles.append("ADDRESS")
        else:
            col_roles.append("GENERAL")

    san_body = []
    records = []
    
    is_admin_or_misc = file_rel.startswith(("misc/", "clean/")) or "ward_vitals" in file_rel

    for i, row in enumerate(body):
        loc = f"row:{i}"
        rec_id = f"{file_rel}:{loc}"
        pid = None if is_admin_or_misc else record_pseudonyms.get(rec_id)
        shift = date_shift_days(pid if pid else rec_id)
        
        san_row = []
        for j, cell in enumerate(row):
            val = cell.strip()
            role = col_roles[j] if j < len(col_roles) else "GENERAL"
            
            if not val:
                san_row.append("")
                continue
                
            if role == "MRN":
                san_row.append(pid if pid else "[MRN]")
                pii_count += 1
            elif role == "NAME":
                san_row.append(pid if pid else "[NAME]")
                pii_count += 1
            elif role == "RELATIVE":
                san_row.append("[RELATIVE]")
                pii_count += 1
            elif role == "AGE":
                m_as = re.match(r"^(\d{1,2})\s*/\s*([MFmf])$", val)
                if m_as:
                    san_row.append(f"{age_band(int(m_as.group(1)))}/{m_as.group(2).upper()}")
                else:
                    digits = "".join(c for c in val if c.isdigit())
                    if digits:
                        san_row.append(age_band(int(digits)))
                    else:
                        san_row.append(val)
                pii_count += 1
            elif role == "DOB":
                shifted_dob = val
                if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                    shifted_dob = shift_iso_date(re.match(r"^(\d{4})-(\d{2})-(\d{2})$", val), shift)
                elif "/" in val:
                    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", val)
                    if m:
                        shifted_dob = shift_slash_date(m, shift)
                elif "-" in val:
                    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", val)
                    if m:
                        shifted_dob = shift_dash_date(m, shift)
                san_row.append(shifted_dob)
                pii_count += 1
            elif role == "DATE":
                shifted_date = val
                if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                    shifted_date = shift_iso_date(re.match(r"^(\d{4})-(\d{2})-(\d{2})$", val), shift)
                elif "/" in val:
                    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", val)
                    if m:
                        shifted_date = shift_slash_date(m, shift)
                elif "-" in val:
                    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", val)
                    if m:
                        shifted_date = shift_dash_date(m, shift)
                san_row.append(shifted_date)
            elif role == "PHONE":
                san_row.append("[PHONE]")
                pii_count += 1
            elif role == "AADHAAR":
                san_row.append("[AADHAAR]")
                pii_count += 1
            elif role == "ABHA":
                san_row.append("[ABHA]")
                pii_count += 1
            elif role == "PIN":
                san_row.append(pin_mask(val))
                pii_count += 1
            elif role == "VILLAGE":
                san_row.append("[VILLAGE]")
                pii_count += 1
            elif role == "DISTRICT":
                san_row.append(val)
            elif role == "ADDRESS":
                clean_addr, n = sanitize_text(val, pid, shift)
                san_row.append(clean_addr)
                pii_count += n
            else:
                clean_val, n = sanitize_text(val, pid, shift)
                san_row.append(clean_val)
                pii_count += n

        san_body.append(san_row)
        records.append({
            "file": f"sanitized/{file_rel}",
            "loc": loc,
            "patient": pid,
        })
    
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    w.writerow(san_header)
    w.writerows(san_body)
    return buf.getvalue(), records, pii_count
