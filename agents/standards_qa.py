# -*- coding: utf-8 -*-
"""
Standards Q&A Agent — מענה מקצועי לשאילתות תקן מהשטח.
שלב 1: מחפש במפרט הכחול (טקסט).
שלב 2: אם לא מצא — קורא ת"י סרוקים דרך Claude Vision.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
from standards.catalog import build_standards_reference
from standards.pdf_search import search_bluebook
from standards.question_router import route_question
from standards.vision_reader import read_standard_for_question
from standards.planning_regs import search_regulations
from standards.engineering_kb import search_engineering_kb
from standards.professional_kb import search_professional_kb

_STANDARDS_REF = build_standards_reference()

_SYSTEM = """\
אתה מהנדס בנייה ישראלי בכיר — שקול פרופסור לקונסטרוקציה ומפרטים מהטכניון.
מפקח שדה שואל אותך שאלה מקצועית ישירות מאתר הבנייה.
ענה בעברית, בדיוק מוחלט, עם מספרים ספציפיים.

מבנה תשובתך — השתמש בכותרות האלה בדיוק:

תשובה:
[תשובה ישירה עם הערך/המספר הספציפי — לא "תלוי", לא "כ-"]

בסיס תקני:
[ת"י מספר + סעיף / פרק מפרט / תקנה — ציטוט מדויק מהחומר שסופק]

לשטח:
[איך בודקים / מודדים / מאשרים — הנחיה פרקטית ספציפית]

כללים מחייבים:
• השתמש בציטוטים ישירים מהחומר שסופק — אל תמציא מספרי סעיפים
• כשיש ערכים מספריים בחומר — ציין אותם במדויק
• אם החומר שסופק אינו מכסה את השאלה — כתוב: "לא נמצא ציטוט ישיר — ידע מקצועי, יש לאמת"
• ענה תמיד בעברית
"""


def answer_question(question: str, client: anthropic.Anthropic, use_vision: bool = True) -> str:
    """Answer a professional construction question with standards citations.

    Returns plain Hebrew text (no Markdown) ready for Telegram / Streamlit.
    use_vision=True: if Blue Book doesn't have enough, query ת"י via Vision API.
    """
    # ── שלב 1: מפרט הכחול (טקסט מהיר) ─────────────────────────────────────────
    pdf_snippets = search_bluebook(question, max_results=3, context_chars=700)

    context_parts: list[str] = []
    if pdf_snippets:
        context_parts.append(pdf_snippets)

    # ── שלב 1b: בסיס ידע הנדסי (ערכים, נוסחאות, טבלאות) ──────────────────────
    eng_snippet = search_engineering_kb(question)
    if eng_snippet:
        context_parts.append("=== בסיס ידע הנדסי (ערכים מאומתים) ===\n" + eng_snippet)

    # ── שלב 1c: תקנות תכנון ובניה ──────────────────────────────────────────────
    regs_snippet = search_regulations(question)
    if regs_snippet:
        context_parts.append("=== תקנות תכנון ובניה ===\n" + regs_snippet)

    # ── שלב 1d: ידע מקצועי רב-תחומי (HVAC, מעליות, אקוסטיקה, תמ"א 38 וכד') ──
    prof_snippet = search_professional_kb(question)
    if prof_snippet:
        context_parts.append("=== ידע מקצועי מורחב ===\n" + prof_snippet)

    context_parts.append('=== קטלוג תקנים ישראליים (ת"י) ===')
    context_parts.append(_STANDARDS_REF)

    # ── שלב 2: ת"י סרוקים דרך Vision (אם יש התאמה) ─────────────────────────────
    vision_text = ""
    if use_vision:
        matched = route_question(question)
        if matched:
            top_name, top_paths = matched[0]
            # Read first 3 pages of the top match (and first page of second match if exists)
            paths_to_read = top_paths[:2]
            if len(matched) > 1:
                _, second_paths = matched[1]
                if second_paths:
                    paths_to_read.append(second_paths[0])

            try:
                vision_text = read_standard_for_question(
                    paths_to_read, question, client, pages_per_doc=3
                )
                context_parts.insert(
                    0,
                    f"=== קריאת תקן ישראלי (Vision) — {top_name} ===\n{vision_text}",
                )
            except Exception as e:
                context_parts.append(f"[Vision reader: {e}]")

    user_msg = (
        f"שאלה מקצועית מהשטח:\n{question}\n\n"
        f"--- חומר עזר (ציטוטים מהמסמכים) ---\n"
        + "\n\n".join(context_parts)
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1400,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    return response.content[0].text.strip()
