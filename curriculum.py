"""
Static curriculum topics from data/curriculum.json (grades 1–12, units, topic strings).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CURRICULUM_PATH = BASE_DIR / "data" / "curriculum.json"

# Internal API subject keys -> subject label in curriculum JSON
SUBJECT_KEY_TO_LABEL = {
    "maths": "Mathematics",
    "science": "Science",
    "english": "ELA",
    "social_studies": "Social Studies",
    "spellings": "ELA",
}

ALLOWED_SUBJECT_KEYS = frozenset(SUBJECT_KEY_TO_LABEL.keys())


@lru_cache(maxsize=1)
def _load_curriculum_file() -> dict:
    path = Path(os.getenv("MENTORBOT_CURRICULUM_PATH", str(DEFAULT_CURRICULUM_PATH)))
    if not path.is_file():
        return {"curriculum": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"curriculum": []}
    except Exception:
        return {"curriculum": []}


def topics_payload_for_grade_subject(grade: int, subject_key: str) -> dict[str, object]:
    """
    Returns { grade, subject, units: [ { title, topics: [ { id, label } ] } ] }.
    """
    g = str(max(1, min(int(grade or 1), 12)))
    sk = str(subject_key or "").strip().lower()
    if sk not in ALLOWED_SUBJECT_KEYS:
        return {"grade": g, "subject": sk, "units": [], "detail": "invalid subject"}

    label = SUBJECT_KEY_TO_LABEL[sk]
    raw = _load_curriculum_file()
    for row in raw.get("curriculum") or []:
        if str(row.get("grade")) != g:
            continue
        for subj in row.get("subjects") or []:
            if str(subj.get("subject")) != label:
                continue
            units_out: list[dict[str, object]] = []
            for ui, unit in enumerate(subj.get("units") or []):
                utitle = str(unit.get("unit") or "").strip()
                tops: list[dict[str, str]] = []
                for ti, topic_label in enumerate(unit.get("topics") or []):
                    tl = str(topic_label or "").strip()
                    if not tl:
                        continue
                    tid = f"g{g}-{sk}-{ui}-{ti}"
                    tops.append({"id": tid, "label": tl})
                if tops:
                    units_out.append({"title": utitle, "topics": tops})
            return {"grade": g, "subject": sk, "units": units_out}

    return {"grade": g, "subject": sk, "units": []}
