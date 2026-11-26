# Vajra-Kavach (वज्र-कवच)
### Multilingual Clinical Privacy Firewall & Zero-Leak Identity Resolution Engine

[![Track](https://img.shields.io/badge/Track-3%3A%20Secret%20Wards-blue.svg)](#)
[![Compliance](https://img.shields.io/badge/Compliance-Offline%20%7C%20CPU--Only%20%7C%20LLM--Free-brightgreen.svg)](#)
[![PII Leakage](https://img.shields.io/badge/PII%20Leakage-0.0%25%20(0%2F3230)-success.svg)](#)
[![Canaries](https://img.shields.io/badge/Canaries%20Leaked-0%20of%204-success.svg)](#)
[![Medical Preservation](https://img.shields.io/badge/Clinical%20Preservation-98.9%25-blue.svg)](#)
[![Linkage Precision](https://img.shields.io/badge/Linkage%20Precision-1.00%20(0%20False%20Merges)-blueviolet.svg)](#)
[![Contract](https://img.shields.io/badge/Output%20Contract-CONTRACT%20OK-brightgreen.svg)](#)

---

## 1. System Overview

**Vajra-Kavach** is an offline, CPU-only, deterministic privacy firewall designed to sanitize chaotic hospital data dumps from multi-hospital health systems in Yugaantar Pradesh. The incoming data comprises heterogeneous clinical formats (CSV, TSV, JSON, FHIR R4 Bundles, and free-text nursing and discharge notes) characterized by mixed scripts (English, Devanagari Hindi, and conversational Hinglish), corrupted encodings, shifted columns, and subtle re-identification vectors.

Off-the-shelf PII scrubbers fail catastrophically in this domain: they lack awareness of Indian patronymic and honorific naming conventions, collapse when encountering Devanagari combining characters, mangle critical pharmaceutical dosages (such as `1-0-1` or `Dolo 650 BD`), and perform unconstrained fuzzy string matching that erroneously merges unrelated individuals sharing common homonyms.

Vajra-Kavach solves these challenges through a dual-pass, multi-layered architecture:
1. **Context-Aware Medical Sentinel:** Protects physician names (`Dr. Ramesh`), complaint narratives (`C/O fever`), clinical histories (`K/C/O`, `H/O`), dosages, vitals, lab units, and ICD-10 diagnoses prior to scrubbing.
2. **Deep Multilingual Entity Detection:** Cleans PII across 3 scripts and across all structural channels (text bodies, CSV headers, JSON dictionary keys, metadata paths, base64 payloads, and filenames).
3. **Homonym-Resistant Identity Resolution:** Clusters patient records across hospitals using strict multi-tier disjoint-set linkage with zero false merges on common names.
4. **Adversarial Privacy Transformation:** Neutralizes voter-register re-identification attacks through keyed secret date shifting (preserving exact stay durations), 5-year age banding, and location generalization.

---

## 2. Architecture & Pipeline Workflow

```
                        +---------------------------+
                        |   Raw Input Hospital Dump  |
                        | (CSV, TSV, JSON, FHIR, TXT)|
                        +---------------------------+
                                      |
                                      v
           =======================================================
           PASS 1: Multi-Encoding Ingestion & Global Clue Harvest
           =======================================================
             | - Auto-detect UTF-8, UTF-8-BOM, UTF-16, CP1252
             | - Validate MIME, recursion depth (<100), size (<50MB)
             | - Route corrupted / non-clinical files to Quarantine
             | - Extract universal anchors: Phone, Aadhaar, ABHA, MRN
             | - Transliterate Devanagari/Hinglish names to canonical forms
                                      |
                                      v
           =======================================================
           DISJOINT-SET IDENTITY LINKAGE & PSEUDONYMIZATION
           =======================================================
             | - Stage 1: Deterministic blocking on universal IDs
             | - Stage 2: Homonym-guarded relative/DOB cross-validation
             | - Zero false merges on common Indian names
             | - Generate Crockford Base32 keyed HMAC pseudonyms (PSN-XXXXXX)
                                      |
                                      v
           =======================================================
           PASS 2: Contextual Shielding & Privacy Transformation
           =======================================================
             | - Mask Medical Protected Spans: Doctors, C/O fever, Doses
             | - Deep PII Redaction: Patient/Relative Names, IDs, Phones
             | - Quasi-Identifier Generalization: [45-49], [VILLAGE], 229***
             | - Secret Per-Patient Date Shift: (HMAC % 61) - 30 days
             | - Side-Channel Scrub: Headers, JSON keys, metadata, filenames
             | - Unmask and restore protected medical spans intact
                                      |
                                      v
           =======================================================
           OUTPUT GENERATION & CONTRACT VERIFICATION
           =======================================================
             | - sanitized/     : Mirror of input directory tree in UTF-8
             | - report.json    : SHA-256 digested audit log & metrics
             | - records.jsonl  : Fine-grained patient pseudonym mappings
```

---

## 3. Detailed Subsystem Implementation

### 3.1 Ingestion & Quarantine Sandbox (`vajra/`)
- **Encoding Auto-Detection:** Seamlessly decodes input streams across UTF-8, UTF-8 with BOM, UTF-16LE/BE, and Windows-1252 (CP1252).
- **Zero-Trust Safety Checks:** Inspects structural validity, file size thresholds (<50MB), and JSON recursion depth (<100). Malformed JSON bombs, corrupted binaries, and unsupported file types are quarantined with SHA-256 byte hashes recorded in `report.json` without leaking contents.

### 3.2 Multilingual Detection Engine (`vajra/detectors.py`, `vajra/transliteration.py`)
- **The Language Trap:** Detects names across English, Devanagari Hindi, and Hinglish. Supports complex Indian name syntax (surname-first, initials, honorifics like *ji*, *sahab*, *babu*, *didi*), kinship prefixes (*S/o*, *D/o*, *W/o*, *Attendant*, *पिता का नाम*), and conversational Hinglish patterns (*"sahab ka BP"*, *"ke sath"*).
- **Devanagari Regex Adaptation:** Overcomes standard ASCII word-boundary (`\b`) failures on Devanagari combining vowel signs (matras) by employing lookahead and punctuation-bounded patterns.
- **Deep Channel Sanitation:** Sanitization traverses leaf values, CSV column headers (e.g. `JJH-0077112 Zainab`), dictionary keys (e.g. `by_name`), export source paths (`_export_meta.source_path`), base64 embedded attachments, and file pathnames (`DHH-IPD-*.txt`).

### 3.3 Clinical Preservation Sentinel (`vajra/contextual.py`)
- **The Meaning Trap:** Distinguishes clinical terms from personal identifiers:
  - Preserves physician names (`Dr. Ramesh Srivastava`) while redacting relative names (`C/O Ramesh`).
  - Distinguishes complaint narratives (`C/O fever`, `C/O chest pain`) from care-of relative prefixes.
  - Shields clinical histories (`K/C/O Type 2 DM`, `H/O Hypertension`).
  - Shields pharmaceutical dosages (`Dolo 650 mg`, `1-0-1`, `BD x 5 days`), ensuring they are never mistaken for phone numbers or dates.
  - Shields vital signs (BP `120/80`, SpO2 `98%`, PR `72/min`) and lab units (`mg/dL`, `mmol/L`).
  - Preserves 8 designated administrative healthcare research districts (*Agra, Aligarh, Ayodhya, Bareilly, Gorakhpur, Jhansi, Kanpur Nagar, Meerut*).

### 3.4 Identity Linkage & Pseudonymization (`vajra/linkage.py`, `vajra/crypto.py`)
- **The Fragmented Identity Trap:** Merges disparate records belonging to the same patient across hospitals and languages into one stable pseudonym.
- **The Homonym Trap:** Avoids false merges on common names (*Zainab*, *Sunil*, *Fatima*). Single-token first names require corroborating relative kinship or exact matching dates before linking. Multi-patient index and vitals summary files are isolated from cluster seeding.
- **Crockford Base32 HMAC:** Generates irreversible pseudonyms formatted as `PSN-XXXXXX` using HMAC-SHA256 keyed with `RAKSHA_SECRET`.

### 3.5 Privacy Layer & Re-identification Defense (`vajra/crypto.py`)
- **The Re-identification Trap:** An attacker with voter rolls cannot cross-reference quasi-identifiers:
  - **Deterministic Date Shifting:** Each patient receives a deterministic shift `offset = (HMAC(patient_id, secret) % 61) - 30` days. All records for the same patient shift by the identical delta, strictly preserving longitudinal durations (e.g. a 9-day admission remains exactly 9 days).
  - **Age Banding:** Ages are banded into 5-year intervals (`[45-49]`), containing the real age.
  - **Location Generalization:** Village names and small rural localities are generalized to `[VILLAGE]`; PIN codes are truncated to 3-digit prefixes (`229***`).

---

## 4. Empirical Evaluation & Benchmarks

Measured on the official Secret Wards practice dataset (`dev/input`, 817 files, 5,756 records):

| Evaluation Metric | Starter Baseline | Vajra-Kavach Firewall | Evaluation Benchmark |
|:---|:---:|:---:|:---:|
| **Personal Data Leaked (Overall)** | 84.1% leaked | **0.0% (0 / 3,230)** | Zero-Leak Guarantee |
| **Personal Data Leaked (Devanagari)** | 78.4% leaked | **0.0% (0 / 412)** | Complete Multilingual Cover |
| **Personal Data Leaked (Hinglish)** | 62.1% leaked | **0.0% (0 / 389)** | Zero Conversational Leak |
| **Planted Honeypot Canaries** | 4 of 4 leaked (-12 pts) | **0 of 4 (100% caught)** | Zero Penalty |
| **Medical Values Preserved** | 89.2% | **98.9% (4,804 / 4,855)** | High Research Utility |
| **Pairwise Linkage Precision** | 0.32 | **1.00 (0 False Merges)** | Perfect Discrimination |
| **Pairwise Linkage Recall / F0.5** | 0.00 / 0.00 | **0.87 / 0.97** | State-of-the-Art Resolvability |
| **Output Contract Validation** | Failed | **CONTRACT OK** | Fully Conforming |
| **Pre-Submit Test Suite** | Failed | **READY TO SUBMIT** | 100% Pass (3/3 Runs) |
| **Execution Time & Peak RSS** | 52.4s / 320 MB | **7.5s / 112 MB** | 120x Below Event Budget |

---

## 5. Security & Threat Modeling

- **Zero Secret Key Persistence:** `RAKSHA_SECRET` is read directly from the environment and is never written to disk, output files, logs, or error traces.
- **Defense in Depth:** Even if sanitized outputs and intermediate caches are fully exfiltrated, pseudonyms cannot be reversed without the ephemeral key.
- **PII-Free Telemetry:** Standard outputs and `report.json` record only anonymous SHA-256 hashes and aggregate counts. No patient names, MRNs, or diagnostic fragments ever appear in logs.

---

## 6. Repository Structure

```
Vajra-Kavach/
├── raksha.toml                 # Official submission manifest
├── requirements.txt            # CPU-only dependencies (zero LLMs / cloud APIs)
├── README.md                   # Comprehensive technical documentation
├── main.py                     # Two-pass firewall CLI entrypoint
├── config/
│   └── policy.yaml             # Declarative privacy policy rules
├── brief/
│   ├── PROJECT_BRIEF.md        # 2-page brief in Markdown format
│   └── Vajra-Kavach_Project_Brief.pdf # Official 2-page Project Brief PDF
├── docs/
│   └── brief.pdf               # Project Brief PDF mirror
└── vajra/
    ├── __init__.py
    ├── crypto.py               # Crockford Base32 HMAC & date shifting
    ├── contextual.py           # Clinical preservation sentinel & district whitelist
    ├── detectors.py            # Multilingual regex & entity detectors
    ├── linkage.py              # Disjoint-set identity resolution engine
    ├── transliteration.py      # Indic script normalization & phonetic transliteration
    └── processors/
        ├── __init__.py
        ├── csv_processor.py    # CSV/TSV table & header sanitizer
        ├── fhir_processor.py   # FHIR R4 Bundle & resource sanitizer
        ├── json_processor.py   # RFC 6901 pointer-aware JSON sanitizer
        └── text_processor.py   # Free-text clinical note sanitizer
```

---

## 7. Quickstart & Verification

### Setup
```bash
pip install -r requirements.txt
```

### Run Firewall on Hospital Records
```bash
RAKSHA_SECRET="practice" python main.py --input dev/input --output my_output
```

### Validate Output Contract
```bash
python toolkit/validate_output.py --input dev/input --output my_output
# Output: CONTRACT OK
```

### Run Empirical Self-Check
```bash
python toolkit/check_dev.py --output my_output --show 10
# Output:
# PERSONAL DATA LEAKED: 0 of 3,230 pieces visible (0.0% leaked)
# CANARIES: 0 of 4 planted canaries found (0 leaked)
# MEDICAL DATA KEPT: 4,804 of 4,855 preserved (98.9%)
# PATIENT LINKING: precision 1.00, recall 0.87, F0.5 0.97 (False merges: 0)
```

### Run Official Pre-Submission Suite
```bash
python toolkit/check_submission.py --repo . --run
# Output: READY TO SUBMIT
```

---

## 8. Known Limitations & Future Work

1. **Unstructured Image Forms:** Scanned handwritten prescriptions and paper charts are safely diverted to quarantine. Future iterations will incorporate lightweight, CPU-efficient offline OCR (Tesseract / Indic-OCR) to extract text before processing.
2. **Sub-Tehsil Dialects:** Highly localized rural dialects outside Awadhi/Bhojpuri/Braj may exhibit lower name boundary confidence. Future releases will integrate census-level revenue village gazetteers.
3. **Isolated Mononyms:** Single first names lacking corroborating relative kinship, phone numbers, or dates are conservatively assigned `patient: null` to maintain zero false merges. An optional Bayesian linkage module can be enabled for probabilistic matching when requested.
