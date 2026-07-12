"""
בוט Telegram למפקח בנייה — חיים עזרא הנדסה ניהול ופיקוח
ממשק עברי מלא — כפתורים בתחתית המסך, ללא פקודות אנגליות.
"""

import gc
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agents.estimator import estimate_work
from agents.inspection_report import analyze_notes
from agents.standards_qa import answer_question
from agents.transcriber import transcribe
from templates.report_builder import build_inspection_docx

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
SUPERVISOR   = os.getenv("SUPERVISOR_NAME", "המפקח")
COMPANY      = os.getenv("COMPANY_NAME", "פיקוח בנייה")

TEMP_DIR   = BASE_DIR / "temp_session"
OUTPUT_DIR = BASE_DIR / "פלטים"
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── כפתורי המקלדת הקבועה ────────────────────────────────────────────────────
BTN_PROJECT  = "📋 פרויקט חדש"
BTN_REPORT   = "📄 צור דו\"ח"
BTN_STATUS   = "📊 סטטוס"
BTN_CLEAR    = "🗑️ נקה"
BTN_QUESTION = "🔍 שאל שאלה מקצועית"
BTN_ESTIMATE = "🧮 הערכת כמויות ועלויות"

KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_PROJECT, BTN_REPORT], [BTN_STATUS, BTN_CLEAR],
     [BTN_QUESTION, BTN_ESTIMATE]],
    resize_keyboard=True,
    is_persistent=True,
)

# ── Session ──────────────────────────────────────────────────────────────────
_sessions: dict[int, dict] = {}

def _sess(chat_id: int) -> dict:
    if chat_id not in _sessions:
        _sessions[chat_id] = {
            "project": "",
            "address": "",
            "attendees": "",
            "notes": [],
            "count": 0,
            "waiting_for_project": False,
            "waiting_for_question": False,
            "waiting_for_estimate": False,
        }
    return _sessions[chat_id]


# ── /start ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👷 *שלום חיים!*\n\n"
        "הכפתורים בתחתית המסך:\n\n"
        "📋 *פרויקט חדש* — פתח ביקור\n"
        "📄 *צור דו\"ח* — קבל Word\n"
        "📊 *סטטוס* — מה נקלט עד כה\n"
        "🗑️ *נקה* — התחל מחדש\n"
        "🔍 *שאל שאלה מקצועית* — שאלת תקן מהשטח\n"
        "🧮 *הערכת כמויות ועלויות* — מחיר ראשוני לפי מידות\n\n"
        "בין לבין — שלח 🎙️ הקלטות, 📝 טקסט, 📸 תמונות.",
        parse_mode="Markdown",
        reply_markup=KEYBOARD,
    )


# ── טיפול בכפתורים ובטקסט ────────────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    s    = _sess(update.effective_chat.id)

    # ── כפתור: פרויקט חדש ──────────────────────────────────────────────────
    if text == BTN_PROJECT:
        s["waiting_for_project"] = True
        await update.message.reply_text(
            "📋 מה שם הפרויקט?", reply_markup=KEYBOARD
        )
        return

    # ── כפתור: צור דו"ח ────────────────────────────────────────────────────
    if text == BTN_REPORT:
        await _do_report(update, context)
        return

    # ── כפתור: סטטוס ───────────────────────────────────────────────────────
    if text == BTN_STATUS:
        await _do_status(update, context)
        return

    # ── כפתור: שאל שאלה מקצועית ────────────────────────────────────────────
    if text == BTN_QUESTION:
        s["waiting_for_question"] = True
        s["waiting_for_project"]  = False
        await update.message.reply_text(
            "🔍 *שאלת ייעוץ תקן*\n\n"
            "הקלד את שאלתך המקצועית — אחבור אותה לתקנים האמיתיים:\n\n"
            "_לדוגמה: מה שיפוע מינימלי לריצוף מרפסת?_\n"
            "_לדוגמה: גובה מעקה מינימלי על גג נגיש?_\n"
            "_לדוגמה: עובי כיסוי בטון לברזל בחוץ?_",
            parse_mode="Markdown",
            reply_markup=KEYBOARD,
        )
        return

    # ── כפתור: הערכת כמויות ועלויות ───────────────────────────────────────────
    if text == BTN_ESTIMATE:
        s["waiting_for_estimate"] = True
        s["waiting_for_project"]  = False
        s["waiting_for_question"] = False
        await update.message.reply_text(
            "🧮 *הערכת כמויות ועלויות*\n\n"
            "תאר את העבודה — סוג, מידות, קומה:\n\n"
            "_לדוגמה: מרפסת בטון 3.5×2 מ' קומה 3_\n"
            "_לדוגמה: ריצוף מרפסת 25 מ\"ר, קרמיקה 60×60_\n"
            "_לדוגמה: טיח חוץ על קיר 4×3 מ'_\n"
            "_לדוגמה: לוח בטון 5×3 מ' עובי 20 ס\"מ_",
            parse_mode="Markdown",
            reply_markup=KEYBOARD,
        )
        return

    # ── כפתור: נקה ─────────────────────────────────────────────────────────
    if text == BTN_CLEAR:
        _sessions[update.effective_chat.id] = {
            "project": "", "address": "", "attendees": "",
            "notes": [], "count": 0,
            "waiting_for_project": False,
            "waiting_for_question": False,
            "waiting_for_estimate": False,
        }
        await update.message.reply_text(
            "🗑️ נוקה. לחץ *פרויקט חדש* להתחיל.",
            parse_mode="Markdown",
            reply_markup=KEYBOARD,
        )
        return

    # ── קלט שאלה מקצועית (אחרי לחיצה על "שאל שאלה מקצועית") ────────────────
    if s.get("waiting_for_question"):
        s["waiting_for_question"] = False
        await _do_standards_qa(text, update, context)
        return

    # ── קלט הערכת עלויות (אחרי לחיצה על "הערכת כמויות") ────────────────────
    if s.get("waiting_for_estimate"):
        s["waiting_for_estimate"] = False
        await _do_estimate(text, update, context)
        return

    # ── קלט שם פרויקט (אחרי לחיצה על "פרויקט חדש") ────────────────────────
    if s.get("waiting_for_project"):
        s["project"]             = text
        s["waiting_for_project"] = False
        s["notes"]               = []
        s["count"]               = 0
        await update.message.reply_text(
            f"✅ פרויקט *{text}* פתוח.\nשלח הקלטות, טקסט, או תמונות עם כיתוב.",
            parse_mode="Markdown",
            reply_markup=KEYBOARD,
        )
        return

    # ── הערת טקסט רגילה ────────────────────────────────────────────────────
    if not s["project"]:
        s["waiting_for_project"] = True
        await update.message.reply_text(
            "📋 מה שם הפרויקט?", reply_markup=KEYBOARD
        )
        return

    s["count"] += 1
    s["notes"].append(f"[הערה {s['count']}]: {text}")
    await update.message.reply_text(
        f"📝 הערה #{s['count']} נשמרה.", reply_markup=KEYBOARD
    )


# ── הקלטה קולית ──────────────────────────────────────────────────────────────
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = _sess(update.effective_chat.id)
    if not s["project"]:
        s["waiting_for_project"] = True
        await update.message.reply_text(
            "📋 מה שם הפרויקט? שלח את השם ואחר כך שלח שוב את ההקלטה.",
            reply_markup=KEYBOARD,
        )
        return

    msg = await update.message.reply_text("🎙️ מתמלל...", reply_markup=KEYBOARD)

    voice    = update.message.voice or update.message.audio
    tg_file  = await context.bot.get_file(voice.file_id)
    suffix   = ".ogg" if update.message.voice else (
        Path(getattr(voice, "file_name", "a.ogg") or "a.ogg").suffix or ".ogg"
    )
    tmp_path = TEMP_DIR / f"{update.effective_chat.id}_{voice.file_id}{suffix}"
    await tg_file.download_to_drive(tmp_path)

    text = transcribe(tmp_path.read_bytes(), filename=tmp_path.name)
    tmp_path.unlink(missing_ok=True)

    if text.startswith("("):
        await msg.edit_text(f"⚠️ {text}")
        return

    s["count"] += 1
    s["notes"].append(f"[הקלטה {s['count']}]: {text}")
    await msg.edit_text(
        f"✅ *הקלטה {s['count']} תומללה:*\n_{text}_",
        parse_mode="Markdown",
    )


# ── תמונה ────────────────────────────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio, base64, anthropic as _anthropic

    s = _sess(update.effective_chat.id)
    if not s["project"]:
        s["waiting_for_project"] = True
        await update.message.reply_text(
            "📋 מה שם הפרויקט? שלח את השם ואחר כך שלח שוב את התמונה.",
            reply_markup=KEYBOARD,
        )
        return

    caption = (update.message.caption or "").strip()
    msg = await update.message.reply_text("📸 מנתח תמונה...", reply_markup=KEYBOARD)

    # ── הורד תמונה (הגדולה ביותר) ────────────────────────────────────────────
    photo    = update.message.photo[-1]
    tg_file  = await context.bot.get_file(photo.file_id)
    tmp_path = TEMP_DIR / f"{update.effective_chat.id}_{photo.file_id}.jpg"
    await tg_file.download_to_drive(tmp_path)

    try:
        img_bytes = tmp_path.read_bytes()
        img_b64   = base64.standard_b64encode(img_bytes).decode()
        tmp_path.unlink(missing_ok=True)

        caption_hint = f"\nהערת המפקח: {caption}" if caption else ""

        def _vision_call():
            client = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=600,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": img_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "אתה מפקח בנייה מומחה. בחן את התמונה ותאר בעברית מקצועית:\n"
                                "1. מה מצולם (האלמנט ההנדסי והמיקום)\n"
                                "2. האם יש ליקוי/חריגה/בעיה גלויה — תאר בדיוק\n"
                                "3. אם מצוינות מידות/סימונים/מספרים בתמונה — ציין אותם במפורש\n"
                                "4. הערכה ראשונית: האם נדרשת פעולה מיידית?\n\n"
                                f"{caption_hint}\n\n"
                                "ענה ב-2-4 משפטים תמציתיים ומדויקים."
                            ),
                        },
                    ],
                }],
            )
            return resp.content[0].text.strip()

        vision_text = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _vision_call),
            timeout=30,
        )

        # ── שמור ממצא מנותח ──────────────────────────────────────────────────
        s["count"] += 1
        note = f"[תמונה {s['count']}]: {vision_text}"
        if caption:
            note += f" | הערת מפקח: {caption}"
        s["notes"].append(note)

        await msg.edit_text(
            f"📸 *תמונה {s['count']} נותחה:*\n_{vision_text}_",
            parse_mode="Markdown",
        )

    except asyncio.TimeoutError:
        tmp_path.unlink(missing_ok=True)
        # Fallback: save caption only
        if caption:
            s["count"] += 1
            s["notes"].append(f"[תמונה {s['count']}]: {caption}")
            await msg.edit_text(
                f"📸 *(ניתוח איטי — נשמר כיתוב בלבד #{s['count']}):*\n_{caption}_",
                parse_mode="Markdown",
            )
        else:
            await msg.edit_text(
                "📸 הניתוח לקח יותר מדי. הוסף כיתוב לתמונה ושלח שוב.",
                reply_markup=KEYBOARD,
            )
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        err = str(e)
        if caption:
            s["count"] += 1
            s["notes"].append(f"[תמונה {s['count']}]: {caption}")
            await msg.edit_text(
                f"📸 *כיתוב נשמר (#{s['count']}):*\n_{caption}_",
                parse_mode="Markdown",
            )
        else:
            logger.exception("Photo vision failed")
            await msg.edit_text(
                "📸 לא הצלחתי לנתח. הוסף כיתוב קצר לתמונה ושלח שוב.",
                reply_markup=KEYBOARD,
            )


# ── הערכת כמויות ועלויות (פנימי) ─────────────────────────────────────────────
async def _do_estimate(description: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio
    import anthropic

    msg = await update.message.reply_text(
        "🧮 מחשב כמויות ועלויות...\n_(5-20 שניות)_",
        parse_mode="Markdown",
        reply_markup=KEYBOARD,
    )

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: estimate_work(description, client)
                ),
                timeout=90,
            )
        except asyncio.TimeoutError:
            await _safe_reply(update, msg,
                "⏱️ *הבקשה לקחה יותר מדי זמן.* נסה שוב.")
            return

        reply = (
            f"🧮 הערכת כמויות ועלויות\n"
            f"{'─' * 32}\n"
            f"📝 {description}\n"
            f"{'─' * 32}\n\n"
            f"{result}\n\n"
            f"{'─' * 32}\n"
            f"⚠️ הערכה ראשונית — אינה מחליפה תכנון מהנדס\n"
            f"💬 לחישוב נוסף — לחץ שוב על 🧮"
        )
        await _safe_reply(update, msg, reply, parse_mode=None)

    except Exception as e:
        err = str(e)
        if "credit balance" in err or "billing" in err.lower():
            await _safe_reply(update, msg,
                "💳 *נגמרו הקרדיטים ב-Anthropic*\n\n"
                "גש ל: console.anthropic.com/settings/billing")
        else:
            logger.exception("Estimate failed")
            await _safe_reply(update, msg, f"❌ שגיאה: {err[:300]}", parse_mode=None)


# ── שאילתה מקצועית (פנימי) ───────────────────────────────────────────────────
async def _do_standards_qa(question: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio
    import anthropic

    msg = await update.message.reply_text(
        "🔍 מחפש בתקנים הישראליים...\n"
        "_מפרט כחול + ת\"י סרוקים + תקנות תכנון + 18 דומיינים מקצועיים_\n"
        "_(20-60 שניות)_",
        parse_mode="Markdown",
        reply_markup=KEYBOARD,
    )

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

        try:
            answer = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: answer_question(question, client)
                ),
                timeout=180,
            )
        except asyncio.TimeoutError:
            await _safe_reply(update, msg,
                "⏱️ *הבקשה לקחה יותר מדי זמן.*\n"
                "נסה שוב — בפעם הבאה יהיה מהיר יותר.")
            return

        reply = (
            f"🔍 שאילתה מקצועית\n"
            f"{'─' * 30}\n"
            f"❓ {question}\n"
            f"{'─' * 30}\n\n"
            f"{answer}\n\n"
            f"{'─' * 30}\n"
            f"💬 לשאלה נוספת — לחץ שוב על 🔍"
        )
        await _safe_reply(update, msg, reply, parse_mode=None)

    except Exception as e:
        err = str(e)
        if "credit balance" in err or "billing" in err.lower():
            await _safe_reply(update, msg,
                "💳 *נגמרו הקרדיטים ב-Anthropic*\n\n"
                "גש ל: console.anthropic.com/settings/billing")
        else:
            logger.exception("Standards Q&A failed")
            await _safe_reply(update, msg, f"❌ שגיאה: {err[:300]}", parse_mode=None)


# ── סטטוס (פנימי) ────────────────────────────────────────────────────────────
async def _do_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s       = _sess(update.effective_chat.id)
    project = s["project"] or "לא הוגדר"
    notes   = s["notes"]
    msg     = f"📊 *סטטוס ביקור*\n\nפרויקט: *{project}*\nממצאים: {len(notes)}\n"
    if notes:
        msg += "\n*אחרונים:*\n" + "\n".join(f"• {n}" for n in notes[-4:])
        if len(notes) > 4:
            msg += f"\n_...ועוד {len(notes) - 4}_"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=KEYBOARD)


# ── עוזר: שלח הודעה בטוחה (edit אם אפשר, אחרת reply) ─────────────────────────
async def _safe_reply(update, msg, text, parse_mode="Markdown"):
    kwargs = {} if parse_mode is None else {"parse_mode": parse_mode}
    try:
        await msg.edit_text(text, **kwargs)
    except Exception:
        await update.message.reply_text(text, reply_markup=KEYBOARD, **kwargs)


# ── יצירת דו"ח (פנימי) ───────────────────────────────────────────────────────
async def _do_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio
    import anthropic

    s       = _sess(update.effective_chat.id)
    project = s.get("project", "")
    notes   = s.get("notes", [])

    if not project:
        s["waiting_for_project"] = True
        await update.message.reply_text("📋 מה שם הפרויקט?", reply_markup=KEYBOARD)
        return
    if not notes:
        await update.message.reply_text(
            "⚠️ אין ממצאים. שלח הקלטות, טקסט, או תמונות קודם.",
            reply_markup=KEYBOARD,
        )
        return

    msg = await update.message.reply_text(
        f"⏳ מנתח {len(notes)} ממצאים מול תקנים ישראליים...\n_(כ-60 שניות)_",
        parse_mode="Markdown",
        reply_markup=KEYBOARD,
    )

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        raw    = "\n".join(notes)

        # הרץ את קריאת Claude בthread נפרד עם timeout של 90 שניות
        try:
            structured = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: analyze_notes(raw, client)
                ),
                timeout=90,
            )
        except asyncio.TimeoutError:
            await _safe_reply(update, msg,
                "⏱️ *הבקשה לקחה יותר מדי זמן.*\n"
                "נסה שוב עם פחות ממצאים, או בדוק את חיבור האינטרנט.")
            return

        findings   = structured.get("findings", [])
        report_num = str(len(list(OUTPUT_DIR.glob(f"*{project[:10]}*"))) + 1).zfill(3)

        # בנה Word בthread נפרד
        doc_data = {
            "project_name":    project,
            "address":         s.get("address", ""),
            "date":            date.today().strftime("%d/%m/%Y"),
            "time":            datetime.now().strftime("%H:%M"),
            "report_number":   report_num,
            "supervisor_name": SUPERVISOR,
            "company_name":    COMPANY,
            "attendees":       s.get("attendees", ""),
            "current_phase":   structured.get("current_phase", ""),
            "findings":        findings,
            "next_visit":      structured.get("next_visit", ""),
        }
        docx_bytes = await asyncio.get_event_loop().run_in_executor(
            None, lambda: build_inspection_docx(doc_data)
        )

        filename = f"דוח_ביקור_{project}_{date.today().strftime('%Y%m%d')}.docx"
        (OUTPUT_DIR / filename).write_bytes(docx_bytes)

        urgent  = sum(1 for f in findings if f.get("urgent"))
        no_std  = sum(1 for f in findings if not f.get("standard_found", True))
        q_count = sum(1 for f in findings if f.get("clarification_needed", "").strip())

        summary = f"✅ *דו\"ח מוכן — {project}*\n\n📋 {len(findings)} ממצאים\n"
        if urgent:  summary += f"🔴 {urgent} ממצאים דחופים\n"
        if no_std:  summary += f"🟡 {no_std} ללא ציטוט תקן מדויק\n"
        if q_count: summary += f"❓ {q_count} שאלות לבדיקה\n"

        await _safe_reply(update, msg, summary)

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=docx_bytes,
            filename=filename,
            caption=f"📄 {filename}",
        )

        s["notes"] = []
        s["count"] = 0
        await update.message.reply_text("🗑️ מוכן לביקור הבא!", reply_markup=KEYBOARD)

    except Exception as e:
        err = str(e)
        if "credit balance" in err or "billing" in err.lower() or "overloaded" in err.lower():
            await _safe_reply(update, msg,
                "💳 *נגמרו הקרדיטים ב-Anthropic*\n\n"
                "גש ל: console.anthropic.com/settings/billing\n"
                "לחץ *Add credits* ← $10\n"
                "ואז לחץ שוב 📄 *צור דו\"ח*")
        else:
            logger.exception("Report generation failed")
            await _safe_reply(update, msg, f"❌ שגיאה: {err[:300]}")


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    if not TOKEN or TOKEN.startswith("הכנס"):
        print("שגיאה: חסר TELEGRAM_BOT_TOKEN בקובץ .env")
        sys.exit(1)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    # שמור תמיכה בפקודות ישנות
    app.add_handler(CommandHandler("report",    lambda u, c: _do_report(u, c)))
    app.add_handler(CommandHandler("status",    lambda u, c: _do_status(u, c)))
    app.add_handler(CommandHandler("clear",     lambda u, c: (
        _sessions.update({u.effective_chat.id: {
            "project":"","address":"","attendees":"","notes":[],"count":0,
            "waiting_for_project":False,"waiting_for_question":False,
            "waiting_for_estimate":False,
        }}) or u.message.reply_text("🗑️ נוקה.", reply_markup=KEYBOARD)
    )))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO,                  handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # טען אינדקס PDF ברקע כדי שהשאלה הראשונה תענה מהר
    import threading
    def _warm_pdf_index():
        try:
            from standards.pdf_search import _get_index
            idx = _get_index()
            print(f"  PDF index: {len(idx)} פרקים טעונים")
        except Exception as e:
            print(f"  PDF index warning: {e}")
    threading.Thread(target=_warm_pdf_index, daemon=True).start()

    print("=" * 45)
    print("  בוט פיקוח בנייה — חיים עזרא")
    print("  פועל... Ctrl+C לעצירה")
    print("=" * 45)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
