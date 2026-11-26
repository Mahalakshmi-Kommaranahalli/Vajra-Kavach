import json
from collections import defaultdict
from pathlib import Path

truth_path = Path("toolkit/dev/truth/truth.json")
truth = json.loads(truth_path.read_text(encoding="utf-8"))

out_path = Path("vajra_out")
recs = defaultdict(dict)
for line in (out_path / "records.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        r = json.loads(line)
        recs[str(r["file"]).replace("sanitized/", "", 1)][r["loc"]] = r.get("patient")

def record_for(loc: str, f_recs: dict):
    if loc in f_recs:
        return f_recs[loc]
    if loc.startswith("/"):
        parts = loc.split("/")
        for i in range(len(parts) - 1, 1, -1):
            anc = "/".join(parts[:i])
            if anc in f_recs:
                return f_recs[anc]
    return f_recs.get("doc")

# Check linking false merges
unit_patient = {}
for rel, f in truth["files"].items():
    for loc, u in f["units"].items():
        if u.get("link") == "required" and u.get("patient"):
            unit_patient[(rel, loc)] = (u["patient"], record_for(loc, recs.get(rel, {})))

units = list(unit_patient.values())
yours = defaultdict(list)
for i, (t, y) in enumerate(units):
    if y:
        yours[y].append(i)

print("--- FALSE MERGES ---")
for y, members in yours.items():
    true_ids = {units[i][0] for i in members}
    if len(true_ids) > 1:
        print(f"Pseudonym {y} merged multiple true patients: {true_ids}")
        for i in members:
            # find original key
            for k, v in unit_patient.items():
                if v == units[i]:
                    print(f"  True {units[i][0]} at {k}")
                    break

print("\n--- CHANNELS WITH LEAKS (base64, metadata, key, header) ---")
for rel, f in truth["files"].items():
    for loc, u in f["units"].items():
        for e in u["entities"]:
            if e["channel"] in ("base64", "metadata", "key", "header"):
                print(f"{e['channel']} | {e['type']} | {rel} | loc:{loc} | {e['surface']}")
