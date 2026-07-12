# -*- coding: utf-8 -*-
"""
Vision-based reader for scanned Israeli Standards (ת"י) PDFs.
Uses PyMuPDF to render pages as images → Claude Vision API to extract content.
All ת"י PDFs are scanned images with zero extractable text.
"""
import base64
import io
import sys
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).parent.parent))

_PROJECT_ROOT = Path(__file__).parent.parent
_STANDARDS_DIR = _PROJECT_ROOT / "תקנים ישראלים"

# ── Resolution settings ────────────────────────────────────────────────────────
# 150 DPI is enough for Claude Vision to read Hebrew text clearly; 200 for dense tables.
_DPI_NORMAL = 150
_DPI_HIGH = 200
_MAX_PAGES_PER_QUERY = 5  # cost guard: ~$0.05–0.08 per call


def _page_to_base64(page: fitz.Page, dpi: int = _DPI_NORMAL) -> str:
    """Render a PDF page to a base64-encoded PNG for Claude Vision."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img_bytes = pix.tobytes("png")
    return base64.standard_b64encode(img_bytes).decode("ascii")


def read_pdf_pages(
    pdf_path: str | Path,
    page_nums: list[int] | None = None,
    question: str = "",
    client=None,
    dpi: int = _DPI_NORMAL,
) -> str:
    """
    Extract content from specific pages (or first N pages) of a scanned ת"י PDF
    using Claude Vision.

    Args:
        pdf_path:  Absolute or project-relative path to the PDF.
        page_nums: 0-indexed page numbers to read. None = pages 0 .. _MAX_PAGES_PER_QUERY-1.
        question:  The user's question — guides Vision to focus on relevant content.
        client:    anthropic.Anthropic() instance.
        dpi:       Render resolution.

    Returns:
        Extracted text / structured content (Hebrew, from Claude Vision).
    """
    if client is None:
        raise ValueError("anthropic client is required")

    pdf_path = Path(pdf_path)
    if not pdf_path.is_absolute():
        pdf_path = _PROJECT_ROOT / pdf_path
    if not pdf_path.exists():
        return f"[שגיאה: קובץ לא נמצא — {pdf_path.name}]"

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        return f"[שגיאה בפתיחת PDF: {e}]"

    total_pages = len(doc)
    if page_nums is None:
        page_nums = list(range(min(_MAX_PAGES_PER_QUERY, total_pages)))
    else:
        page_nums = [p for p in page_nums if 0 <= p < total_pages][:_MAX_PAGES_PER_QUERY]

    if not page_nums:
        return "[אין עמודים בטווח המבוקש]"

    # Build multimodal message
    content: list[dict] = []

    if question:
        content.append({
            "type": "text",
            "text": (
                f"אתה קורא תקן ישראלי (ת\"י) סרוק — הקובץ: {pdf_path.name}\n"
                f"השאלה של המפקח: {question}\n\n"
                f"חלץ את המידע הרלוונטי לשאלה. "
                f"הכלל את מספרי הסעיפים/טבלאות המדויקים. "
                f"אם אין תשובה ישירה, ציין זאת."
            ),
        })
    else:
        content.append({
            "type": "text",
            "text": (
                f"קרא וחלץ את תוכן התקן הישראלי הסרוק — {pdf_path.name}.\n"
                f"חלץ: כותרות, מספרי סעיפים, טבלאות, ערכים מספריים, דרישות."
            ),
        })

    for p_num in page_nums:
        page = doc[p_num]
        b64 = _page_to_base64(page, dpi=dpi)
        content.append({
            "type": "text",
            "text": f"[עמוד {p_num + 1} מתוך {total_pages}]",
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64,
            },
        })

    doc.close()

    response = client.messages.create(
        model="claude-opus-4-8",  # best Vision accuracy for Hebrew scans
        max_tokens=2000,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text.strip()


def read_standard_for_question(
    pdf_paths: list[str | Path],
    question: str,
    client,
    pages_per_doc: int = 4,
) -> str:
    """
    Read one or more ת"י PDFs (first N pages each) and answer the question.

    Args:
        pdf_paths:      List of PDF paths to read (1–3 recommended).
        question:       User's question in Hebrew.
        client:         anthropic.Anthropic instance.
        pages_per_doc:  How many pages to read per document.

    Returns:
        Synthesized answer with document citations.
    """
    if not pdf_paths:
        return "[לא נמצאו קבצי תקן רלוונטיים לשאלה]"

    # Use TOC cache for targeted page selection when available
    try:
        from standards.pdf_toc_builder import find_relevant_pages, load_toc_cache
        _toc_available = bool(load_toc_cache())
    except Exception:
        _toc_available = False

    doc_texts = []
    for pdf_path in pdf_paths[:3]:
        path = Path(pdf_path)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        name = path.name
        rel_key = str(path.relative_to(_PROJECT_ROOT))

        if _toc_available:
            page_nums = find_relevant_pages(rel_key, question)
        else:
            page_nums = list(range(pages_per_doc))

        text = read_pdf_pages(path, page_nums=page_nums, question=question, client=client)
        doc_texts.append(f"=== {name} (עמ' {[p+1 for p in page_nums]}) ===\n{text}")

    combined = "\n\n".join(doc_texts)

    synthesis_prompt = f"""\
אתה מהנדס בנייה ישראלי בכיר. קראת את החומר הבא מתוך תקנים ישראליים.

שאלת המפקח: {question}

חומר מהתקנים:
{combined}

ענה בפורמט:

תשובה:
[תשובה ישירה, ברורה, 2-3 משפטים]

בסיס תקני:
[ציין ת"י מספר + מספר סעיף/טבלה ספציפי — ישירות מהחומר שלמעלה]

לשטח:
[הערה מעשית — איך בודקים / מאשרים בפועל]

⚠️ אם לא מצאת תשובה ישירה בחומר — כתוב בדיוק: "לא נמצא ציטוט ישיר — המלצה מקצועית, יש לאמת"
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": synthesis_prompt}],
    )
    return response.content[0].text.strip()
