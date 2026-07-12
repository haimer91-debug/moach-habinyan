# -*- coding: utf-8 -*-
"""
PDF Table-of-Contents Builder for scanned ת"י standards.
Uses Claude Vision to read the first pages of each PDF and extract
section headings + page numbers → stored in _toc_cache.json.

This enables targeted reading: instead of always reading pages 1-3,
we can jump directly to the relevant section.

Run once (takes ~5-10 minutes, costs ~$2-3 in Vision API):
    python -m standards.pdf_toc_builder
"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF

_PROJECT_ROOT = Path(__file__).parent.parent
_STANDARDS_DIR = _PROJECT_ROOT / "תקנים ישראלים"
_TOC_CACHE = Path(__file__).parent / "_toc_cache.json"

# Pages to read for TOC extraction (first 4 pages usually contain TOC)
_TOC_PAGES = [0, 1, 2, 3]
_DPI = 120  # Lower DPI for TOC pages (faster, still readable)


def _page_to_b64(page: fitz.Page, dpi: int = _DPI) -> str:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return base64.standard_b64encode(pix.tobytes("png")).decode("ascii")


def extract_toc_from_pdf(pdf_path: Path, client) -> dict:
    """
    Use Vision to extract table of contents from a scanned PDF.
    Returns: {"sections": [{"title": str, "page": int, "keywords": [str]}], "total_pages": int}
    """
    try:
        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        pages_to_read = [p for p in _TOC_PAGES if p < total_pages]

        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"זהו תקן ישראלי סרוק: {pdf_path.name} ({total_pages} עמודים).\n"
                    "חלץ את תוכן העניינים (TOC): כותרות פרקים, מספרי סעיפים ומספרי עמודים.\n"
                    "ענה ב-JSON בלבד:\n"
                    '{"sections": [{"title": "כותרת", "page": 5, "keywords": ["מילה1", "מילה2"]}]}\n'
                    "אם אין TOC — נסה לחלץ נושאי עמודים שקראת."
                ),
            }
        ]

        for p_num in pages_to_read:
            b64 = _page_to_b64(doc[p_num], dpi=_DPI)
            content.append({"type": "text", "text": f"[עמוד {p_num + 1}]"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
            })
        doc.close()

        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1000,
            messages=[{"role": "user", "content": content}],
        )
        raw = resp.content[0].text.strip()

        # Parse JSON
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            data["total_pages"] = total_pages
            return data

        return {"sections": [], "total_pages": total_pages, "error": "no JSON"}

    except Exception as e:
        return {"sections": [], "total_pages": 0, "error": str(e)}


def build_toc_cache(client, force: bool = False) -> dict:
    """
    Build TOC cache for all ת"י PDFs.
    Skips already-cached PDFs unless force=True.
    Returns the full cache dict.
    """
    # Load existing cache
    cache: dict[str, dict] = {}
    if _TOC_CACHE.exists() and not force:
        try:
            cache = json.loads(_TOC_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    # Find all PDFs
    all_pdfs = list(_STANDARDS_DIR.rglob("*.pdf"))
    print(f"נמצאו {len(all_pdfs)} קבצי PDF")

    new_count = 0
    for i, pdf_path in enumerate(all_pdfs):
        key = str(pdf_path.relative_to(_PROJECT_ROOT))
        if key in cache and not force:
            continue

        print(f"[{i+1}/{len(all_pdfs)}] {pdf_path.name} ...", end=" ", flush=True)
        try:
            toc = extract_toc_from_pdf(pdf_path, client)
            cache[key] = toc
            n_sections = len(toc.get("sections", []))
            print(f"✓ {n_sections} פרקים, {toc.get('total_pages', 0)} עמודים")
            new_count += 1
        except Exception as e:
            print(f"✗ {e}")
            cache[key] = {"sections": [], "error": str(e)}

        # Save every 10 PDFs
        if new_count % 10 == 0:
            _TOC_CACHE.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        time.sleep(0.3)  # Rate limiting

    # Final save
    _TOC_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ נשמר ל-{_TOC_CACHE} — {len(cache)} PDF במטמון")
    return cache


def load_toc_cache() -> dict[str, dict]:
    """Load the TOC cache from disk."""
    if not _TOC_CACHE.exists():
        return {}
    try:
        return json.loads(_TOC_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def find_relevant_pages(pdf_rel_path: str, query: str) -> list[int]:
    """
    Given a PDF path and a query, return the most relevant page numbers.
    Uses the TOC cache to find which pages cover the query topic.
    Falls back to [0,1,2] if no cache entry.
    """
    cache = load_toc_cache()
    toc = cache.get(pdf_rel_path, {})
    sections = toc.get("sections", [])

    if not sections:
        return [0, 1, 2]

    q_lower = query.lower()
    scored: list[tuple[int, int]] = []  # (score, page_num)

    for sec in sections:
        title = sec.get("title", "").lower()
        keywords = [k.lower() for k in sec.get("keywords", [])]
        page = sec.get("page", 1) - 1  # Convert to 0-indexed

        score = 0
        for word in q_lower.split():
            if len(word) > 2:
                if word in title:
                    score += 3
                for kw in keywords:
                    if word in kw:
                        score += 1

        if score > 0 and 0 <= page:
            scored.append((score, page))
            # Also include the next page (content continues)
            scored.append((score - 1, page + 1))

    if not scored:
        return [0, 1, 2, 3]

    scored.sort(key=lambda x: x[0], reverse=True)
    # Deduplicate while preserving order
    seen: set[int] = set()
    pages: list[int] = []
    for _, p in scored:
        if p not in seen:
            seen.add(p)
            pages.append(p)
        if len(pages) >= 5:
            break

    return sorted(pages[:5])


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")

    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-REPLACE"):
        print("❌ חסר ANTHROPIC_API_KEY ב-.env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    print("מתחיל לבנות אינדקס עמודים לכל ת\"י...")
    print("זה ייקח כ-5-10 דקות ויעלה ~$2-3 בAPI")
    print()
    build_toc_cache(client)
