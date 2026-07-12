# -*- coding: utf-8 -*-
"""
מוח הבנייה — Construction Knowledge Assistant
Streamlit web app for field use (mobile-first, Hebrew RTL).
"""
import os
import sys
import threading
from pathlib import Path

import streamlit as st

# ── Path setup ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Page config (MUST be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="מוח הבנייה",
    page_icon="🏗️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Inject RTL + mobile CSS ────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* RTL layout */
body, .stApp, [data-testid="stAppViewContainer"] {
    direction: rtl;
    text-align: right;
    font-family: 'Segoe UI', Arial, sans-serif;
}
[data-testid="stSidebar"] { direction: rtl; }

/* Header */
h1, h2, h3 { text-align: right; }

/* Chat bubbles */
.user-bubble {
    background: #0e4f8f;
    color: #fff;
    border-radius: 18px 18px 4px 18px;
    padding: 10px 16px;
    margin: 4px 0 4px auto;
    max-width: 82%;
    display: inline-block;
    text-align: right;
    float: right;
    clear: both;
}
.bot-bubble {
    background: #f0f2f6;
    color: #1a1a1a;
    border-radius: 18px 18px 18px 4px;
    padding: 10px 16px;
    margin: 4px auto 4px 0;
    max-width: 90%;
    display: inline-block;
    text-align: right;
    float: left;
    clear: both;
    white-space: pre-wrap;
}
@media (prefers-color-scheme: dark) {
    .bot-bubble { background: #1e2533; color: #e0e0e0; }
}
.chat-wrap { overflow: hidden; margin-bottom: 8px; }
.status-badge {
    font-size: 0.75em;
    color: #888;
    text-align: center;
    padding: 2px 0;
}
/* Tab buttons */
div[data-testid="stHorizontalBlock"] button {
    border-radius: 20px;
}
/* Make text areas bigger on mobile */
textarea { font-size: 16px !important; }
input[type="text"] { font-size: 16px !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ── Load .env (local) + Streamlit Secrets (cloud) ─────────────────────────────
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Pull secrets from Streamlit Cloud into env vars when running there
try:
    for _k in ("ANTHROPIC_API_KEY", "SUPERVISOR_NAME", "COMPANY_NAME"):
        if _k in st.secrets and not os.getenv(_k):
            os.environ[_k] = st.secrets[_k]
except Exception:
    pass

# ── Anthropic client (cached) ──────────────────────────────────────────────────
@st.cache_resource
def get_client():
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-REPLACE"):
        return None
    return anthropic.Anthropic(api_key=api_key)


@st.cache_resource
def warm_pdf_index():
    """Pre-load the Blue Book index in background (runs once per session)."""
    def _warm():
        try:
            from standards.pdf_search import _get_index
            _get_index()
        except Exception:
            pass
    t = threading.Thread(target=_warm, daemon=True)
    t.start()
    return True


warm_pdf_index()

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "mode" not in st.session_state:
    st.session_state.mode = "שאלה"

# ── Title ─────────────────────────────────────────────────────────────────────
st.markdown("## 🏗️ מוח הבנייה")
st.caption("עוזר AI לפיקוח בנייה • תקנים • עלויות • שטח")

client = get_client()
if client is None:
    st.error(
        "⚠️ מפתח API לא מוגדר. עדכן ANTHROPIC_API_KEY בקובץ .env ואז הפעל מחדש."
    )

# ── Mode selector ─────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🔍 שאלה מקצועית", use_container_width=True,
                 type="primary" if st.session_state.mode == "שאלה" else "secondary"):
        st.session_state.mode = "שאלה"
        st.rerun()
with col2:
    if st.button("🧮 הערכת עלויות", use_container_width=True,
                 type="primary" if st.session_state.mode == "עלויות" else "secondary"):
        st.session_state.mode = "עלויות"
        st.rerun()
with col3:
    if st.button("📋 דוח ביקורת", use_container_width=True,
                 type="primary" if st.session_state.mode == "דוח" else "secondary"):
        st.session_state.mode = "דוח"
        st.rerun()

st.divider()

# ── Chat history ───────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(
            f'<div class="chat-wrap"><div class="user-bubble">{msg["content"]}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="chat-wrap"><div class="bot-bubble">{msg["content"]}</div></div>',
            unsafe_allow_html=True,
        )

# ── Report helper (must be defined before the send block) ─────────────────────
def _generate_report_text(findings: str, api_client) -> str:
    """Quick structured report from field notes."""
    import datetime
    today = datetime.date.today().strftime("%d/%m/%Y")
    prompt = f"""\
אתה מפקח בנייה — עזור לי לכתוב ממצאי ביקורת.

פרטים שמסרתי:
{findings}

כתוב דוח קצר בעברית בפורמט:

📋 דוח ביקורת — {today}

נושא: [משפט אחד]

ממצאים:
• [ממצא 1]
• [ממצא 2]
• ...

הנחיות לתיקון:
• [הנחיה 1]
• ...

בסיס תקני: [ת"י / פרק מפרט רלוונטי אם ידוע]

סטטוס: ⏳ פתוח לטיפול
"""
    response = api_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── Input area ─────────────────────────────────────────────────────────────────
mode = st.session_state.mode

if mode == "שאלה":
    placeholder = "לדוגמא: מה גובה מעקה מרפסת לפי ת\"י 1142? / מה כיסוי ברזל לחוץ?"
    button_label = "🔍 שאל"
    hint = "השאלה תבוצע מול המפרט הכחול + תקנים ישראליים (ת\"י) סרוקים"
elif mode == "עלויות":
    placeholder = "לדוגמא: מרפסת בטון 3×2 מ׳ קומה שלישית / ריצוף פורצלן 50 מ\"ר"
    button_label = "🧮 חשב"
    hint = "הערכת כמויות ועלויות • אינה מחליפה תכנון מהנדס"
else:  # דוח
    placeholder = "תאר את הממצאים מהביקורת — מה ראית בשטח?"
    button_label = "📋 צור דוח"
    hint = "מלא פרטים ואקים דוח Word"

user_input = st.text_area(
    label="הקלד שאלה / תיאור:",
    placeholder=placeholder,
    height=100,
    key=f"input_{mode}",
    label_visibility="collapsed",
)
st.caption(hint)

send_col, clear_col = st.columns([3, 1])
with send_col:
    send_clicked = st.button(button_label, use_container_width=True, type="primary")
with clear_col:
    if st.button("🗑️ נקה", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ── Process input ──────────────────────────────────────────────────────────────
if send_clicked and user_input.strip():
    if client is None:
        st.error("אין חיבור ל-API. עדכן את המפתח.")
    else:
        question = user_input.strip()
        st.session_state.messages.append({"role": "user", "content": question})

        with st.spinner("חושב... ⏳"):
            try:
                if mode == "שאלה":
                    from agents.standards_qa import answer_question
                    answer = answer_question(question, client, use_vision=True)

                elif mode == "עלויות":
                    from agents.estimator import estimate_work
                    answer = estimate_work(question, client)

                else:  # דוח
                    answer = _generate_report_text(question, client)

            except Exception as e:
                answer = f"⚠️ שגיאה: {e}"

        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()

# ── Standards search sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📚 חיפוש תקן")
    search_term = st.text_input("חפש לפי נושא / מספר ת\"י", key="std_search")
    if search_term:
        from standards.question_router import route_question
        matches = route_question(search_term)
        if matches:
            for name, paths in matches[:5]:
                with st.expander(name):
                    for p in paths:
                        fname = Path(p).name
                        st.caption(f"📄 {fname}")
        else:
            st.info("לא נמצאו תקנים מתאימים")

    st.divider()
    st.markdown("### ℹ️ אודות")
    st.caption(
        "מוח הבנייה — עוזר AI לפיקוח בנייה.\n"
        "מבוסס על:\n"
        "• המפרט הכחול (51 פרקים)\n"
        "• תקנים ישראליים סרוקים (123 PDF)\n"
        "• תקנות תכנון ובנייה\n"
        "• בסיס ידע הנדסי (ת\"י 118/466/1004/2481...)\n"
        "• 18 דומיינים מקצועיים:\n"
        "  מעליות, HVAC, אקוסטיקה, תמ\"א 38,\n"
        "  פינוי-בינוי, שמאות, טופס 4, חוזים,\n"
        "  ביטוח, אלומיניום, הידרולוגיה, נגישות,\n"
        "  עיריות, גיאוטכניקה, תנועה, נוף, תמחור\n"
        "• Claude Vision + Claude Sonnet\n\n"
        "⚠️ לשימוש כעזר מקצועי בלבד.\n"
        "תמיד אמת מול המסמך המקורי."
    )
