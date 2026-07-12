import os
import sys
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# ── Bootstrap ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)
OUTPUT_DIR = BASE_DIR / "פלטים"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="מערכת פיקוח בנייה",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── RTL + Hebrew styling ─────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    html, body, [class*="css"] { direction: rtl; font-family: 'Arial', sans-serif; }
    .stTextArea textarea { direction: rtl; text-align: right; }
    .stTextInput input { direction: rtl; text-align: right; }
    .stSelectbox select { direction: rtl; }
    h1, h2, h3, label, .stMarkdown { text-align: right; }
    .stButton button { width: 100%; font-size: 1.1rem; font-weight: bold; }
    .success-box {
        background: #e8f5e9; border-right: 4px solid #2e7d32;
        padding: 12px 16px; border-radius: 6px; margin: 8px 0;
    }
    .urgent-box {
        background: #ffebee; border-right: 4px solid #c62828;
        padding: 12px 16px; border-radius: 6px; margin: 8px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar: settings ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ הגדרות")
    api_key = st.text_input(
        "מפתח Claude API",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="הכנס את מפתח ה-API מ-console.anthropic.com",
    )
    supervisor_name = st.text_input(
        "שם המפקח",
        value=os.getenv("SUPERVISOR_NAME", ""),
    )
    company_name = st.text_input(
        "שם החברה / עצמאי",
        value=os.getenv("COMPANY_NAME", ""),
    )
    st.divider()
    st.markdown("**גרסה 1.0** | מערכת אייג'נטים לפיקוח בנייה")


def get_client():
    if not api_key or api_key.startswith("הכנס"):
        st.error("יש להזין מפתח API בתפריט הצד.")
        st.stop()
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


# ── Main tabs ────────────────────────────────────────────────────────────────
st.markdown("# 🏗️ מערכת אייג'נטים — פיקוח בנייה")
st.markdown("בחר לשונית לפי הפעולה הרצויה")

tab1, tab2, tab3 = st.tabs(["📋 דו\"ח ביקור", "💰 מעקב תקציב", "📅 מעקב לוז"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Inspection Report
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## 📋 יצירת דו\"ח ביקור אוטומטי")
    st.markdown(
        "הדבק את שיחת ה-WhatsApp מהביקור (או כתוב הערות חופשיות), "
        "מלא את פרטי הפרויקט ולחץ **צור דו\"ח**."
    )

    col1, col2 = st.columns(2)
    with col1:
        project_name = st.text_input("שם הפרויקט *", placeholder="פרויקט רימון, בת ים")
        address = st.text_input("כתובת", placeholder="רחוב הרצל 12, בת ים")
        attendees = st.text_input(
            "נוכחים בביקור", placeholder="קבלן ראשי: ג'ורג', יזם: דוד כהן"
        )
    with col2:
        visit_date = st.date_input("תאריך הביקור", value=date.today())
        visit_time = st.text_input("שעת הביקור", placeholder="09:30", value="")
        report_num = st.text_input("מספר דו\"ח", placeholder="001")

    # WhatsApp file upload
    uploaded_file = st.file_uploader(
        "העלה קובץ ייצוא WhatsApp (.txt) — או הדבק טקסט ישירות למטה",
        type=["txt"],
        help="ייצא את השיחה מ-WhatsApp (ללא מדיה) ושמור כ-.txt, אז גרור לכאן",
    )

    prefill = ""
    if uploaded_file is not None:
        prefill = uploaded_file.read().decode("utf-8", errors="ignore")
        st.success(f"הקובץ נטען: {uploaded_file.name} ({len(prefill):,} תווים)")

    raw_notes = st.text_area(
        "הערות ביקור / שיחת WhatsApp *",
        value=prefill,
        height=250,
        placeholder=(
            "הדבק כאן את ייצוא שיחת ה-WhatsApp, או כתוב הערות חופשיות מהביקור.\n\n"
            "לדוג':\n"
            "[28/05/2025, 09:15] חיים: בקומה 3 יש שקיעה בתקרת שלד - דחוף\n"
            "[28/05/2025, 09:22] חיים: האינסטלטור לא סיים את עבודות הניקוז בממ\"ד\n"
            "[28/05/2025, 09:35] חיים: ריצוף קומה 1 נגמר, נראה טוב"
        ),
    )

    generate_btn = st.button("⚡ צור דו\"ח ביקור", type="primary")

    if generate_btn:
        if not project_name:
            st.warning("יש למלא שם פרויקט.")
        elif not raw_notes.strip():
            st.warning("יש להזין הערות ביקור.")
        else:
            client = get_client()

            with st.spinner("מנתח הערות ומכין דו\"ח... (כ-20-30 שניות)"):
                from agents.inspection_report import analyze_notes
                from templates.report_builder import build_inspection_docx

                structured = analyze_notes(raw_notes, client)

            # ── Preview ─────────────────────────────────────────────────────
            st.markdown("---")
            st.markdown("### תצוגה מקדימה — ניתוח הנדסי")

            current_phase = structured.get("current_phase", "")
            if current_phase:
                st.info(f"**שלב נוכחי:** {current_phase}")

            findings = structured.get("findings", [])
            next_visit = structured.get("next_visit", "")

            # Show each finding as an expander
            for idx, f in enumerate(findings, 1):
                urgent = f.get("urgent", False)
                std_found = f.get("standard_found", True)
                clarify = f.get("clarification_needed", "").strip()
                label = f"ממצא {idx} — {f.get('element','?')} | {f.get('location','')}"
                icon = "🔴" if urgent else ("🟡" if not std_found else "🟢")

                with st.expander(f"{icon} {label}", expanded=(idx == 1)):
                    st.markdown(f"**מיקום מוגדר:** {f.get('location','—')}")
                    st.markdown(f"**כשל:** {f.get('defect_type','—')}")

                    std_ref = f.get("standard_ref", "")
                    if std_found:
                        st.markdown(
                            f'<div class="success-box">📋 <strong>תקן:</strong> {std_ref}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f'<div class="urgent-box">⚠️ {std_ref}</div>',
                            unsafe_allow_html=True,
                        )

                    st.markdown(f"**שלב מחייב לתיקון:** `{f.get('correction_phase','—')}`")
                    st.markdown(f"**הטיפול הנדרש:** {f.get('treatment','—')}")

                    if clarify:
                        st.info(f"❓ שאלה לחיים: {clarify}")

            if next_visit:
                st.markdown(
                    f'<div class="success-box">📅 <strong>ביקור הבא:</strong> {next_visit}</div>',
                    unsafe_allow_html=True,
                )

            # Build Word document
            doc_data = {
                "project_name": project_name,
                "address": address,
                "date": visit_date.strftime("%d/%m/%Y"),
                "time": visit_time or "—",
                "report_number": report_num or "—",
                "supervisor_name": supervisor_name or "המפקח",
                "company_name": company_name or "פיקוח בנייה",
                "attendees": attendees,
                "current_phase": current_phase,
                "findings": findings,
                "next_visit": next_visit,
            }

            docx_bytes = build_inspection_docx(doc_data)

            # Save to output folder
            filename = f"דוח_ביקור_{project_name}_{visit_date.strftime('%Y%m%d')}.docx"
            save_path = OUTPUT_DIR / filename
            save_path.write_bytes(docx_bytes)

            st.success(f"הדו\"ח נשמר בתיקיית הפלטים: {filename}")

            st.download_button(
                label="⬇️ הורד דו\"ח Word",
                data=docx_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Budget tracker (coming soon)
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## 💰 מעקב תקציב")
    st.info(
        "Agent זה בפיתוח.\n\n"
        "יאפשר: העלאת Excel תקציב + חשבוניות → ניתוח חריגות → דו\"ח מצב תקציב.",
        icon="🔧",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Schedule tracker (coming soon)
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## 📅 מעקב לוז")
    st.info(
        "Agent זה בפיתוח.\n\n"
        "יאפשר: הגדרת אבני דרך → עדכון התקדמות → ניתוח עיכובים → המלצות.",
        icon="🔧",
    )
