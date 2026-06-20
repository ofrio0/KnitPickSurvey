import streamlit as st
import uuid
from datetime import datetime
import os
import random
import gspread
from google.oauth2.service_account import Credentials
import json

# --- 1. CONFIGURATION & STATE INITIALIZATION ---
st.set_page_config(page_title="Knit Pick Eval", layout="wide")

# Google Sheets Authentication setup
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # Pull credentials from Streamlit secrets
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

@st.cache_data
def load_evaluation_data(json_path="survey_manifest.json", max_candidates_per_anchor=5):
    """
    Reads model predictions from JSON. Limits candidates to prevent UI crowding.
    """
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
            
        # Shuffle to mix positives and negatives
        random.shuffle(candidates)
        
        # Enforce the maximum limit so the UI doesn't get crushed
        # This takes the first 5 from the newly shuffled list
        candidates = candidates[:max_candidates_per_anchor] 
        
        tasks.append({
            "anchor_id": str(anchor_id),
            "anchor_img": str(anchor_data.get("img_url", "")),
            "candidates": candidates
        })
        
    random.shuffle(tasks)
    return tasks

tasks = load_evaluation_data()

# --- 3. SUBMISSION LOGIC ---
def save_ratings_and_advance():
    current_task = tasks[st.session_state.current_step]
    records = []
    
    # Collect data for all 5 candidates
    for i, candidate in enumerate(current_task["candidates"]):
        # st.feedback returns 0-4. We add 1 to make it a 1-5 scale.
        # If user skips a rating, it returns None. We default to 3 (neutral) or you can enforce validation.
        raw_rating = st.session_state.get(f"rating_{st.session_state.current_step}_{i}")
        human_score = (raw_rating + 1) if raw_rating is not None else None 
        
        if human_score is not None:
            # Append as a list of values for Google Sheets
            records.append([
                st.session_state.session_id,
                current_task["anchor_id"],
                candidate["id"],
                human_score,
                candidate["model_score"],
                datetime.now().isoformat()
            ])
    
    # Save to Google Sheets
    if records:
        try:
            client = get_gspread_client()
            sheet_url = st.secrets["gcp_service_account"]["sheet_url"]
            sheet = client.open_by_url(sheet_url).sheet1
            sheet.append_rows(records)
        except Exception as e:
            st.error(f"Error saving to Google Sheets: {e}")
            return # Stop advancement so user data isn't lost
    
    # Clear the radio/feedback states for the next screen
    for i in range(len(current_task["candidates"])):
        if f"rating_{i}" in st.session_state:
            del st.session_state[f"rating_{i}"]
            
    # Advance progress
    st.session_state.current_step += 1

# --- 4. UI LAYOUT ---
st.title("Knit Pick: Fashion Compatibility")

if st.session_state.current_step >= len(tasks):
    st.success("You've completed all evaluations! Thank you for your help.")
    st.balloons()
    st.stop()

current_task = tasks[st.session_state.current_step]

# Progress Bar
progress = st.session_state.current_step / len(tasks)
st.progress(progress, text=f"Task {st.session_state.current_step + 1} of {len(tasks)}")

st.markdown("### How well do these outfits match?")
st.write("Rate each combination from 1 star (terrible match) to 5 stars (perfect outfit).")

# Main Layout: 1 column for Anchor, 1 wide column containing a grid for Candidates
col_anchor, col_candidates = st.columns([1, 3.5])

with col_anchor:
    st.markdown("**Anchor**")
    st.image(current_task["anchor_img"], use_container_width=True)
    st.caption(f"ID: {current_task['anchor_id']}")

with col_candidates:
    st.markdown("**Rate Candidates**")
    # Create 5 sub-columns for the candidates
    cand_cols = st.columns(len(current_task["candidates"]))
    
    for i, (col, candidate) in enumerate(zip(cand_cols, current_task["candidates"])):
        with col:
            st.image(candidate["img"], use_container_width=True)
            # The key binds the input to st.session_state so we can read it in the save function
            st.feedback("stars", key=f"rating_{st.session_state.current_step}_{i}")

st.divider()

# Submit Button
# Using a button that calls the callback function ensures data is saved before the UI re-renders
st.button("Submit & Next Outfit ➡️", on_click=save_ratings_and_advance, type="primary", use_container_width=True)