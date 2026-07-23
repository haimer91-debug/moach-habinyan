# -*- coding: utf-8 -*-
"""
מוח הבנייה — Construction Knowledge Assistant
Streamlit chat app, mobile-first, Hebrew RTL.
"""
import os, re, sys, json, uuid, base64, threading, datetime
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

st.set_page_config(
    page_title="מוח הבנייה",
    page_icon="🏗️",
    layout="centered",
    initial_sidebar_state="auto",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"], .stApp {
    background-color: #0d1117 !important; color: #c9d1d9 !important;
}
[data-testid="stHeader"] { background-color: #0d1117 !important; }
[data-testid="stSidebar"] { background-color: #161b22 !important; direction: rtl; }

body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stVerticalBlock"] {
    direction: rtl; text-align: right;
    font-family: 'Segoe UI', Arial, sans-serif;
}
h1,h2,h3,h4,p,li { text-align: right; direction: rtl; }

/* Chat bubbles */
[data-testid="stChatMessage"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 12px !important;
    margin-bottom: 6px !important;
    direction: rtl !important;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
    direction: rtl; text-align: right;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background-color: #1c2128 !important;
    border-color: #388bfd40 !important;
}
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"] {
    background-color: #21262d !important;
    border: 1px solid #30363d !important;
}

/* Buttons */
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
.stButton button:hover { border-color: #58a6ff !important; color: #58a6ff !important; }

/* Inputs */
textarea, input[type="text"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
    border-radius: 8px !important;
    font-size: 16px !important;
    direction: rtl !important;
}

/* Chat input bar */
[data-testid="stChatInput"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 24px !important;
    direction: rtl !important;
}
[data-testid="stChatInput"] textarea {
    border: none !important; direction: rtl !important;
}

/* ── Inline 📎 file uploader — floats at bottom-left next to chat input ── */
section[data-testid="stFileUploader"] {
    position: fixed !important;
    bottom: 14px !important;
    left: max(10px, calc(50% - 395px)) !important;
    z-index: 999 !important;
    width: auto !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] { display: none !important; }
[data-testid="stFileUploadDropzone"] {
    border: 1px solid #30363d !important;
    border-radius: 22px !important;
    background: #21262d !important;
    min-height: 0 !important;
    padding: 7px 14px 7px 10px !important;
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
    cursor: pointer !important;
    width: auto !important;
    white-space: nowrap !important;
}
[data-testid="stFileUploadDropzone"] span { display: none !important; }
[data-testid="stFileUploadDropzone"]::before {
    content: "📎";
    font-size: 17px;
    line-height: 1;
    flex-shrink: 0;
}
[data-testid="stFileUploadDropzone"] button {
    background: transparent !important;
    border: none !important;
    color: #8b949e !important;
    font-size: 0.78em !important;
    padding: 0 !important;
    cursor: pointer !important;
    white-space: nowrap !important;
}
[data-testid="stFileUploadDropzone"] button:hover { color: #58a6ff !important; }

hr { border-color: #30363d !important; }
.stCaption, small { color: #8b949e !important; }
.stDownloadButton button {
    background-color: #21262d !important; border-color: #30363d !important;
    color: #58a6ff !important; font-size: 0.8em !important;
    padding: 2px 10px !important; border-radius: 6px !important;
}
[data-testid="stSpinner"] { color: #58a6ff !important; }
[data-testid="stExpander"] {
    background-color: #161b22 !important;
    border: 1px solid #30363d !important; border-radius: 8px !important;
}
[data-testid="stChatMessage"] p { margin-bottom: 0.4em !important; }
[data-testid="stChatMessage"] ul,
[data-testid="stChatMessage"] ol { margin-top: 0.3em !important; }

[data-testid="stSidebar"] .stButton button {
    text-align: right !important; direction: rtl !important;
    font-size: 0.85em !important; overflow: hidden !important;
    text-overflow: ellipsis !important; white-space: nowrap !important;
}

/* Pending image chip */
.img-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 4px 8px;
    font-size: 0.82em;
    color: #8b949e;
    margin-bottom: 6px;
}
</style>
""", unsafe_allow_html=True)

# ── Env + secrets ──────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
try:
    for _k in ("ANTHROPIC_API_KEY", "SUPERVISOR_NAME", "COMPANY_NAME"):
        if _k in st.secrets and not os.getenv(_k):
            os.environ[_k] = st.secrets[_k]
except Exception:
    pass

# ── Clients & warm-up ──────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY", "")
    return anthropic.Anthropic(api_key=key) if key and not key.startswith("sk-ant-REPLACE") else None

@st.cache_resource
def warm_pdf_index():
    def _w():
        try:
            from standards.pdf_search import _get_index; _get_index()
        except Exception: pass
    threading.Thread(target=_w, daemon=True).start()
    return True

warm_pdf_index()

# ── Knowledge bases ────────────────────────────────────────────────────────────
@st.cache_resource
def _load_kb():
    kb = {}
    try:
        from standards.engineering_kb import (
            STRUCTURAL_RC, STEEL_REBAR, FORMWORK, LOADS,
            WATERPROOFING, PLASTER_INSULATION, FLOORING,
            PLUMBING, ELECTRICAL, FIRE_SAFETY, RAILINGS,
            FOUNDATIONS, QUALITY_CONTROL, COSTS_2026,
            STAIRS, GREEN_BUILDING, HOT_WEATHER_CONCRETING,
            TOLERANCES_CRACKS,
        )
        kb.update({
            "STRUCTURAL_RC": STRUCTURAL_RC, "STEEL_REBAR": STEEL_REBAR,
            "FORMWORK": FORMWORK, "LOADS": LOADS,
            "WATERPROOFING": WATERPROOFING, "PLASTER_INSULATION": PLASTER_INSULATION,
            "FLOORING": FLOORING, "PLUMBING": PLUMBING,
            "ELECTRICAL": ELECTRICAL, "FIRE_SAFETY": FIRE_SAFETY,
            "RAILINGS": RAILINGS, "FOUNDATIONS": FOUNDATIONS,
            "QUALITY_CONTROL": QUALITY_CONTROL, "COSTS_2026": COSTS_2026,
            "STAIRS": STAIRS, "GREEN_BUILDING": GREEN_BUILDING,
            "HOT_WEATHER_CONCRETING": HOT_WEATHER_CONCRETING,
            "TOLERANCES_CRACKS": TOLERANCES_CRACKS,
        })
    except Exception:
        pass
    try:
        from standards.professional_kb import (
            ACOUSTICS, ELEVATORS, HVAC, URBAN_RENEWAL,
            REAL_ESTATE_LEVY, BUILDING_PERMITS, CONSTRUCTION_CONTRACTS,
            CONSTRUCTION_INSURANCE, ALUMINUM, HYDROLOGY,
            SITE_MANAGEMENT, ACCESSIBILITY, MUNICIPAL_CONDITIONS,
            GEOTECHNICAL, TRAFFIC_CONSULTING, LANDSCAPE_INTERIOR,
            QUANTITY_SURVEYING,
        )
        kb.update({
            "ACOUSTICS": ACOUSTICS, "ELEVATORS": ELEVATORS,
            "HVAC": HVAC, "URBAN_RENEWAL": URBAN_RENEWAL,
            "REAL_ESTATE_LEVY": REAL_ESTATE_LEVY, "BUILDING_PERMITS": BUILDING_PERMITS,
            "CONSTRUCTION_CONTRACTS": CONSTRUCTION_CONTRACTS,
            "CONSTRUCTION_INSURANCE": CONSTRUCTION_INSURANCE,
            "ALUMINUM": ALUMINUM, "HYDROLOGY": HYDROLOGY,
            "SITE_MANAGEMENT": SITE_MANAGEMENT, "ACCESSIBILITY": ACCESSIBILITY,
            "MUNICIPAL_CONDITIONS": MUNICIPAL_CONDITIONS, "GEOTECHNICAL": GEOTECHNICAL,
            "TRAFFIC_CONSULTING": TRAFFIC_CONSULTING,
            "LANDSCAPE_INTERIOR": LANDSCAPE_INTERIOR,
            "QUANTITY_SURVEYING": QUANTITY_SURVEYING,
        })
    except Exception:
        pass
    try:
        from standards.planning_regs import PLANNING_REGULATIONS
        kb["PLANNING_REGULATIONS"] = PLANNING_REGULATIONS
    except Exception:
        pass
    return kb

_KB = _load_kb()
_ALL_KB = "\n\n".join(_KB.values())

_SYSTEM = f"""\
אתה מוח הבנייה — עוזר AI מקצועי לפיקוח בנייה בישראל.

אתה בקיא ב:
• תקנות תכנון ובנייה — גובה, חניה, נגישות, רישוי, שימוש חורג
• תקנים ישראליים (ת"י) — בטון ת"י 118/466, ברזל, אינסטלציה, חשמל, בידוד, מעקות, כיבוי אש
• המפרט הכחול — 51 פרקי ביצוע ופיקוח
• הנדסת קונסטרוקציה: לוחות, קורות, עמודים, מרפסות, יסודות
• איטום, ניקוז, גמר: ריצוף, טיח, צביעה, חיפוי
• זיהוי ליקויים בשטח: סדקים, רטיבות, כשלי ביצוע, חריגות מתקן
• כתיבת דוחות ביקורת מקצועיים
• הערכת כמויות ועלויות — מחירי שוק ישראל 2025-2026
• כיבוי אש, ספרינקלרים, גלאים, גישה לנכה
• היתרי בנייה, תמ"א 38, היטל השבחה, טופס 4

כשמשתמש שולח תמונה:
• נתח לעומק מנקודת מבט הנדסית: חומרים, מצב, ליקויים, חריגות
• זהה סכנות ובעיות שצריכות טיפול דחוף
• תן חוות דעת מפקח בנייה מנוסה
• המלץ על בדיקות נוספות אם נדרש

כשמשתמש מבקש הערכת עלות:
• חשב כמויות בדיוק (הראה נוסחה ומספרים)
• תן מחירים בשקלים (₪) עם טווח מינ'–מקס'
• פרט לפי פריטי עבודה

כשמשתמש מבקש דוח ביקורת:
• פרמט מקצועי: נושא, ממצאים, הנחיות תיקון, בסיס תקני, סטטוס

ענה תמיד בעברית. היה ישיר, מדויק, מקצועי.
כשיש מידע בבסיס הידע שלהלן — צטט סעיפים מדויקים. אל תאמר "אין לי גישה" אם המידע כן קיים למטה.

══════════════════════════════════════════════════
בסיס הידע המקצועי המלא — ישראל
══════════════════════════════════════════════════

{_ALL_KB}
"""

# ── Persistence — browser localStorage (survives app restarts on Streamlit Cloud)
from streamlit_local_storage import LocalStorage

_LS_KEY = "moach_convos_v1"

def _ls():
    return LocalStorage()

def load_convos():
    # Session cache — avoid calling LS component more than once per session
    if "convos_cache" in st.session_state:
        return st.session_state.convos_cache
    data = _ls().getItem(_LS_KEY)
    # getItem returns None on the very first render cycle (component not yet ready)
    if isinstance(data, list):
        st.session_state.convos_cache = data
        return data
    st.session_state.convos_cache = []
    return []

def save_convos(convos):
    st.session_state.convos_cache = convos
    _ls().setItem(_LS_KEY, convos)

def _serialisable(msgs):
    out = []
    for m in msgs:
        entry = {"role": m.get("role", "user"), "content": m.get("content", "")}
        if m.get("image_label"):
            entry["image_label"] = m["image_label"]
        out.append(entry)
    return out

def auto_save():
    msgs = st.session_state.messages
    if not msgs:
        return
    convos = load_convos()
    cid = st.session_state.active_convo_id
    first_user = next((m["content"] for m in msgs if m.get("role") == "user"), "")
    title = (first_user[:50] + "…") if len(first_user) > 50 else first_user
    now = datetime.datetime.now().isoformat()
    serialised = _serialisable(msgs)

    if cid:
        for c in convos:
            if c["id"] == cid:
                c["messages"] = serialised
                c["title"] = title
                c["updated_at"] = now
                save_convos(convos)
                return

    # New conversation
    cid = str(uuid.uuid4())
    st.session_state.active_convo_id = cid
    convos.insert(0, {
        "id": cid, "title": title,
        "messages": serialised,
        "created_at": now, "updated_at": now,
    })
    save_convos(convos)

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "active_convo_id" not in st.session_state:
    st.session_state.active_convo_id = None
if "pending_image" not in st.session_state:
    st.session_state.pending_image = None
if "pending_image_type" not in st.session_state:
    st.session_state.pending_image_type = None
if "img_key" not in st.session_state:
    st.session_state.img_key = 0

# ── Helpers ────────────────────────────────────────────────────────────────────
def clean(text: str) -> str:
    return re.sub(r'\n{3,}', '\n\n', text.strip())

def export_txt() -> str:
    ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    lines = [f"שיחה עם מוח הבנייה — {ts}", "=" * 50, ""]
    for m in st.session_state.messages:
        role = "אני" if m.get("role") == "user" else "מוח הבנייה"
        lines += [f"[{role}]", m.get("content", ""), ""]
    return "\n".join(lines)

def call_brain(client, prev_messages, user_text, image_bytes=None, image_mime=None):
    """prev_messages = conversation history BEFORE the new message."""
    api_msgs = []
    for m in prev_messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            api_msgs.append({"role": role, "content": content})

    # New user message (with optional image)
    if image_bytes:
        b64 = base64.standard_b64encode(image_bytes).decode()
        user_content = [
            {"type": "image",
             "source": {"type": "base64", "media_type": image_mime, "data": b64}},
            {"type": "text",
             "text": user_text or "נתח את התמונה מנקודת מבט מפקח בנייה. זהה ליקויים, חריגות, מצב הביצוע."},
        ]
    else:
        user_content = user_text

    api_msgs.append({"role": "user", "content": user_content})

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=_SYSTEM,
        messages=api_msgs,
    )
    return resp.content[0].text.strip()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    if st.button("➕ שיחה חדשה", use_container_width=True, type="primary"):
        st.session_state.messages = []
        st.session_state.active_convo_id = None
        st.session_state.pending_image = None
        st.session_state.img_key += 1
        st.rerun()

    st.markdown("---")
    st.markdown("### 💬 שיחות שמורות")
    convos = load_convos()
    if not convos:
        st.caption("אין שיחות שמורות עדיין")
    for c in convos:
        is_active = c["id"] == st.session_state.active_convo_id
        date_str = c.get("updated_at", "")[:10]
        cb, cx = st.columns([5, 1])
        with cb:
            if st.button(
                c["title"], key=f"load_{c['id']}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
                help=date_str,
            ):
                loaded = c.get("messages", [])
                st.session_state.messages = list(loaded)
                st.session_state.active_convo_id = c["id"]
                st.session_state.pending_image = None
                st.session_state.img_key += 1
                st.rerun()
        with cx:
            if st.button("✕", key=f"del_{c['id']}", help="מחק"):
                save_convos([x for x in convos if x["id"] != c["id"]])
                if st.session_state.active_convo_id == c["id"]:
                    st.session_state.messages = []
                    st.session_state.active_convo_id = None
                st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ אודות")
    st.caption(
        "מוח הבנייה — עוזר AI לפיקוח בנייה.\n"
        "• המפרט הכחול (51 פרקים)\n"
        "• תקנים ישראליים סרוקים\n"
        "• תקנות תכנון ובנייה\n"
        "• מחירוני בנייה 2025-2026\n"
        "• Claude Vision\n\n"
        "⚠️ לשימוש כעזר מקצועי בלבד."
    )

# ── Main ───────────────────────────────────────────────────────────────────────
client = get_client()

st.markdown("## 🏗️ מוח הבנייה")
st.caption("מפקח AI לבנייה • שאל כל שאלה • צרף תמונה מהשטח")

if client is None:
    st.error("⚠️ מפתח API לא מוגדר.")

# ── Chat history ───────────────────────────────────────────────────────────────
for i, msg in enumerate(st.session_state.messages):
    avatar = "👤" if msg.get("role") == "user" else "🏗️"
    with st.chat_message(msg["role"], avatar=avatar):
        if msg.get("image_label"):
            st.caption(f"📷 {msg['image_label']}")
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            c1, _, _ = st.columns([2, 2, 6])
            with c1:
                st.download_button(
                    "💾 שמור", data=msg["content"].encode("utf-8"),
                    file_name=f"תשובה_{i//2+1}.txt", mime="text/plain",
                    key=f"dl_{i}",
                )

# ── Export / clear ─────────────────────────────────────────────────────────────
if st.session_state.messages:
    st.divider()
    ec1, ec2, _ = st.columns([3, 3, 4])
    with ec1:
        st.download_button(
            "📄 ייצא שיחה", data=export_txt().encode("utf-8"),
            file_name="שיחה_מוח_הבנייה.txt", mime="text/plain",
        )
    with ec2:
        if st.button("🗑️ נקה שיחה"):
            st.session_state.messages = []
            st.session_state.active_convo_id = None
            st.session_state.pending_image = None
            st.session_state.img_key += 1
            st.rerun()

# ── Pending image chip (shows above chat input when image is attached) ─────────
if st.session_state.pending_image:
    chip_col, rm_col, _ = st.columns([2, 1, 7])
    with chip_col:
        st.image(st.session_state.pending_image, width=56)
    with rm_col:
        st.write("")  # vertical align
        if st.button("✕ הסר", key="rm_img"):
            st.session_state.pending_image = None
            st.session_state.pending_image_type = None
            st.session_state.img_key += 1
            st.rerun()

# ── File uploader — styled as inline 📎 button via CSS (only when no pending) ──
if not st.session_state.pending_image:
    uploaded = st.file_uploader(
        "צרף תמונה",
        type=["jpg", "jpeg", "png", "webp"],
        label_visibility="collapsed",
        key=f"img_{st.session_state.img_key}",
    )
    if uploaded:
        st.session_state.pending_image = uploaded.read()
        st.session_state.pending_image_type = uploaded.type or "image/jpeg"
        st.rerun()

# ── Chat input ─────────────────────────────────────────────────────────────────
placeholder = (
    "כתוב שאלה לגבי התמונה..." if st.session_state.pending_image
    else "שאל על תקנים, עלויות, ליקויים, דוחות..."
)

if prompt := st.chat_input(placeholder):
    if client is None:
        st.error("אין חיבור ל-API.")
    else:
        # Snapshot history BEFORE appending new message
        prev_messages = list(st.session_state.messages)

        img_bytes = st.session_state.pending_image
        img_type  = st.session_state.pending_image_type
        img_label = f"תמונה ({len(img_bytes)//1024} KB)" if img_bytes else None

        user_msg = {"role": "user", "content": prompt}
        if img_label:
            user_msg["image_label"] = img_label
        st.session_state.messages.append(user_msg)

        with st.chat_message("user", avatar="👤"):
            if img_label:
                st.caption(f"📷 {img_label}")
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="🏗️"):
            with st.spinner("מעבד... ⏳"):
                try:
                    answer = call_brain(
                        client, prev_messages, prompt,
                        image_bytes=img_bytes, image_mime=img_type,
                    )
                    answer = clean(answer)
                except Exception as e:
                    answer = f"⚠️ שגיאה: {e}"
            st.markdown(answer)
            c1, _, _ = st.columns([2, 2, 6])
            with c1:
                st.download_button(
                    "💾 שמור", data=answer.encode("utf-8"),
                    file_name="תשובה.txt", mime="text/plain",
                    key="dl_latest",
                )

        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.session_state.pending_image = None
        st.session_state.pending_image_type = None
        st.session_state.img_key += 1
        auto_save()
