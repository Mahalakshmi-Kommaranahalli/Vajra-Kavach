from __future__ import annotations
from vajra.crypto import date_shift_days
from vajra.detectors import sanitize_text

def process_text_content(
    text: str,
    file_rel: str,
    record_pseudonyms: dict[str, str | None],
    known_names: set[str] | None = None,
    known_relatives: set[str] | None = None,
) -> tuple[str, list[dict], int]:
    """Sanitize free text notes, prescriptions, and discharge summaries, embedding pseudonyms consistently."""
    loc = "doc"
    rec_id = f"{file_rel}:{loc}"
    is_admin = file_rel.startswith(("misc/", "clean/")) or "visitor_log" in file_rel
    pid = None if is_admin else record_pseudonyms.get(rec_id)
    shift = date_shift_days(pid if pid else rec_id)

    cleaned_text, pii_count = sanitize_text(text, pid, shift, known_names=known_names, known_relatives=known_relatives)

    # Ensure pseudonym is consistently present inside the exported document
    if pid and pid not in cleaned_text:
        cleaned_text = f"Patient: [{pid}]\n" + cleaned_text

    records = [{
        "file": f"sanitized/{file_rel}",
        "loc": loc,
        "patient": pid,
    }]
    return cleaned_text, records, pii_count
