#!/usr/bin/env bash
# ==============================================================================
# Vajra-Kavach: Install Offline Dependencies (Air-Gapped Phase)
# Run strictly WITHOUT internet access on the target machine.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WHEELHOUSE_DIR="${PROJECT_ROOT}/wheelhouse"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"

echo "======================================================================"
echo "🛡️  Vajra-Kavach: Installing From Local Wheelhouse (100% Offline)"
echo "======================================================================"

if [ ! -d "${WHEELHOUSE_DIR}" ]; then
  echo "❌ Error: Wheelhouse directory not found at ${WHEELHOUSE_DIR}."
  echo "Please run scripts/build_offline_bundle.sh on an online host first."
  exit 1
fi

echo "[1/2] Installing dependencies with --no-index..."
python3 -m pip install \
  --no-index \
  --find-links="${WHEELHOUSE_DIR}" \
  --requirement "${REQUIREMENTS_FILE}"

echo "[2/2] Verifying offline import integrity..."
python3 -c "
import os
os.environ['OFFLINE_MODE'] = 'true'
from vajra.airgap import enforce_airgap
enforce_airgap()
import cryptography
import dateutil
from vajra.storage import get_storage
db = get_storage()
print('✓ Local storage adapter initialized:', db.get_summary_stats()['database_engine'])
print('✓ Cryptography version:', cryptography.__version__)
print('✓ Offline imports verified successfully!')
"

echo ""
echo "✅ Air-gapped installation complete. System is ready to run offline!"
echo "Run pipeline: OFFLINE_MODE=true RAKSHA_SECRET=practice python3 main.py --input <input_dir> --output <output_dir>"
