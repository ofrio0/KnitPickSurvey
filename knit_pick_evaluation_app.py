import streamlit as st
import json
import uuid
from datetime import datetime
import os
import random
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURATION & STATE INITIALIZATION ---
st.set_page_config(page_title="Knit Pick Eval", layout="wide")

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

# --- 2. ONBOARDING SCREEN ---
# If they haven't set their profile, show this and stop the rest of the app from loading
if not st.session_state.profile_set:
    # Inject CSS to make the submit button bold and Blue instead of the default Streamlit Red
    st.markdown("""
        <style>
        [data-testid="stForm"] button {
            background-color: #1E88E5 !important;
            color: white !important;
            font-size: 18px !important;
            font-weight: bold !important;
            border-radius: 8px !important;
            border: none !important;
            padding: 10px !important;
        }
        [data-testid="stForm"] button:hover {
            background-color: #1565C0 !important;
        }
        /* Make the slider text bigger and bolder */
        .stSlider [data-testid="stTickBar"] span {
            font-size: 16px !important;
            font-weight: bold !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("Welcome to Knit Pick! 🧶")
    st.markdown("### We need your help to evaluate our AI's fashion sense!")
    st.write("Before we begin, please tell us a bit about yourself. This helps us analyze if the AI aligns better with certain demographics or styling experts.")
    
    with st.form("onboarding_form"):
        st.markdown("#### 👤 Your Demographics")
        gender = st.selectbox("**How do you identify?**", ["Female", "Male", "Non-binary", "Prefer not to say"])
        
        st.divider()
        
        st.markdown("#### 👗 Your Fashion Expertise")
        expertise = st.select_slider(
            "**How well do you know fashion?**", 
            options=[
                "1 - I just wear clothes", 
                "2 - Casual interest", 
                "3 - Pretty knowledgeable", 
                "4 - Fashion enthusiast", 
                "5 - Expert / Stylist"
            ]
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        # Notice we removed type="primary" so our blue CSS takes over nicely
        submitted = st.form_submit_button("Start Evaluation ➡️", use_container_width=True)
        
        if submitted:
            st.session_state.user_gender = gender
            # Extract just the number from the expertise string
            st.session_state.user_expertise = int(expertise.split(" - ")[0])
            st.session_state.profile_set = True
            st.rerun() # Reload the page to show the main app
            
    st.stop() # Halts execution here until the form is submitted


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
        
        candidates = []
        for c in raw_candidates:
            candidates.append({
                "id": str(c["id"]),
                "img": str(c["img_url"]),
                "model_score": float(c["score"])
            })
            
        random.shuffle(candidates)
        candidates = candidates[:max_candidates_per_anchor] 
        
        tasks.append({
            "anchor_id": str(anchor_id),
            "anchor_type": str(anchor_data.get("anchor_type", "top")).lower(),
            "anchor_img": str(anchor_data.get("img_url", "")),
            "candidates": candidates
        })
        
    random.shuffle(tasks)
    return tasks

tasks = load_evaluation_data()

# --- 4. SUBMISSION LOGIC ---
def save_ratings_and_advance():
    step = st.session_state.current_step
    current_task = tasks[step]
    records = []
    
    for i, candidate in enumerate(current_task["candidates"]):
        dynamic_key = f"step_{step}_rating_{i}"
        raw_rating = st.session_state.get(dynamic_key)
        
        # If raw_rating is None (no stars given), human_score becomes 0
        human_score = (raw_rating + 1) if raw_rating is not None else 0 
        
        records.append([
            st.session_state.session_id,
            st.session_state.user_gender,     # ADDED GENDER
            st.session_state.user_expertise,  # ADDED EXPERTISE
            current_task["anchor_id"],
            candidate["id"],
            human_score,
            candidate["model_score"],
            datetime.now().isoformat()
        ])
    
    if records:
        try:
            client = get_gspread_client()
            sheet_url = st.secrets["gcp_service_account"]["sheet_url"]
            sheet = client.open_by_url(sheet_url).sheet1
            sheet.append_rows(records)
        except Exception as e:
            st.error(f"Error saving to Google Sheets: {e}")
            return 
    
    for i in range(len(current_task["candidates"])):
        old_key = f"step_{step}_rating_{i}"
        if old_key in st.session_state:
            del st.session_state[old_key]
            
    st.session_state.current_step += 1

# --- 5. UI LAYOUT ---
st.title("Knit Pick: Fashion Compatibility")

if st.session_state.current_step >= len(tasks):
    st.success("You've completed all evaluations! Thank you for your help.")
    st.balloons()
    st.stop()

current_task = tasks[st.session_state.current_step]
step = st.session_state.current_step

is_top = "top" in current_task["anchor_type"]
anchor_name = "Top" if is_top else "Bottom"
candidate_name = "bottoms" if is_top else "tops"

progress = step / len(tasks)
st.progress(progress, text=f"Task {step + 1} of {len(tasks)}")

st.markdown(f"### How well do these {candidate_name} match the {anchor_name.lower()}?")
st.write("Rate each combination from 1 star (terrible match) to 5 stars (perfect outfit).")

col_anchor, col_candidates = st.columns([1, 3.5])

with col_anchor:
    st.markdown(f"**Anchor {anchor_name}**")
    st.image(current_task["anchor_img"], use_container_width=True)
    st.caption(f"ID: {current_task['anchor_id']}")

with col_candidates:
    st.markdown("**Rate Candidates**")
    cand_cols = st.columns(len(current_task["candidates"]))
    
    for i, (col, candidate) in enumerate(zip(cand_cols, current_task["candidates"])):
        with col:
            st.image(candidate["img"], use_container_width=True)
            st.feedback("stars", key=f"step_{step}_rating_{i}")

st.divider()
st.button("Submit & Next Outfit ➡️", on_click=save_ratings_and_advance, type="primary", use_container_width=True)