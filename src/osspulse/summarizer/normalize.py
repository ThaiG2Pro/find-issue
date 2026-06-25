"""Input preparation and summary normalization — pure functions, no I/O (AC-4-015..019).

``prepare_input``  — dirty-data guard + truncation (AC-4-017/019).
``normalize_summary`` — strip fences, collapse whitespace, ≤N sentences (AC-4-015/016).
"""

import re

from osspulse.summarizer.errors import SummarizationFailed

# Common abbreviations whose dots must not trigger sentence-splitting (ADR-006).
_ABBREVS = ["e.g.", "i.e.", "etc.", "vs.", "U.S.", "Mr.", "Dr.", "Prof.", "Sr.", "Jr."]

# Placeholder format used during masking (must not appear in any real LLM output).
_MASK = "<<DOT{i}>>"


def prepare_input(title: str, body: str, input_char_cap: int = 8000) -> tuple[str, str]:
    """Return ``(title, body)`` suitable for hashing and sending to the LLM (AC-4-017/019).

    - Guards against missing/None-like fields (EC-006): coerce to ``str`` via ``or ""``.
    - Strips leading/trailing whitespace from both fields.
    - Truncates ``body`` to ``input_char_cap`` characters BEFORE hashing and the LLM call
      so the cache key is stable across runs (AC-4-019).
    - Title is also stripped and capped to avoid a pathological title inflating the prompt.
    """
    t = (title or "").strip()[:input_char_cap]
    b = (body or "").strip()[:input_char_cap]
    return t, b


def normalize_summary(text: str, max_sentences: int = 2, max_chars: int = 600) -> str:
    """Return a clean 1–``max_sentences`` sentence plain-text summary (AC-4-015/016).

    Steps (ADR-006):
    1. Strip leading/trailing whitespace.
    2. Strip surrounding markdown code fences (``` or ```lang) and backtick runs.
    3. Collapse all internal whitespace (including newlines) to single spaces.
    4. Temporarily mask abbreviation dots to avoid over-splitting.
    5. Split on sentence boundaries ``(?<=[.!?])\\s+``; keep first ``max_sentences``.
    6. Unmask abbreviation dots.
    7. Re-join, strip again, clamp to ``max_chars``.
    8. Raise ``SummarizationFailed`` if result is empty/whitespace (EC-012).
    """
    # 1. Strip
    s = text.strip()

    # 2. Strip surrounding code fences (```lang ... ``` or ``` ... ```)
    s = re.sub(r"^```[^\n]*\n?", "", s)
    s = re.sub(r"\n?```$", "", s)
    s = s.strip("`").strip()

    # 3. Collapse internal whitespace / newlines → single space
    s = re.sub(r"\s+", " ", s).strip()

    # 4. Mask abbreviation dots
    for i, abbrev in enumerate(_ABBREVS):
        s = s.replace(abbrev, abbrev.replace(".", _MASK.format(i=i)))

    # 5. Split on sentence boundaries; keep first max_sentences non-empty sentences
    parts = re.split(r"(?<=[.!?])\s+", s)
    kept = [p.strip() for p in parts if p.strip()][:max_sentences]

    # 6. Unmask
    result = " ".join(kept)
    for i, abbrev in enumerate(_ABBREVS):
        result = result.replace(abbrev.replace(".", _MASK.format(i=i)), abbrev)

    # 7. Clamp
    result = result.strip()[:max_chars].strip()

    # 8. Empty → fail (EC-012); never cache an empty summary
    if not result:
        raise SummarizationFailed("LLM returned an empty or whitespace-only summary")

    return result
