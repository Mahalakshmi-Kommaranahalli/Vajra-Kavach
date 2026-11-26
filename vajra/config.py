from __future__ import annotations
import os
from pathlib import Path
from vajra.airgap import is_offline_mode, enforce_airgap

def load_dotenv(env_path: Path | None = None) -> None:
    """Load key-value pairs from a .env file into os.environ if not already set (pure stdlib)."""
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass

# Automatically load .env if present
load_dotenv()

# Enforce strict offline airgap
OFFLINE_MODE = is_offline_mode()
if OFFLINE_MODE:
    enforce_airgap(strict=True, allow_loopback=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"

def load_policy(path: Path | None = None) -> dict:
    if path is None:
        policy_env = os.environ.get("RAKSHAK_POLICY")
        if policy_env and Path(policy_env).exists():
            path = Path(policy_env)
        else:
            path = ROOT_DIR / "config" / "policy.yaml"
    policy = {
        "offline_mode": 1 if OFFLINE_MODE else 0,
        "date_shift_max_days": 180,
        "age_band_years": 5,
        "generalize_pin": 1,
        "pin_prefix_digits": 3,
        "generalize_village": 1,
        "preserve_districts": 1,
        "suppress_high_risk": 1,
        "rare_age_threshold": 85,
        "pseudonym_prefix": "PSN",
        "quarantine_unsupported": 1,
        "max_file_size_mb": 50,
        "max_json_depth": 100,
        "database_adapter": "sqlite",
        "sqlite_path": str(ROOT_DIR / "data" / "vajra_records.db"),
        "assets_dir": str(ASSETS_DIR),
        "wheelhouse_dir": str(ROOT_DIR / "wheelhouse"),
    }
    if path and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" in line:
                k, v = (x.strip() for x in line.split(":", 1))
                v_clean = v.strip('"').strip("'")
                if v_clean.lstrip("-").isdigit():
                    policy[k] = int(v_clean)
                elif v_clean.lower() in ("true", "yes"):
                    policy[k] = 1
                elif v_clean.lower() in ("false", "no"):
                    policy[k] = 0
                else:
                    policy[k] = v_clean
    return policy

POLICY = load_policy()
