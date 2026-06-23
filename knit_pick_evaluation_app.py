import streamlit as st
import json
import uuid
from datetime import datetime
import os
import random
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURATION & STATE INITIALIZATION ---
st.set_page_config(page_title="הערכת Knit Pick", layout="wide")

@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    return gspread.authorize(creds)

# Initialize session state variables
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]

if "current_step" not in st.session_state:
    st.session_state.current_step = 0

if "profile_set" not in st.session_state:
    st.session_state.profile_set = False

# --- GLOBAL CSS INJECTION ---
st.markdown("""
    <style>
    /* ---- RTL AND HEBREW ALIGNMENT ---- */
    .stMarkdown, .stText, p, h1, h2, h3, h4, h5, h6, label[data-testid="stWidgetLabel"] {
        direction: rtl !important;
        text-align: right !important;
    }
    
    /* Align the text inside the selectbox */
    div[data-baseweb="select"] {
        direction: rtl !important;
    }
    
    /* Submit buttons */
    [data-testid="stForm"] button, .stButton button {
        background-color: #1E88E5 !important;
        color: white !important;
        font-size: 18px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 10px !important;
        direction: rtl !important;
    }
    [data-testid="stForm"] button:hover, .stButton button:hover {
        background-color: #1565C0 !important;
    }
    
    /* ---- FASHION EXPERTISE SLIDER ENHANCEMENTS ---- */
    /* 1. Make the slider options text bigger and extra bold */
    .stSlider [data-testid="stTickBar"] span {
        font-size: 16px !important;
        font-weight: 900 !important;
        direction: rtl !important;
    }
    /* 2. Make the question title above the slider bigger */
    .stSlider [data-testid="stWidgetLabel"] p {
        font-size: 20px !important;
    }
    /* 3. Make the draggable dot bigger for easier mobile tapping */
    .stSlider [role="slider"] {
        width: 24px !important;
        height: 24px !important;
    }
    /* ----------------------------------------------- */
    
    /* Make the stars larger but leave their alignment natural */
    div[data-testid="stFeedback"] {
        transform: scale(2);
        transform-origin: left center;
        padding-bottom: 10px;
        padding-left: 20%;
        padding-right: 20%;
        direction: ltr; /* Keeps the stars functionally left-to-right 1 to 5 */
    }
    
    /* Limit image height to prevent excessive scrolling */
    [data-testid="stImage"] img {
        max-height: 55vh !important;
        object-fit: contain !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. ONBOARDING SCREEN ---
if not st.session_state.profile_set:
    st.title("ברוכים הבאים ל-Knit Pick! 🧶")
    st.markdown("### אנחנו צריכים את עזרתכם בהערכת חוש האופנה של ה-AI שלנו!")
    st.write("לפני שנתחיל, ספרו לנו קצת על עצמכם. זה יעזור לנו להבין אם המודל מתאים יותר לקהלים מסוימים או למומחי אופנה.")
    
    with st.form("onboarding_form"):
        st.markdown("#### 👤 פרטים אישיים")
        gender = st.selectbox("**מגדר**", ["אישה", "גבר", "א-בינארי", "מעדיף/ה שלא לענות"])
        
        st.divider()
        
        st.markdown("#### 👗 מומחיות באופנה")
        expertise = st.select_slider(
            "**עד כמה את/ה מבין/ה באופנה?**", 
            options=[
                "1 - אני פשוט מתלבש/ת", 
                "2 - מתעניין/ת לפעמים", 
                "3 - מבין/ה די טוב", 
                "4 - חובב/ת אופנה", 
                "5 - מומחה / סטייליסט/ית"
            ]
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button("התחלת ההערכה ⬅️", use_container_width=True)
        
        if submitted:
            # Map Hebrew input to English output for the Google Sheet
            gender_mapping = {
                "אישה": "Female",
                "גבר": "Male",
                "א-בינארי": "Non-binary",
                "מעדיף/ה שלא לענות": "Prefer not to say"
            }
            
            st.session_state.user_gender = gender_mapping[gender]
            st.session_state.user_expertise = int(expertise.split(" - ")[0])
            st.session_state.profile_set = True
            st.rerun() 
            
    st.stop() 


# --- 3. DATA LOADER ---
@st.cache_data
def load_evaluation_data(json_path="survey_manifest.json", max_candidates_per_anchor=5):
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        st.error(f"Error: Could not find '{json_path}'.")
        st.stop()
        
    tasks = []
    
    for anchor_id, anchor_data in data.items():
        raw_candidates = anchor_data.get("positives", []) + anchor_data.get("negatives", [])
        anchor_type = str(anchor_data.get("anchor_type", "top")).lower()
        anchor_img = str(anchor_data.get("img_url", ""))
        
        random.shuffle(raw_candidates)
        limited_candidates = raw_candidates[:max_candidates_per_anchor]
        
        for c in limited_candidates:
            tasks.append({
                "anchor_id": str(anchor_id),
                "anchor_type": anchor_type,
                "anchor_img": anchor_img,
                "candidate_id": str(c["id"]),
                "candidate_img": str(c["img_url"]),
                "model_score": float(c["score"])
            })
            
    return tasks

base_tasks = load_evaluation_data()

if "session_tasks" not in st.session_state:
    user_tasks = list(base_tasks)
    random.shuffle(user_tasks)
    st.session_state.session_tasks = user_tasks

# --- 4. SUBMISSION LOGIC ---
def save_ratings_and_advance():
    step = st.session_state.current_step
    current_task = st.session_state.session_tasks[step]
    
    dynamic_key = f"step_{step}_rating"
    raw_rating = st.session_state.get(dynamic_key)
    
    human_score = (raw_rating + 1) if raw_rating is not None else 0 
    
    record = [
        st.session_state.session_id,
        st.session_state.user_gender,     
        st.session_state.user_expertise,  
        current_task["anchor_id"],
        current_task["candidate_id"],
        human_score,
        current_task["model_score"],
        datetime.now().isoformat()
    ]
    
    try:
        client = get_gspread_client()
        sheet_url = st.secrets["gcp_service_account"]["sheet_url"]
        sheet = client.open_by_url(sheet_url).sheet1
        sheet.append_rows([record])
    except Exception as e:
        st.error(f"שגיאה בשמירה ל-Google Sheets: {e}")
        return 
    
    if dynamic_key in st.session_state:
        del st.session_state[dynamic_key]
            
    st.session_state.current_step += 1

# --- 5. UI LAYOUT ---
st.title("Knit Pick: התאמת אופנה")

if st.session_state.current_step >= len(st.session_state.session_tasks):
    st.success("סיימת את כל ההערכות! תודה רבה על העזרה.")
    st.balloons()
    st.stop()

current_task = st.session_state.session_tasks[st.session_state.current_step]
step = st.session_state.current_step

is_top = "top" in current_task["anchor_type"].lower()
top_img = current_task["anchor_img"] if is_top else current_task["candidate_img"]
bottom_img = current_task["candidate_img"] if is_top else current_task["anchor_img"]

progress = step / len(st.session_state.session_tasks)

# Friendly message showing how many they've done and encouraging them
progress_text = f"דירגתם עד כה: {step} שילובים | אפשר לעצור מתי שתרצו, אבל נשמח אם תדרגו כמה שיותר!"
st.progress(progress, text=progress_text)

st.markdown("### עד כמה השילוב הזה מתאים?")
st.write("דרגו את השילוב מ-1 (ממש לא מתאים) עד 5 כוכבים (שילוב מושלם).")

# Display exactly two columns side-by-side
col1, col2 = st.columns(2)

with col1:
    st.markdown("**חלק עליון**")
    st.image(top_img, use_container_width=True)

with col2:
    st.markdown("**חלק תחתון**")
    st.image(bottom_img, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("**דרגו את השילוב:**")
st.feedback("stars", key=f"step_{step}_rating")

st.markdown("<div style='clear: both; margin-bottom: 40px;'></div>", unsafe_allow_html=True)
st.divider()
st.button("הגשה ולשילוב הבא ⬅️", on_click=save_ratings_and_advance, type="primary", use_container_width=True)