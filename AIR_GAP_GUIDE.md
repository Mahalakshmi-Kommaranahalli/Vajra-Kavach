# 🛡️ Vajra-Kavach: Enterprise Air-Gapped & Offline Architecture Guide

This document provides a comprehensive systems and DevOps guide for deploying **Vajra-Kavach** in completely air-gapped, zero-trust, and isolated clinical infrastructure with **zero outbound network access**.

---

## 1. Executive Architecture Summary

| Architectural Layer | Implementation | Air-Gap Guarantee |
| :--- | :--- | :--- |
| **Network Socket Boundary** | `vajra/airgap.py` (`AirGapGuard`) | Low-level monkey-patching of `socket.connect`, `socket.create_connection`, and `urllib.request`. Throws `AirGapViolationError` on any outbound connection. |
| **Configuration Toggle** | `OFFLINE_MODE=true` | Configurable via environment variable or `.env` / `config/policy.yaml`. Default is `true`. |
| **Local Persistence Adapter** | `vajra/storage.py` (`LocalStorageAdapter`) | Pure SQLite3 engine (`data/vajra_records.db`) with WAL mode. Replaces all remote databases, cloud queues, and cloud storage (S3/Firebase/Neon). |
| **Asset Localization** | `./assets/gazetteers/` | Bundles all gazetteers, Indian name transliterations, districts, and drug formularies locally. Zero runtime model/data downloads. |
| **Dependency Wheelhouse** | `./wheelhouse/` | Pinned binary `.whl` and `.tar.gz` packages downloaded during the online build phase. Offline installation uses `pip install --no-index`. |
| **Container Isolation** | `docker-compose.yml` (`network_mode: "none"`) | Disables container networking at the Docker/Linux kernel namespace level. |

---

## 2. Step-by-Step Deployment Lifecycle

### Phase A: Online Preparation (Build Workstation)
Perform these steps on a machine with internet access before deploying to the air-gapped environment:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Mahalakshmi-Kommaranahalli/Vajra-Kavach.git
   cd Vajra-Kavach
   ```

2. **Download all binary wheels to `./wheelhouse/`:**
   * **Linux / macOS:**
     ```bash
     chmod +x scripts/*.sh
     ./scripts/build_offline_bundle.sh
     ```
   * **Windows:**
     ```cmd
     scripts\build_offline_bundle.bat
     ```

3. **Verify Wheelhouse Contents:**
   Ensure the following wheels exist inside `./wheelhouse/`:
   * `cryptography-*.whl`
   * `python_dateutil-*.whl`
   * `six-*.whl`
   * `cffi-*.whl`
   * `pycparser-*.whl`

4. **Optional: Pre-Build Docker Image:**
   ```bash
   docker build -t vajra-kavach:offline-latest .
   docker save -o vajra-kavach-offline.tar vajra-kavach:offline-latest
   ```

---

### Phase B: Media Transfer (USB / Secure Air-Gap Bridge)
Transfer the entire directory or tarball to the air-gapped facility:
* Source code (`vajra/`, `config/`, `main.py`, `raksha.toml`)
* Offline Wheelhouse (`wheelhouse/`)
* Local Gazetteers (`assets/`)
* Scripts (`scripts/`)
* Docker image archive (`vajra-kavach-offline.tar`, if using containers)

---

### Phase C: Offline Installation & Execution (Air-Gapped Host)

#### Option 1: Native Host Execution
1. **Install dependencies strictly from local files:**
   * **Linux / macOS:**
     ```bash
     ./scripts/install_offline.sh
     ```
   * **Windows:**
     ```cmd
     scripts\install_offline.bat
     ```

2. **Execute the pipeline:**
   ```bash
   export OFFLINE_MODE=true
   export RAKSHA_SECRET=practice
   python main.py --input /path/to/hospital_dump --output /path/to/my_output
   ```

3. **Verify Local SQLite Database:**
   Inspect records in the air-gapped database:
   ```bash
   sqlite3 data/vajra_records.db "SELECT psn, records_count, age_band FROM patients LIMIT 5;"
   ```

#### Option 2: Docker Air-Gapped Execution (`network_mode: "none"`)
1. **Load image (if transferred via tarball):**
   ```bash
   docker load -i vajra-kavach-offline.tar
   ```

2. **Run in total network isolation:**
   ```bash
   docker compose up
   ```
   *Note: Because `network_mode: "none"` is configured, the container has NO network interface (except internal loopback). Any outbound network packet is dropped by the kernel.*

---

## 3. Auditing & Zero Outbound Traffic Verification

### 1. Automated Socket Guard Verification
Run the built-in air-gap verification test:
```bash
python scripts/verify_airgap.py
```
This script intentionally attempts an outbound connection to an external DNS/HTTP IP to verify that `AirGapViolationError` is thrown, confirms local SQLite persistence, and executes a dry-run sanitization.

### 2. Network Interface Audit (Linux `tcpdump`)
To mathematically prove zero network traffic during batch processing on Linux:
```bash
# In Terminal 1: Monitor network traffic on all interfaces
sudo tcpdump -i any -n "not port 22 and not arp"

# In Terminal 2: Run the full dataset processing
RAKSHA_SECRET=practice python main.py --input dev/input --output my_output
```
**Result:** 0 packets captured across all non-SSH interfaces.

---

## 4. Troubleshooting & FAQ

* **Q: What happens if a third-party library tries to send telemetry?**
  * `vajra/airgap.py` intercepts `socket.connect`. The connection is terminated immediately before any packet leaves the host, and an `AirGapViolationError` is raised.
* **Q: Does the web studio require internet access?**
  * No. The web studio (`web/index.html` and `dashboard.html`) uses 100% self-contained embedded CSS and native browser Web Speech API. Zero external CDN calls (`cdn.tailwindcss.com` or Google Fonts) are made.
* **Q: How are secret keys managed in air-gapped environments?**
  * `RAKSHA_SECRET` is delivered strictly via process environment variables and is never persisted to disk, logs, or intermediate files.
