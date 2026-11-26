#!/usr/bin/env bash
# ==============================================================================
# Vajra-Kavach: Build Offline Bundle & Wheelhouse (Online Phase)
# Run this on an internet-connected machine before air-gap deployment.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WHEELHOUSE_DIR="${PROJECT_ROOT}/wheelhouse"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"

echo "======================================================================"
echo "🛡️  Vajra-Kavach: Building Offline Dependencies Wheelhouse"
echo "======================================================================"

mkdir -p "${WHEELHOUSE_DIR}"

# Ensure pip is up to date
echo "[1/3] Verifying pip installation..."
python3 -m pip install --upgrade pip setuptools wheel --quiet || true

# Download all binary wheels and source tarballs for offline installation
echo "[2/3] Downloading dependency wheels to ${WHEELHOUSE_DIR}..."
python3 -m pip download \
  --requirement "${REQUIREMENTS_FILE}" \
  --dest "${WHEELHOUSE_DIR}" \
  --prefer-binary

echo "[3/3] Generating wheelhouse inventory checksums..."
if command -v sha256sum &> /dev/null; then
  (cd "${WHEELHOUSE_DIR}" && sha256sum *.whl *.tar.gz 2>/dev/null > SHA256SUMS.txt || true)
elif command -v shasum &> /dev/null; then
  (cd "${WHEELHOUSE_DIR}" && shasum -a 256 *.whl *.tar.gz 2>/dev/null > SHA256SUMS.txt || true)
fi

echo ""
echo "✅ Offline bundle successfully created at: ${WHEELHOUSE_DIR}"
echo "📦 Total packages downloaded: $(ls -1 "${WHEELHOUSE_DIR}"/*.whl "${WHEELHOUSE_DIR}"/*.tar.gz 2>/dev/null | wc -l || echo 0)"
echo "🚀 You can now transfer this repository and wheelhouse to an air-gapped machine."
