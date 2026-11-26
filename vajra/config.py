from __future__ import annotations
import os
from pathlib import Path

def load_policy(path: Path | None = None) -> dict:
    if path is None:
        policy_env = os.environ.get("RAKSHAK_POLICY")
        if policy_env and Path(policy_env).exists():
            path = Path(policy_env)
        else:
            path = Path(__file__).resolve().parent.parent / "config" / "policy.yaml"
    policy = {
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
