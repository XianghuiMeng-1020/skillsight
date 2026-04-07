from __future__ import annotations

from typing import Dict


DEFAULT_BLOOM_RUBRIC: Dict[str, Dict[str, str]] = {
    "0": {
        "label": "novice",
        "descriptor": "Mostly remember/understand signals; little proof of application.",
    },
    "1": {
        "label": "developing",
        "descriptor": "Can explain concepts and occasionally apply them in constrained tasks.",
    },
    "2": {
        "label": "proficient",
        "descriptor": "Frequently applies and analyzes in realistic scenarios with coherent evidence.",
    },
    "3": {
        "label": "advanced",
        "descriptor": "Evaluates trade-offs and creates robust solutions with strong evidence.",
    },
}
