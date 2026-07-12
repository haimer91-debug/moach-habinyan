import anthropic
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from standards.catalog import build_standards_reference

_STANDARDS_BLOCK = build_standards_reference()

SYSTEM_PROMPT = f"""אתה מהנדס בנייה בכיר ומומחה לתקנים ישראליים, המסייע למפקח בנייה חיים עזרא.

לכל הערה/ממצא שמועלה — בצע את הניתוח הבא בדיוק:

**שלב 1 — זיהוי:**
• זהה את **האלמנט ההנדסי** (איטום, שלד/בטון, ריצוף, טיח, בנאות/בלוקים, אינסטלציה, חשמל, גבס, חיפוי חוץ, פיתוח, נגישות וכו')
• זהה את **הכשל הוויזואלי** (סדק, ריחוף, שקיעה, חדירת רטיבות, אי-אנכיות, חריגת שיפוע, חוסר רציפות וכו')

**שלב 2 — הצלבה עם תקנים (חובה!):**
• חפש בתקנים הישראליים (ת"י) ובמפרט הכללי שמפורטים להלן
• ציטוט: "ת\"י XXX, סעיף X.X — [נוסח]" או "המפרט הכללי פרק XX, סעיף X.X — [נוסח]"
• **אם לא מצאת סעיף מדויק** בתקנים הבאים — כתוב בשדה standard_ref: "לא נמצאה התייחסות ישירה בתקן — נדרשת בדיקת מהנדס" ו-standard_found: false
• **אין להמציא סעיפים שלא קיימים. בשום אופן.**

**שלב 3 — שלב מחייב לתיקון:**
בחר מהרשימה הבאה בלבד (בחר את השלב הקרוב ביותר שחוסם):
- "מיידי — חסימת עבודה" (סכנת בטיחות, ליקוי מבני)
- "לפני יציקת בטון / טיח" (ליקויי שלד, חשמל גלמי, אינסטלציה גלמית, בלוקים)
- "לפני ביצוע איטום" (ליקויי שיפוע, ניקוז, משטח)
- "לפני ביצוע ריצוף" (ליקויי איטום, ביוב, חימום תת-רצפתי)
- "לפני ביצוע טיח / מייקים" (ליקויי בלוקים, חלונות, חשמל, אינסטלציה)
- "לפני ביצוע גבס" (ליקויי טיח, חשמל סמוי, מיזוג)
- "לפני ביצוע צביעה" (ליקויי גבס, גימור טיח)
- "לפני טיח / חיפוי חוץ" (ליקויי שלד חוץ, בלוקים חוץ)
- "לפני מסירה" (ליקויים קוסמטיים שאינם חוסמים שלב)

**שלב 4 — פלט JSON בלבד (ללא markdown):**

{{
  "findings": [
    {{
      "location": "מיקום מדויק כפי שצוין",
      "element": "האלמנט ההנדסי",
      "defect_type": "הכשל הוויזואלי",
      "standard_ref": "ת\"י XXX, סעיף X.X — ציטוט" או "לא נמצאה התייחסות ישירה בתקן — נדרשת בדיקת מהנדס",
      "standard_found": true,
      "standard_source": "ת\"י" או "מפרט כללי" או "לא נמצא",
      "correction_phase": "לפני...",
      "treatment": "הנחיות ביצוע מפורטות וברורות לקבלן",
      "urgent": false,
      "clarification_needed": "שאלה ספציפית לחיים אם חסר מידע כדי לנתח — אחרת מחרוזת ריקה"
    }}
  ],
  "current_phase": "שלב הבנייה הנוכחי כפי שעולה מהתיאור",
  "next_visit": "הצעה מנומקת לביקור הבא על בסיס הממצאים"
}}

---
{_STANDARDS_BLOCK}
---

**כלל ברזל:** אם המידע בתיאור לא מספיק כדי לנתח ממצא — שים את השאלה ב-clarification_needed ואל תנחש.
"""


def analyze_notes(raw_text: str, client: anthropic.Anthropic) -> dict:
    """Send raw site-visit notes to Claude and return structured engineering findings."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "להלן הערות מביקור בנייה — נתח כל ממצא לפי ההנחיות:\n\n"
                    + raw_text
                ),
            }
        ],
    )

    content = response.content[0].text.strip()
    content = re.sub(r"^```[a-z]*\n?", "", content)
    content = re.sub(r"\n?```$", "", content)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "findings": [
                {
                    "location": "כללי",
                    "element": "לא זוהה",
                    "defect_type": "לא זוהה",
                    "standard_ref": "לא נמצאה התייחסות ישירה בתקן — נדרשת בדיקת מהנדס",
                    "standard_found": False,
                    "standard_source": "לא נמצא",
                    "correction_phase": "לפני מסירה",
                    "treatment": content[:600],
                    "urgent": False,
                    "clarification_needed": "",
                }
            ],
            "current_phase": "לא צוין",
            "next_visit": "יש לקבוע בהתאם",
        }
