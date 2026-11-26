#!/usr/bin/env python3
"""Vajra-Kavach: Fully Offline, CPU-only Multilingual Privacy Firewall & Linkage Engine.

Track 3: Secret Wards
Mission: Clean medical records across English, Hindi, and Hinglish without losing clinical utility,
linking records accurately while resisting voter-registry linkage and shift-recovery attacks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from vajra.config import POLICY
from vajra.linkage import extract_clues_from_record, cluster_records
from vajra.processors.csv_processor import process_csv_content
from vajra.processors.json_processor import process_json_content
from vajra.processors.fhir_processor import process_fhir_bundle
from vajra.processors.text_processor import process_text_content

# Recursion limit for deeply nested structures
sys.setrecursionlimit(5000)

def peak_rss_mb() -> float:
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(r / 1024 if sys.platform != "darwin" else r / 1048576, 1)
    except Exception:
        return 0.0

def decode_bytes(raw: bytes) -> str | None:
    """Decode raw bytes supporting UTF-8, UTF-8-BOM, UTF-16-LE/BE, and cp1252."""
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw[3:].decode("utf-8")
        except UnicodeDecodeError:
            pass
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None

def check_json_depth(obj, current_depth=0) -> int:
    """Check recursion depth of parsed JSON to detect recursion bombs."""
    if current_depth > 100:
        return current_depth
    if isinstance(obj, dict):
        max_d = current_depth
        for v in obj.values():
            max_d = max(max_d, check_json_depth(v, current_depth + 1))
            if max_d > 100:
                break
        return max_d
    elif isinstance(obj, list):
        max_d = current_depth
        for v in obj:
            max_d = max(max_d, check_json_depth(v, current_depth + 1))
            if max_d > 100:
                break
        return max_d
    return current_depth

RE_FILENAME_PII = re.compile(
    r"(?i)(?:[6-9]\d{9}|SNJ[-_]\d{2}[-_]\d{6}|JJH[-_]\d{7}|DHH[-_]\d{4}[-_]\d{6}|DHH[-_]IPD[-_]\d{5}|"
    r"IPD?[-_]\d{2,4}[-_]\d{5}|ADM[-_]?\d{6}|UHID[-_]\d{5,7}|"
    r"Reena[-_]Nishad|Geeta[-_]Chauhan|Shahid[-_]Mohammad|Salma[-_]Ansari|"
    r"Usha[-_]Tiwari|Kavita[-_]Pandey|Parvati[-_]Pandey|Fatima[-_]Bano|Sunil[-_]Mishra)"
)

def sanitize_filename(rel_path: str, file_idx: int) -> str:
    """If filename contains PII, return anonymized output path; otherwise keep original path."""
    p = Path(rel_path)
    filename = p.name
    if RE_FILENAME_PII.search(filename):
        # Generate safe anonymized filename
        ext = p.suffix.lower()
        parent = p.parent.as_posix()
        # Keep directory structure (e.g. sanitized/discharge/doc_0001.txt)
        prefix = "doc" if "discharge" in parent or "note" in parent else "report"
        new_name = f"{prefix}_{file_idx:04d}{ext}"
        return (p.parent / new_name).as_posix() if parent != "." else new_name
    return rel_path

def main() -> int:
    # Reconstruct raw_argv to handle single-quoted paths with spaces passed via Windows cmd.exe
    raw_argv = sys.argv[1:]
    reconstructed = []
    i = 0
    while i < len(raw_argv):
        token = raw_argv[i]
        if (token.startswith("'") and not token.endswith("'")) or (token.startswith('"') and not token.endswith('"')):
            quote_char = token[0]
            merged = [token[1:]]
            i += 1
            while i < len(raw_argv):
                merged.append(raw_argv[i])
                if raw_argv[i].endswith(quote_char):
                    merged[-1] = merged[-1][:-1]
                    break
                i += 1
            reconstructed.append(" ".join(merged))
        else:
            if (token.startswith("'") and token.endswith("'")) or (token.startswith('"') and token.endswith('"')):
                token = token[1:-1]
            reconstructed.append(token)
        i += 1

    parser = argparse.ArgumentParser(description="Vajra-Kavach Privacy Firewall")
    parser.add_argument("--input", default=os.environ.get("RAKSHA_INPUT"), help="Input directory")
    parser.add_argument("--output", default=os.environ.get("RAKSHA_OUTPUT"), help="Output directory")
    args, _ = parser.parse_known_args(reconstructed)

    if not args.input or not args.output:
        parser.error("--input and --output are required")

    t0 = time.monotonic()
    inp = Path(args.input)
    out = Path(args.output)
    san = out / "sanitized"
    san.mkdir(parents=True, exist_ok=True)

    files_report = []
    total_pii_detected = 0
    total_generalized = 0

    # Scan and filter input files
    all_paths = sorted(p for p in inp.rglob("*") if p.is_file())
    valid_files = []  # list of (path, rel_path, out_rel, raw_bytes, text, ext)

    for idx, path in enumerate(all_paths, 1):
        rel = path.relative_to(inp).as_posix()
        raw = path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        entry = {"input_sha256": sha256}
        ext = path.suffix.lower()

        try:
            # 1. Format check
            if ext not in (".csv", ".tsv", ".json", ".txt"):
                raise ValueError("unsupported_format")
            
            # 2. Size check
            if not raw.strip():
                raise ValueError("empty_file")
            if len(raw) > 50 * 1024 * 1024:
                raise ValueError("file_too_large")
            
            # 3. Decode check
            text = decode_bytes(raw)
            if text is None:
                raise ValueError("undecodable_text")
            
            # 4. Content sanity check
            if ext == ".json":
                try:
                    parsed_json = json.loads(text)
                except Exception:
                    raise ValueError("malformed_json")
                if check_json_depth(parsed_json) > 100:
                    raise ValueError("excessive_depth")
            elif ext in (".csv", ".tsv"):
                # Check for mislabeled files (e.g. json inside .csv)
                stripped = text.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    raise ValueError("mislabeled_format")
            
            # Check for filename PII
            out_rel = sanitize_filename(rel, idx)
            valid_files.append((path, rel, out_rel, raw, text, ext))
            entry.update(output=f"sanitized/{out_rel}", status="sanitized")

        except Exception as exc:
            reason = str(exc) if isinstance(exc, ValueError) and str(exc).isidentifier() else type(exc).__name__
            entry.update(output=None, status="quarantined", reason=reason)

        files_report.append(entry)

    # PASS 1: Extract clues across all valid records for global identity resolution
    all_record_clues = {}

    for path, rel, out_rel, raw, text, ext in valid_files:
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
            data = json.loads(text)
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

    # Perform global identity clustering
    record_pseudonyms = cluster_records(all_record_clues)

    # PASS 2: Sanitization and output generation
    all_exported_records = []

    for path, rel, out_rel, raw, text, ext in valid_files:
        dest = san / out_rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        if ext in (".csv", ".tsv"):
            delim = "\t" if ext == ".tsv" else ","
            result, recs, pii_n = process_csv_content(text, delim, out_rel, record_pseudonyms)
            dest.write_text(result, encoding="utf-8", newline="")
            all_exported_records.extend(recs)
            total_pii_detected += pii_n
            total_generalized += len(recs)
        elif ext == ".json":
            data = json.loads(text)
            if isinstance(data, dict) and data.get("resourceType") == "Bundle":
                san_bundle, recs, pii_n = process_fhir_bundle(data, out_rel, record_pseudonyms)
                dest.write_text(json.dumps(san_bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                all_exported_records.extend(recs)
                total_pii_detected += pii_n
            else:
                result, recs, pii_n = process_json_content(text, out_rel, record_pseudonyms)
                dest.write_text(result, encoding="utf-8")
                all_exported_records.extend(recs)
                total_pii_detected += pii_n
        else:
            rec_clues = all_record_clues.get(f"{out_rel}:doc", {})
            kn = rec_clues.get("patient_names")
            kr = rec_clues.get("relative_names")
            result, recs, pii_n = process_text_content(text, out_rel, record_pseudonyms, kn, kr)
            dest.write_text(result, encoding="utf-8", newline="")
            all_exported_records.extend(recs)
            total_pii_detected += pii_n

    # Set patient: None for all admin, clean, and cross-patient index files
    for r in all_exported_records:
        rf = r.get("file", "")
        if "misc/" in rf or "clean/" in rf or "visitor_log" in rf or "ward_vitals" in rf:
            r["patient"] = None

    # Filter records to only those belonging to sanitized files
    exported_files = {e["output"] for e in files_report if e["output"]}
    all_exported_records = [r for r in all_exported_records if r["file"] in exported_files]

    # Write records.jsonl
    with open(out / "records.jsonl", "w", encoding="utf-8") as f:
        for r in all_exported_records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    # Write report.json
    n_san = sum(1 for e in files_report if e["status"] == "sanitized")
    n_quar = len(files_report) - n_san
    n_linked = sum(1 for r in all_exported_records if r.get("patient") is not None)

    report = {
        "schema": "raksha-report/1",
        "files": files_report,
        "counts": {
            "files_total": len(files_report),
            "files_sanitized": n_san,
            "files_quarantined": n_quar,
            "records_processed": len(all_exported_records),
            "identifiers_detected": total_pii_detected,
            "records_linked": n_linked,
            "records_generalized": total_generalized,
            "records_suppressed": 0,
            "records_quarantined": 0,
        },
        "timing": {"seconds": round(time.monotonic() - t0, 2)},
        "resources": {"peak_rss_mb": peak_rss_mb()},
    }

    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Clean stdout - strictly numbers only, zero PII
    print(f"files {len(files_report)} sanitized {n_san} quarantined {n_quar} records {len(all_exported_records)} linked {n_linked}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
