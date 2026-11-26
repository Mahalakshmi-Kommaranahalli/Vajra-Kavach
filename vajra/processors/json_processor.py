from __future__ import annotations
import base64
import json
import re
from vajra.crypto import age_band, pin_mask, date_shift_days
from vajra.detectors import sanitize_text, shift_iso_date

def sanitize_json_leaf(val, pid: str | None, shift: int, known_names: set[str] | None = None) -> tuple[any, int]:
    """Recursively clean leaf values, decoding base64 if detected."""
    if isinstance(val, str):
        # Check if value is a base64 encoded string
        if len(val) >= 24 and re.match(r"^[A-Za-z0-9+/]+={0,2}$", val.strip()):
            try:
                decoded = base64.b64decode(val.strip()).decode("utf-8")
                clean_text, n = sanitize_text(decoded, pid, shift, known_names=known_names)
                re_encoded = base64.b64encode(clean_text.encode("utf-8")).decode("ascii")
                return re_encoded, n
            except Exception:
                pass
        
        # Check if string is a date
        if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
            shifted = shift_iso_date(re.match(r"^(\d{4})-(\d{2})-(\d{2})$", val), shift)
            return shifted, 0
        
        clean_text, n = sanitize_text(val, pid, shift, known_names=known_names)
        return clean_text, n
    
    if isinstance(val, int) and val > 1000000000:
        # Probable Aadhaar or phone number as an integer
        return 0, 1
        
    return val, 0

def clean_dict_node(d: dict, pid: str | None, shift: int, known_names: set[str] | None = None) -> tuple[dict, int]:
    """Clean dictionary node, sanitizing both keys and values."""
    new_dict = {}
    pii_count = 0
    names = set(known_names) if known_names else set()

    # Pre-scan for patient names in this node
    if "patient" in d and isinstance(d["patient"], dict) and "name" in d["patient"]:
        names.add(str(d["patient"]["name"]))
    if "patient_name" in d and isinstance(d["patient_name"], str):
        names.add(d["patient_name"])
    if "name" in d and isinstance(d["name"], str):
        if any(k in d for k in ("hospital_uhid", "uhid", "age", "phone", "sex", "gender", "guardian", "patient_ref")):
            names.add(d["name"])

    for k, v in d.items():
        clean_k, nk = sanitize_text(k, pid, shift, known_names=names)
        pii_count += nk
        
        k_low = k.strip().lower()
        if k_low in ("uhid", "mrn", "patient_id", "patientid", "hospital_uhid", "patient_ref"):
            new_dict[clean_k] = pid if pid else "[MRN]"
            pii_count += 1
        elif k_low in ("patient_name", "first", "last", "local"):
            new_dict[clean_k] = pid if pid else "[NAME]"
            pii_count += 1
        elif k_low == "patient":
            if isinstance(v, str):
                new_dict[clean_k] = pid if pid else "[NAME]"
                pii_count += 1
            elif isinstance(v, dict):
                sub_d, sub_n = clean_dict_node(v, pid, shift, names)
                new_dict[clean_k] = sub_d
                pii_count += sub_n
            else:
                new_dict[clean_k] = v
        elif k_low == "by_name" and isinstance(v, dict):
            new_sub = {}
            for sub_k, sub_v in v.items():
                new_sub["[NAME]"] = pid if pid else "[MRN]"
                pii_count += 2
            new_dict[clean_k] = new_sub
        elif k_low == "by_uhid" and isinstance(v, dict):
            new_sub = {}
            for sub_k, sub_v in v.items():
                clean_sub_v, sv_n = clean_dict_node(sub_v, pid, shift, names) if isinstance(sub_v, dict) else (sub_v, 0)
                new_sub[pid if pid else "[MRN]"] = clean_sub_v
                pii_count += 1 + sv_n
            new_dict[clean_k] = new_sub
        elif k_low == "name" and isinstance(v, str):
            if any(sibling in d for sibling in ("uhid", "hospital_uhid", "patient_ref", "age", "phone", "sex", "gender", "guardian")):
                new_dict[clean_k] = pid if pid else "[NAME]"
                pii_count += 1
            else:
                clean_v, nv = sanitize_text(v, pid, shift, known_names=names)
                new_dict[clean_k] = clean_v
                pii_count += nv
        elif k_low in ("guardian", "relative_name"):
            new_dict[clean_k] = "[RELATIVE]"
            pii_count += 1
        elif k_low in ("mobile", "phone", "contact_no"):
            new_dict[clean_k] = "[PHONE]"
            pii_count += 1
        elif k_low in ("age", "umar"):
            if isinstance(v, (int, str)):
                try:
                    num_age = int(str(v).split()[0])
                    new_dict[clean_k] = age_band(num_age)
                    pii_count += 1
                except Exception:
                    new_dict[clean_k] = v
            else:
                new_dict[clean_k] = v
        elif k_low in ("pin", "zip", "postalcode"):
            new_dict[clean_k] = pin_mask(str(v))
            pii_count += 1
        elif k_low in ("village", "gaon", "gram"):
            new_dict[clean_k] = "[VILLAGE]"
            pii_count += 1
        elif k_low in ("source_path", "filepath", "path"):
            clean_path = re.sub(r"[A-Za-z]+_[A-Za-z]+_\d+", "anonymous_export", str(v))
            clean_path, np = sanitize_text(clean_path, pid, shift, known_names=names)
            new_dict[clean_k] = clean_path
            pii_count += np + 1
        elif k_low in ("notes", "complaints"):
            clean_note, nn = sanitize_text(str(v), pid, shift, known_names=names)
            new_dict[clean_k] = clean_note
            pii_count += nn
        else:
            if isinstance(v, dict):
                sub_d, sub_n = clean_dict_node(v, pid, shift, names)
                new_dict[clean_k] = sub_d
                pii_count += sub_n
            elif isinstance(v, list):
                sub_list = []
                for item in v:
                    if isinstance(item, dict):
                        item_d, item_n = clean_dict_node(item, pid, shift, names)
                        sub_list.append(item_d)
                        pii_count += item_n
                    else:
                        item_val, item_n = sanitize_json_leaf(item, pid, shift, names)
                        sub_list.append(item_val)
                        pii_count += item_n
                new_dict[clean_k] = sub_list
            else:
                leaf_v, nl = sanitize_json_leaf(v, pid, shift, names)
                new_dict[clean_k] = leaf_v
                pii_count += nl

    return new_dict, pii_count

# The ONLY keys that define array sub-records in this dataset
SUB_RECORD_KEYS = {"visits", "results", "patients"}

def process_json_content(
    text: str,
    file_rel: str,
    record_pseudonyms: dict[str, str | None],
) -> tuple[str, list[dict], int]:
    """Process arbitrary JSON documents, properly generating RFC 6901 pointers for lists of records."""
    data = json.loads(text)
    records = []
    pii_count = 0

    has_sub_records = False
    if isinstance(data, dict):
        for k in list(data.keys()):
            v = data[k]
            if k in SUB_RECORD_KEYS and isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                has_sub_records = True
                pointer_key = k.replace("~", "~0").replace("/", "~1")
                for i, rec_item in enumerate(v):
                    loc = f"/{pointer_key}/{i}"
                    rec_id = f"{file_rel}:{loc}"
                    pid = record_pseudonyms.get(rec_id)
                    shift = date_shift_days(pid if pid else rec_id)
                    
                    cleaned_item, n = clean_dict_node(rec_item, pid, shift)
                    pii_count += n
                    v[i] = cleaned_item
                    
                    records.append({
                        "file": f"sanitized/{file_rel}",
                        "loc": loc,
                        "patient": pid,
                    })

    if not has_sub_records:
        loc = "doc"
        rec_id = f"{file_rel}:{loc}"
        pid = record_pseudonyms.get(rec_id)
        shift = date_shift_days(pid if pid else rec_id)

        if isinstance(data, dict):
            cleaned_data, n = clean_dict_node(data, pid, shift)
            pii_count += n
            data = cleaned_data
        elif isinstance(data, list):
            cleaned_list = []
            for item in data:
                if isinstance(item, dict):
                    cd, n = clean_dict_node(item, pid, shift)
                    pii_count += n
                    cleaned_list.append(cd)
                else:
                    cv, n = sanitize_json_leaf(item, pid, shift)
                    pii_count += n
                    cleaned_list.append(cv)
            data = cleaned_list
        
        records.append({
            "file": f"sanitized/{file_rel}",
            "loc": loc,
            "patient": pid,
        })

    # Ensure any top-level metadata fields are cleaned
    if isinstance(data, dict):
        for meta_key in ("_export_meta", "facility", "metadata"):
            if meta_key in data and isinstance(data[meta_key], dict):
                clean_meta, nm = clean_dict_node(data[meta_key], None, 0)
                data[meta_key] = clean_meta
                pii_count += nm

    return json.dumps(data, ensure_ascii=False, indent=2) + "\n", records, pii_count
