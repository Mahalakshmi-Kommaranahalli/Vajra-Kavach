import json
import base64
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", s).casefold().split())

_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")

def with_b64(text: str) -> str:
    extra = []
    for m in _B64.finditer(text):
        tok = m.group(0)
        try:
            extra.append(base64.b64decode(tok + "=" * (-len(tok) % 4)).decode("utf-8", errors="ignore"))
        except Exception:
            pass
    return text + "\n" + "\n".join(extra) if extra else text

def read_text(p: Path) -> str:
    try:
        raw = p.read_bytes()[: 50 * 1024 * 1024]
    except OSError:
        return ""
    return with_b64(raw.decode("utf-8", errors="replace"))

truth = json.loads(Path("toolkit/dev/truth/truth.json").read_text(encoding="utf-8"))
out = Path("vajra_out")
san = out / "sanitized"
report = json.loads((out / "report.json").read_text(encoding="utf-8"))
renamed = {e.get("input_sha256"): e.get("output") for e in report.get("files") or []}

print("=== ACTUAL LEAKS IN OUTPUT ===")
leaks_by_channel = defaultdict(list)
for rel, f in truth["files"].items():
    out_rel = rel
    declared = renamed.get(f["sha256"])
    if declared:
        out_rel = str(declared).replace("sanitized/", "", 1)
    p = san / out_rel
    exists = p.is_file()
    text = norm(read_text(p)) if exists else ""
    fname = norm(out_rel)

    for loc, u in f["units"].items():
        for e in u["entities"]:
            if e.get("type") == "CANARY":
                continue
            surface = norm(e["surface"])
            hay = fname if e["channel"] == "filename" else text
            hit = bool(surface) and (surface in hay if exists or e["channel"] == "filename" else False)
            if hit:
                leaks_by_channel[e["channel"]].append((e["type"], rel, loc, e["surface"]))

for ch, items in leaks_by_channel.items():
    print(f"\nChannel: {ch} (Total leaked: {len(items)})")
    for it in items[:10]:
        print(" ", it)
