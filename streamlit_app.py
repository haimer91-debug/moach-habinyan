# -*- coding: utf-8 -*-
"""
מוח הבנייה — Construction Knowledge Assistant
Streamlit web app for field use (mobile-first, Hebrew RTL).
"""
import os
import re
import sys
import json
import uuid
import threading
import datetime
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
    initial_sidebar_state="auto",
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

/* Sidebar conversation buttons */
[data-testid="stSidebar"] .stButton button {
    text-align: right !important;
    direction: rtl !important;
    font-size: 0.85em !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}
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

# ── Constants ──────────────────────────────────────────────────────────────────
MODE_EMOJI = {"שאלה": "🔍", "עלויות": "🧮", "דוח": "📋"}
CONVERSATIONS_FILE = PROJECT_ROOT / "data" / "conversations.json"

# ── Session state ──────────────────────────────────────────────────────────────
if "mode" not in st.session_state:
    st.session_state.mode = "שאלה"
# Each mode has its own isolated message list
if "mode_messages" not in st.session_state:
    st.session_state.mode_messages = {"שאלה": [], "עלויות": [], "דוח": []}
# Each mode tracks which saved conversation is currently loaded
if "mode_active_id" not in st.session_state:
    st.session_state.mode_active_id = {"שאלה": None, "עלויות": None, "דוח": None}


# ── Persistence helpers ─────────────────────────────────────────────────────────
def load_all_conversations():
    if CONVERSATIONS_FILE.exists():
        try:
            with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_all_conversations(convos):
    CONVERSATIONS_FILE.parent.mkdir(exist_ok=True)
    try:
        with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(convos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def auto_save_current():
    """Save or update the current mode's conversation to disk."""
    mode = st.session_state.mode
    messages = st.session_state.mode_messages.get(mode, [])
    if not messages:
        return

    convos = load_all_conversations()
    convo_id = st.session_state.mode_active_id.get(mode)

    first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
    title = (first_user[:45] + "...") if len(first_user) > 45 else first_user
    now = datetime.datetime.now().isoformat()

    if convo_id:
        for c in convos:
            if c["id"] == convo_id:
                c["messages"] = messages
                c["updated_at"] = now
                c["title"] = title
                save_all_conversations(convos)
                return
        # ID not in file anymore — fall through to create new
        convo_id = None

    # New conversation
    convo_id = str(uuid.uuid4())
    st.session_state.mode_active_id[mode] = convo_id
    convos.insert(0, {
        "id": convo_id,
        "title": title,
        "mode": mode,
        "messages": messages,
        "created_at": now,
        "updated_at": now,
    })
    save_all_conversations(convos)


# ── Utility ────────────────────────────────────────────────────────────────────
def clean_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def export_conversation(mode: str) -> str:
    messages = st.session_state.mode_messages.get(mode, [])
    ts = datetime.datetime.now().strftime('%d/%m/%Y %H:%M')
    lines = [f"שיחה עם מוח הבנייה — {ts}", "=" * 50, ""]
    for msg in messages:
        role = "אני" if msg["role"] == "user" else "מוח הבנייה"
        lines.append(f"[{role}]")
        lines.append(msg["content"])
        lines.append("")
    return "\n".join(lines)


def _generate_report_text(findings: str, api_client) -> str:
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


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    current_mode = st.session_state.mode

    if st.button("➕ שיחה חדשה", use_container_width=True, type="primary"):
        st.session_state.mode_messages[current_mode] = []
        st.session_state.mode_active_id[current_mode] = None
        st.rerun()

    st.markdown("---")
    st.markdown("### 💬 שיחות שמורות")

    convos = load_all_conversations()
    if not convos:
        st.caption("אין שיחות שמורות עדיין")
    else:
        for c in convos:
            em = MODE_EMOJI.get(c.get("mode", ""), "💬")
            cmode = c.get("mode", "שאלה")
            is_active = (c["id"] == st.session_state.mode_active_id.get(cmode))
            date_str = c.get("updated_at", "")[:10]

            col_btn, col_del = st.columns([5, 1])
            with col_btn:
                label = f"{em} {c['title']}"
                if st.button(
                    label,
                    key=f"load_{c['id']}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                    help=f"{cmode} • {date_str}",
                ):
                    st.session_state.mode = cmode
                    st.session_state.mode_messages[cmode] = list(c["messages"])
                    st.session_state.mode_active_id[cmode] = c["id"]
                    st.rerun()
            with col_del:
                if st.button("✕", key=f"del_{c['id']}", help="מחק שיחה"):
                    new_convos = [x for x in convos if x["id"] != c["id"]]
                    save_all_conversations(new_convos)
                    if st.session_state.mode_active_id.get(cmode) == c["id"]:
                        st.session_state.mode_messages[cmode] = []
                        st.session_state.mode_active_id[cmode] = None
                    st.rerun()

    st.markdown("---")
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

    st.markdown("---")
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


# ── Main area ──────────────────────────────────────────────────────────────────
client = get_client()

st.markdown("## 🏗️ מוח הבנייה")
st.caption("עוזר AI לפיקוח בנייה • תקנים • עלויות • שטח")

if client is None:
    st.error("⚠️ מפתח API לא מוגדר. עדכן ANTHROPIC_API_KEY בקובץ .env ואז הפעל מחדש.")

# ── Mode selector ──────────────────────────────────────────────────────────────
mode = st.session_state.mode
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🔍 שאלה מקצועית", use_container_width=True,
                 type="primary" if mode == "שאלה" else "secondary",
                 key="btn_shela"):
        if mode != "שאלה":
            st.session_state.mode = "שאלה"
            st.rerun()
with col2:
    if st.button("🧮 הערכת עלויות", use_container_width=True,
                 type="primary" if mode == "עלויות" else "secondary",
                 key="btn_uluyot"):
        if mode != "עלויות":
            st.session_state.mode = "עלויות"
            st.rerun()
with col3:
    if st.button("📋 דוח ביקורת", use_container_width=True,
                 type="primary" if mode == "דוח" else "secondary",
                 key="btn_doc"):
        if mode != "דוח":
            st.session_state.mode = "דוח"
            st.rerun()

st.divider()

# Isolated message list for this mode only
messages = st.session_state.mode_messages[mode]

# ── Chat history ───────────────────────────────────────────────────────────────
for i, msg in enumerate(messages):
    avatar = "👤" if msg["role"] == "user" else "🏗️"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            btn_col1, btn_col2, _ = st.columns([2, 2, 6])
            with btn_col1:
                st.download_button(
                    "💾 שמור",
                    data=msg["content"].encode("utf-8"),
                    file_name=f"תשובה_{i // 2 + 1}.txt",
                    mime="text/plain",
                    key=f"dl_ans_{i}",
                )
            with btn_col2:
                if st.button("📋 העתק", key=f"copy_{i}"):
                    st.toast("✅ הועתק ללוח!")

# ── Export / clear buttons ─────────────────────────────────────────────────────
if messages:
    st.divider()
    exp_col1, exp_col2, _ = st.columns([3, 3, 4])
    with exp_col1:
        st.download_button(
            "📄 ייצא שיחה",
            data=export_conversation(mode).encode("utf-8"),
            file_name="שיחה_מוח_הבנייה.txt",
            mime="text/plain",
        )
    with exp_col2:
        if st.button("🗑️ נקה שיחה"):
            st.session_state.mode_messages[mode] = []
            st.session_state.mode_active_id[mode] = None
            st.rerun()

# ── Input area (mode-specific, isolated keys) ──────────────────────────────────
if mode == "שאלה":
    # chat_input key is tied to mode so switching modes never carries over a value
    if prompt := st.chat_input(
        "שאל שאלה מקצועית... (מעקה, כיסוי, בטון, ת\"י...)",
        key="chat_input_shela",
    ):
        if client is None:
            st.error("אין חיבור ל-API.")
        else:
            messages.append({"role": "user", "content": prompt})
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
                btn_c1, _, _ = st.columns([2, 2, 6])
                with btn_c1:
                    st.download_button(
                        "💾 שמור",
                        data=answer.encode("utf-8"),
                        file_name="תשובה.txt",
                        mime="text/plain",
                        key="dl_latest",
                    )

            messages.append({"role": "assistant", "content": answer})
            auto_save_current()

else:
    if mode == "עלויות":
        placeholder = "לדוגמא: מרפסת בטון 3×2 מ׳ קומה שלישית / ריצוף פורצלן 50 מ\"ר"
        button_label = "🧮 חשב עלות"
        hint = "הערכת כמויות ועלויות בשקלים • אינה מחליפה תכנון מהנדס"
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
        send_clicked = st.button(button_label, use_container_width=True, type="primary",
                                 key=f"send_{mode}")
    with clear_col:
        if st.button("🗑️ נקה", use_container_width=True, key=f"clear_{mode}"):
            st.session_state.mode_messages[mode] = []
            st.session_state.mode_active_id[mode] = None
            st.rerun()

    if send_clicked and user_input.strip():
        if client is None:
            st.error("אין חיבור ל-API. עדכן את המפתח.")
        else:
            question = user_input.strip()
            messages.append({"role": "user", "content": question})

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

            messages.append({"role": "assistant", "content": answer})
            auto_save_current()
            st.rerun()
