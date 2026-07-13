# -*- coding: utf-8 -*-
"""
מוח הבנייה — Construction Knowledge Assistant
Streamlit web app for field use (mobile-first, Hebrew RTL).
"""
import os
import re
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

# ── Dark theme CSS + RTL ────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base dark theme ── */
html, body, [data-testid="stAppViewContainer"], .stApp {
    background-color: #0d1117 !important;
    color: #c9d1d9 !important;
}
[data-testid="stHeader"] { background-color: #0d1117 !important; }
[data-testid="stSidebar"] {
    background-color: #161b22 !important;
    direction: rtl;
}

/* ── RTL layout ── */
body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stVerticalBlock"] {
    direction: rtl;
    text-align: right;
    font-family: 'Segoe UI', Arial, sans-serif;
}
h1, h2, h3, h4, p, li { text-align: right; direction: rtl; }

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 12px !important;
    margin-bottom: 6px !important;
    direction: rtl !important;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
    direction: rtl;
    text-align: right;
}
/* User message - slightly different shade */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background-color: #1c2128 !important;
    border-color: #388bfd40 !important;
}

/* ── Avatar icons ── */
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"] {
    background-color: #21262d !important;
    border: 1px solid #30363d !important;
}

/* ── Buttons ── */
.stButton button {
    border-radius: 20px !important;
    border: 1px solid #30363d !important;
    background-color: #21262d !important;
    color: #c9d1d9 !important;
}
.stButton button[kind="primary"] {
    background-color: #1f6feb !important;
    border-color: #388bfd !important;
    color: #fff !important;
}
.stButton button:hover {
    border-color: #58a6ff !important;
    color: #58a6ff !important;
}

/* ── Text areas & inputs ── */
textarea, input[type="text"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
    border-radius: 8px !important;
    font-size: 16px !important;
    direction: rtl !important;
}
textarea:focus, input:focus {
    border-color: #388bfd !important;
    box-shadow: 0 0 0 2px #388bfd30 !important;
}

/* ── Chat input at bottom ── */
[data-testid="stChatInput"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 24px !important;
    direction: rtl !important;
}
[data-testid="stChatInput"] textarea {
    border: none !important;
    direction: rtl !important;
}

/* ── Dividers ── */
hr { border-color: #30363d !important; }

/* ── Captions / small text ── */
.stCaption, small, [data-testid="stCaptionContainer"] {
    color: #8b949e !important;
}

/* ── Download button ── */
.stDownloadButton button {
    background-color: #21262d !important;
    border-color: #30363d !important;
    color: #58a6ff !important;
    font-size: 0.8em !important;
    padding: 2px 10px !important;
    border-radius: 6px !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] { color: #58a6ff !important; }

/* ── Selectbox / pills ── */
[data-testid="stSelectbox"] div, [role="listbox"] {
    background-color: #161b22 !important;
    border-color: #30363d !important;
    color: #c9d1d9 !important;
}

/* ── Tabs / segmented control ── */
[data-testid="stTabs"] [data-baseweb="tab"] {
    background-color: #21262d !important;
    color: #8b949e !important;
    border-radius: 8px 8px 0 0 !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background-color: #1f6feb !important;
    color: #fff !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
}

/* Fix markdown inside chat: reduce extra blank space */
[data-testid="stChatMessage"] p { margin-bottom: 0.4em !important; }
[data-testid="stChatMessage"] ul,
[data-testid="stChatMessage"] ol { margin-top: 0.3em !important; }
</style>
""", unsafe_allow_html=True)

# ── Load env + secrets ─────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

try:
    for _k in ("ANTHROPIC_API_KEY", "SUPERVISOR_NAME", "COMPANY_NAME"):
        if _k in st.secrets and not os.getenv(_k):
            os.environ[_k] = st.secrets[_k]
except Exception:
    pass

# ── Anthropic client ───────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-REPLACE"):
        return None
    return anthropic.Anthropic(api_key=api_key)


@st.cache_resource
def warm_pdf_index():
    def _warm():
        try:
            from standards.pdf_search import _get_index
            _get_index()
        except Exception:
            pass
    threading.Thread(target=_warm, daemon=True).start()
    return True


warm_pdf_index()

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "mode" not in st.session_state:
    st.session_state.mode = "שאלה"


def clean_text(text: str) -> str:
    """Remove excessive blank lines from AI responses."""
    text = text.strip()
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def export_conversation() -> str:
    """Build a plain-text export of the full conversation."""
    import datetime
    lines = [f"שיחה עם מוח הבנייה — {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", "=" * 50, ""]
    for msg in st.session_state.messages:
        role = "אני" if msg["role"] == "user" else "מוח הבנייה"
        lines.append(f"[{role}]")
        lines.append(msg["content"])
        lines.append("")
    return "\n".join(lines)

# ── Title ──────────────────────────────────────────────────────────────────────
st.markdown("## 🏗️ מוח הבנייה")
st.caption("עוזר AI לפיקוח בנייה • תקנים • עלויות • שטח")

client = get_client()
if client is None:
    st.error("⚠️ מפתח API לא מוגדר. עדכן ANTHROPIC_API_KEY בקובץ .env ואז הפעל מחדש.")

# ── Mode selector ──────────────────────────────────────────────────────────────
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
for i, msg in enumerate(st.session_state.messages):
    avatar = "👤" if msg["role"] == "user" else "🏗️"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

        if msg["role"] == "assistant":
            # Export buttons per answer
            btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 6])
            with btn_col1:
                st.download_button(
                    "💾 שמור",
                    data=msg["content"].encode("utf-8"),
                    file_name=f"תשובה_{i//2 + 1}.txt",
                    mime="text/plain",
                    key=f"dl_ans_{i}",
                )
            with btn_col2:
                if st.button("📋 העתק", key=f"copy_{i}"):
                    st.toast("✅ הועתק ללוח!")

# ── Export full conversation ───────────────────────────────────────────────────
if st.session_state.messages:
    st.divider()
    export_col1, export_col2, export_col3 = st.columns([3, 3, 4])
    with export_col1:
        st.download_button(
            "📄 ייצא שיחה מלאה",
            data=export_conversation().encode("utf-8"),
            file_name="שיחה_מוח_הבנייה.txt",
            mime="text/plain",
        )
    with export_col2:
        if st.button("🗑️ נקה שיחה"):
            st.session_state.messages = []
            st.rerun()

# ── Report helper ──────────────────────────────────────────────────────────────
def _generate_report_text(findings: str, api_client) -> str:
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

הנחיות לתיקון:
• [הנחיה 1]

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
    # Chat input — always at bottom, like WhatsApp
    if prompt := st.chat_input("שאל שאלה מקצועית... (מעקה, כיסוי, בטון, ת\"י...)"):
        if client is None:
            st.error("אין חיבור ל-API.")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)

            with st.chat_message("assistant", avatar="🏗️"):
                with st.spinner("מחפש ומנתח... ⏳"):
                    try:
                        from agents.standards_qa import answer_question
                        answer = answer_question(prompt, client, use_vision=True)
                        answer = clean_text(answer)
                    except Exception as e:
                        answer = f"⚠️ שגיאה: {e}"
                st.markdown(answer)

                btn_col1, btn_col2, _ = st.columns([2, 2, 6])
                with btn_col1:
                    st.download_button(
                        "💾 שמור",
                        data=answer.encode("utf-8"),
                        file_name="תשובה.txt",
                        mime="text/plain",
                        key="dl_latest",
                    )

            st.session_state.messages.append({"role": "assistant", "content": answer})

else:
    # Text area input for עלויות / דוח
    if mode == "עלויות":
        placeholder = "לדוגמא: מרפסת בטון 3×2 מ׳ קומה שלישית / ריצוף פורצלן 50 מ\"ר"
        button_label = "🧮 חשב עלות"
        hint = "הערכת כמויות ועלויות • אינה מחליפה תכנון מהנדס"
    else:
        placeholder = "תאר את הממצאים מהביקורת — מה ראית בשטח?"
        button_label = "📋 צור דוח"
        hint = "מלא פרטים ואקים דוח מובנה"

    user_input = st.text_area(
        label="הקלד:",
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

    if send_clicked and user_input.strip():
        if client is None:
            st.error("אין חיבור ל-API. עדכן את המפתח.")
        else:
            question = user_input.strip()
            st.session_state.messages.append({"role": "user", "content": question})

            with st.spinner("מעבד... ⏳"):
                try:
                    if mode == "עלויות":
                        from agents.estimator import estimate_work
                        answer = estimate_work(question, client)
                    else:
                        answer = _generate_report_text(question, client)
                    answer = clean_text(answer)
                except Exception as e:
                    answer = f"⚠️ שגיאה: {e}"

            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.rerun()

# ── Sidebar ────────────────────────────────────────────────────────────────────
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
                        st.caption(f"📄 {Path(p).name}")
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
        "• בסיס ידע הנדסי\n"
        "• 18 דומיינים מקצועיים\n"
        "• Claude Vision + Claude Sonnet\n\n"
        "⚠️ לשימוש כעזר מקצועי בלבד.\n"
        "תמיד אמת מול המסמך המקורי."
    )
