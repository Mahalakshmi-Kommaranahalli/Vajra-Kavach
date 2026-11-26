import csv
import io
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, ".")
from main import decode_bytes, sanitize_filename
from vajra.linkage import extract_clues_from_record, DisjointSet, DISEASE_WORDS

inp = Path("toolkit/dev/input")
all_record_clues = {}

for path in sorted(inp.rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(inp).as_posix()
    raw = path.read_bytes()
    text = decode_bytes(raw)
    ext = path.suffix.lower()
    if not text or ext not in (".csv", ".tsv", ".json", ".txt"):
        continue
    out_rel = sanitize_filename(rel, 1)

    if ext in (".csv", ".tsv"):
        delim = "\t" if ext == ".tsv" else ","
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
        if rows:
            header = [h.strip().lower() for h in rows[0]]
            name_idx = next((i for i, h in enumerate(header) if h in ("patient name", "naam", "patient", "name", "first name", "firstname")), None)
            uhid_idx = next((i for i, h in enumerate(header) if h in ("uhid", "patient id", "patientid", "reg no", "mrn")), None)
            for i, row in enumerate(rows[1:]):
                loc = f"row:{i}"
                rec_id = f"{out_rel}:{loc}"
                row_text = " ".join(row)
                clues = extract_clues_from_record(row_text, rel)
                if name_idx is not None and name_idx < len(row):
                    from vajra.transliteration import normalize_name
                    n_val = normalize_name(row[name_idx])
                    if n_val:
                        clues["patient_names"].add(n_val)
                if uhid_idx is not None and uhid_idx < len(row):
                    u_val = row[uhid_idx].strip().upper().replace("/", "-")
                    if u_val:
                        clues["mrns"].add(u_val)
                all_record_clues[rec_id] = clues
    elif ext == ".json":
        try:
            data = json.loads(text)
        except Exception:
            continue
        is_fhir = isinstance(data, dict) and data.get("resourceType") == "Bundle"
        has_sub = False
        if isinstance(data, dict) and not is_fhir:
            for k, v in data.items():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                    has_sub = True
                    pointer_key = k.replace("~", "~0").replace("/", "~1")
                    for i, item in enumerate(v):
                        loc = f"/{pointer_key}/{i}"
                        rec_id = f"{out_rel}:{loc}"
                        all_record_clues[rec_id] = extract_clues_from_record(json.dumps(item), rel)
        if not has_sub:
            loc = "doc"
            rec_id = f"{out_rel}:{loc}"
            all_record_clues[rec_id] = extract_clues_from_record(text, rel)
    else:
        loc = "doc"
        rec_id = f"{out_rel}:{loc}"
        all_record_clues[rec_id] = extract_clues_from_record(text, rel)

# Now simulate clustering step by step and print when any bad_rid is unioned!
bad_rids = {
    'registration/sanjeevani_registration.csv:row:5',
    'registration/sanjeevani_registration.csv:row:7',
    'registration/sanjeevani_registration.csv:row:19',
    'registration/jeevanjyoti_patients.tsv:row:6',
    'registration/jeevanjyoti_patients.tsv:row:11',
    'registration/jeevanjyoti_patients.tsv:row:27'
}

ds = DisjointSet()
by_phone = defaultdict(list)
by_aadhaar = defaultdict(list)
by_abha = defaultdict(list)
by_mrn = defaultdict(list)
by_name = defaultdict(list)

for rid, clues in all_record_clues.items():
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

for p, rids in by_phone.items():
    for i in range(1, len(rids)):
        ds.union(rids[0], rids[i])
        if any(ds.find(b) == ds.find(rids[0]) for b in bad_rids):
            # check if two bad_rids merged
            found = [b for b in bad_rids if ds.find(b) == ds.find(rids[0])]
            if len(found) > 1:
                print(f"MERGED by phone {p}: {found} with {rids[0]} and {rids[i]}")

for a, rids in by_aadhaar.items():
    for i in range(1, len(rids)):
        ds.union(rids[0], rids[i])
        found = [b for b in bad_rids if ds.find(b) == ds.find(rids[0])]
        if len(found) > 1:
            print(f"MERGED by aadhaar {a}: {found}")

for ab, rids in by_abha.items():
    for i in range(1, len(rids)):
        ds.union(rids[0], rids[i])
        found = [b for b in bad_rids if ds.find(b) == ds.find(rids[0])]
        if len(found) > 1:
            print(f"MERGED by abha {ab}: {found}")

for m, rids in by_mrn.items():
    for i in range(1, len(rids)):
        ds.union(rids[0], rids[i])
        found = [b for b in bad_rids if ds.find(b) == ds.find(rids[0])]
        if len(found) > 1:
            print(f"MERGED by mrn {m}: {found}")

for name, rids in by_name.items():
    tokens = name.split()
    is_full_name = len(tokens) >= 2
    for i in range(len(rids)):
        r1 = rids[i]
        c1 = all_record_clues[r1]
        root1 = ds.find(r1)
        for j in range(i + 1, len(rids)):
            r2 = rids[j]
            c2 = all_record_clues[r2]
            root2 = ds.find(r2)
            if root1 == root2:
                continue
            if c1["phones"] and c2["phones"] and not (c1["phones"] & c2["phones"]):
                continue
            hosp1 = {m.split("-")[0] for m in c1["mrns"] if "-" in m}
            hosp2 = {m.split("-")[0] for m in c2["mrns"] if "-" in m}
            if (hosp1 & hosp2) and not (c1["mrns"] & c2["mrns"]):
                continue
            clean_rel1 = {r for r in c1["relative_names"] if len(r) > 3 and r not in DISEASE_WORDS}
            clean_rel2 = {r for r in c2["relative_names"] if len(r) > 3 and r not in DISEASE_WORDS}
            rel_match = bool(clean_rel1 & clean_rel2)
            if clean_rel1 and clean_rel2 and not rel_match:
                continue
            dob_match = bool(c1["dob"] and c2["dob"] and c1["dob"] == c2["dob"])
            age_match = bool(c1["age"] is not None and c2["age"] is not None and abs(c1["age"] - c2["age"]) <= 1)
            
            merged = False
            if not is_full_name:
                if rel_match or (dob_match and age_match):
                    ds.union(r1, r2)
                    merged = True
            else:
                if rel_match or dob_match or (age_match and (not clean_rel1 or not clean_rel2)):
                    ds.union(r1, r2)
                    merged = True
            if merged:
                found = [b for b in bad_rids if ds.find(b) == ds.find(r1)]
                if len(found) > 1:
                    print(f"MERGED by name '{name}': {r1} and {r2}. Contained bad: {found}")
                    sys.exit(0)
