# -*- coding: utf-8 -*-
"""
PDF Search Engine — קורא ישירות מקבצי המפרט הכללי האמיתיים.
כל טקסט מהמסמך המקורי, ללא המצאות.
"""

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Optional

try:
    import pdfplumber
    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False

BASE_DIR = Path(__file__).parent.parent
BLUEBOOK_DIR = BASE_DIR / "המפרט הכללי הספר הכחול"
CACHE_FILE   = BASE_DIR / "standards" / "_pdf_index_cache.json"

# ── מיפוי פרקים אמיתיים (מהקבצים עצמם) ───────────────────────────────────────
CHAPTER_MAP = {
    "00": "הוראות כלליות",
    "01": "עבודות עפר",
    "02": "עבודות בטון",
    "03": "מוצרי בטון טרומי",
    "04": "בנאות ועבודות בלוקים",
    "05": "עבודות איטום",
    "06": "ריצוף וחיפוי — חלק א",
    "07": "מתקני תברואה (אינסטלציה)",
    "08": "מתקני חשמל",
    "09": "טיח",
    "10": "ריצוף וחיפוי — חלק ב",
    "11": "מתכת — שונות",
    "12": "אלומיניום וזכוכית",
    "13": "עבודות צביעה",
    "14": "גינות ופיתוח חוץ",
    "15": "מיזוג אוויר",
    "16": "מעלית",
    "17": "מחסומים וחניה",
    "18": "תשתיות תקשורת",
    "19": "שונות",
    "20": "נגרות וסיכוך",
    "21": "אבן טבעית",
    "22": "חיפויי אבן",
    "23": "פיתוח חוץ",
    "26": "עבודות מיוחדות",
    "34": "גילוי וכיבוי אש",
    "35": "בקרת מערכות (BMS)",
    "39": "גנרטור דיזל",
    "40": "שונות מכניות",
    "41": "גינון והשקיה",
    "50": "משטחי בטון",
    "51": "עבודות סלילה",
    "54": "עבודות מנהור",
    "97": "בטיחות בעבודות בנייה",
}


def _fix_rtl(raw: str) -> str:
    """Fix reversed Hebrew words as stored in RTL PDFs."""
    lines = []
    for line in raw.split("\n"):
        words = line.split()
        fixed = " ".join(w[::-1] for w in words)
        lines.append(fixed)
    return "\n".join(lines)


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract all text from a PDF, fixing RTL reversal."""
    if not _HAS_PDFPLUMBER:
        return ""
    try:
        pages_text = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                raw = page.extract_text() or ""
                if raw.strip():
                    pages_text.append(_fix_rtl(raw))
        return "\n\n".join(pages_text)
    except Exception:
        return ""


def _build_index() -> dict:
    """Build search index from all Blue Book PDFs."""
    if not BLUEBOOK_DIR.exists():
        return {}

    index = {}
    pdf_files = sorted(BLUEBOOK_DIR.glob("פרק *.pdf"))

    for pdf_path in pdf_files:
        # Get chapter number from filename
        m = re.search(r"פרק (\d+[\d.]*)", pdf_path.name)
        if not m:
            continue
        ch_num = m.group(1)

        # Skip duplicate "daf tikun" files — keep main file only
        if "דף תיקון" in pdf_path.name:
            continue

        text = _extract_pdf_text(pdf_path)
        if not text.strip():
            continue

        ch_name = CHAPTER_MAP.get(ch_num, f"פרק {ch_num}")
        index[ch_num] = {
            "name": ch_name,
            "file": pdf_path.name,
            "text": text,
        }

    return index


def _load_index() -> dict:
    """Load index from cache or build fresh."""
    # Check if cache exists and is recent enough
    if CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if cached.get("_version") == "2":
                return cached.get("chapters", {})
        except Exception:
            pass

    # Build fresh index
    chapters = _build_index()

    try:
        payload = {"_version": "2", "chapters": chapters}
        CACHE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=None),
            encoding="utf-8"
        )
    except Exception:
        pass

    return chapters


# ── Singleton index ────────────────────────────────────────────────────────────
_INDEX: Optional[dict] = None


def _get_index() -> dict:
    global _INDEX
    if _INDEX is None:
        _INDEX = _load_index()
    return _INDEX


def search_bluebook(query: str, max_results: int = 4, context_chars: int = 600) -> str:
    """
    Search all Blue Book chapters for relevant sections.
    Returns formatted Hebrew text with actual quotes from the documents.
    """
    if not _HAS_PDFPLUMBER:
        return ""

    index = _get_index()
    if not index:
        return ""

    # Build keyword list (Hebrew words 3+ chars)
    keywords = [w for w in re.split(r"\s+|[,./]", query) if len(w) >= 3]
    if not keywords:
        return ""

    results = []

    for ch_num, ch_data in index.items():
        text  = ch_data["text"]
        name  = ch_data["name"]

        # Score: how many keywords appear in this chapter
        score = sum(1 for kw in keywords if kw in text)
        if score == 0:
            continue

        # Find best matching snippet
        best_pos  = -1
        best_score = 0
        for kw in keywords:
            pos = text.find(kw)
            if pos >= 0:
                # Count overlapping keywords around this position
                window = text[max(0, pos-200): pos+400]
                local_score = sum(1 for k in keywords if k in window)
                if local_score > best_score:
                    best_score  = local_score
                    best_pos    = pos

        if best_pos < 0:
            continue

        start   = max(0, best_pos - 150)
        end     = min(len(text), best_pos + context_chars)
        snippet = text[start:end].strip()

        results.append((score, ch_num, name, snippet))

    # Sort by relevance score
    results.sort(key=lambda x: -x[0])

    if not results:
        return ""

    lines = [f"=== ממצאים ממפרט הכללי (ציטוט מהמסמך המקורי) ==="]
    for score, ch_num, name, snippet in results[:max_results]:
        lines.append(f"\n── פרק {ch_num} — {name} ──")
        lines.append(snippet)

    return "\n".join(lines)


def search_specific_chapter(chapter_num: str, query: str, context_chars: int = 800) -> str:
    """Search within a specific chapter. chapter_num e.g. '05', '07'."""
    index = _get_index()
    ch = index.get(chapter_num)
    if not ch:
        return f"פרק {chapter_num} לא נמצא באינדקס."

    text     = ch["text"]
    keywords = [w for w in re.split(r"\s+|[,./]", query) if len(w) >= 3]

    snippets = []
    seen_positions = []

    for kw in keywords:
        pos = 0
        while True:
            idx = text.find(kw, pos)
            if idx < 0:
                break
            # Skip if too close to a previous result
            if any(abs(idx - sp) < 200 for sp in seen_positions):
                pos = idx + 1
                continue
            seen_positions.append(idx)
            start   = max(0, idx - 100)
            end     = min(len(text), idx + context_chars)
            snippets.append(text[start:end].strip())
            pos = idx + 1
            if len(snippets) >= 3:
                break
        if len(snippets) >= 3:
            break

    if not snippets:
        return f"לא נמצאו תוצאות לחיפוש '{query}' בפרק {chapter_num}."

    name = ch.get("name", f"פרק {chapter_num}")
    lines = [f"=== פרק {chapter_num} — {name} (ציטוט מקורי) ==="]
    for s in snippets:
        lines.append(f"\n{s}\n{'─'*40}")
    return "\n".join(lines)


def get_chapter_toc() -> str:
    """Return list of available chapters."""
    index = _get_index()
    lines = ["פרקי המפרט הכללי הזמינים לחיפוש:"]
    for ch_num in sorted(index.keys(), key=lambda x: float(x)):
        lines.append(f"  פרק {ch_num} — {index[ch_num]['name']}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Quick test
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("בונה אינדקס...")
    idx = _get_index()
    print(f"נטענו {len(idx)} פרקים")
    print()
    print("חיפוש: קופינג שיפוע אטב")
    result = search_bluebook("קופינג שיפוע אטב מרפסת")
    print(result[:2000] if result else "לא נמצא")
