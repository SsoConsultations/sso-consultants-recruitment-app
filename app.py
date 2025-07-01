import streamlit as st
import os
import io
import json
import re
import bcrypt
from datetime import datetime
import time

# --- Supabase Imports ---
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
from postgrest.exceptions import Exception # For Supabase API errors

# --- AI & Document Processing Imports ---
from openai import OpenAI
import pandas as pd
from PyPDF2 import PdfReader
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_ALIGN_VERTICAL

# --- Streamlit Page Configuration (MUST BE THE FIRST ST COMMAND) ---
st.set_page_config(
    page_title="SSO Consultants AI Recruitment",
    page_icon="�",
    layout="wide"
)

# --- Custom CSS for Styling ---
st.markdown(
    """
    <style>
    /* Global base styling - pure white background, pure black text by default */
    body {
        background-color: #FFFFFF; /* Pure white background */
        color: #000000 !important; /* Pure black for general text readability - CRITICAL */
        font-family: 'Inter', sans-serif;
    }

    /* Hide Streamlit header and footer by default */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Custom styling for the main content area to center it */
    .stApp {
        max-width: 1200px; /* Max width for content */
        margin: auto; /* Center the content */
        padding-top: 20px; /* Add some padding at the top */
        padding-bottom: 80px; /* Space for the fixed footer */
    }

    /* Streamlit specific adjustments for better aesthetics */
    .stButton>button {
        background-color: #FF8C00; /* Orange background for buttons */
        color: white !important; /* White text for buttons */
        border-radius: 8px; /* Rounded corners for buttons */
        border: none;
        padding: 10px 20px;
        font-weight: bold;
        transition: background-color 0.3s;
    }
    .stButton>button:hover {
        background-color: #FFA500; /* Lighter orange on hover */
    }

    /* Text input and text area styling */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        border-radius: 8px;
        border: 1px solid #E0E0E0; /* Light grey border */
        padding: 10px;
        color: #000000; /* Black text for inputs */
    }

    /* Markdown styling for headers and text */
    h1, h2, h3, h4, h5, h6 {
        color: #FF8C00; /* Orange for headers */
        font-weight: bold;
    }
    .stMarkdown {
        color: #000000; /* Ensure markdown text is black */
    }

    /* Specific style for success/error messages */
    .stAlert {
        border-radius: 8px;
    }

    /* Centering specific elements like images or logos */
    .center-image {
        display: block;
        margin-left: auto;
        margin-right: auto;
        width: 50%; /* Adjust as needed */
    }

    /* Custom styling for the main title */
    .main-title {
        text-align: center;
        color: #FF8C00; /* Orange */
        font-size: 2.5em;
        margin-bottom: 30px;
        font-weight: bold;
    }

    /* Custom styling for the sub-header */
    .sub-header {
        text-align: center;
        color: #000000; /* Black */
        font-size: 1.2em;
        margin-bottom: 40px;
    }

    /* Sidebar styling */
    .css-1d391kg, .css-1lcbmhc { /* Streamlit sidebar classes */
        background-color: #F8F8F8; /* Light grey background for sidebar */
        color: #000000; /* Black text for sidebar */
    }

    /* Ensure selectbox and multiselect options are readable */
    .stSelectbox>div>div, .stMultiSelect>div>div {
        color: #000000;
    }
    .stSelectbox>div>div>div>div, .stMultiSelect>div>div>div>div {
        color: #000000;
    }

    /* Adjustments for the file uploader */
    .stFileUploader label {
        color: #000000; /* Black text for file uploader label */
    }

    /* Custom styling for the "Powered by" text */
    .powered-by {
        text-align: center;
        font-size: 0.9em;
        color: #888888; /* Grey color */
        margin-top: 20px;
    }

    /* Adjustments for expander */
    .streamlit-expanderHeader {
        background-color: #F0F0F0; /* Light grey for expander header */
        color: #000000; /* Black text */
        border-radius: 8px;
        padding: 10px;
    }
    .streamlit-expanderContent {
        background-color: #FFFFFF; /* White for expander content */
        border: 1px solid #E0E0E0;
        border-top: none;
        border-radius: 0 0 8px 8px;
        padding: 15px;
    }

    /* Ensure all text is black by default unless specified */
    p, li, div, span, a {
        color: #000000;
    }

    /* Specific styling for the AI-generated response text */
    .ai-response-box {
        background-color: #F9F9F9;
        border-left: 5px solid #FF8C00;
        padding: 15px;
        border-radius: 8px;
        margin-top: 20px;
        color: #000000; /* Ensure text inside is black */
    }

    /* Styling for the application status badges */
    .status-badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 5px;
        font-weight: bold;
        color: white;
        text-align: center;
    }
    .status-Pending { background-color: #FFC107; } /* Amber */
    .status-Reviewed { background-color: #17A2B8; } /* Info Blue */
    .status-Interview { background-color: #28A745; } /* Success Green */
    .status-Rejected { background-color: #DC3545; } /* Danger Red */
    .status-Hired { background-color: #6F42C1; } /* Purple */
    </style>
    """,
    unsafe_allow_html=True
)

# --- Global Constants and Configuration ---
# Supabase Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Initialize Supabase Client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(postgrest_client_timeout=10))
    st.session_state['supabase_client'] = supabase
    print("Supabase client initialized successfully.")
except Exception as e:
    st.error(f"Error initializing Supabase: {e}. Please check your environment variables.")
    st.stop() # Stop the app if Supabase cannot be initialized

# OpenAI API Key
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if OPENAI_API_KEY:
    client_openai = OpenAI(api_key=OPENAI_API_KEY)
else:
    st.warning("OpenAI API key not found. AI features will be disabled.")
    client_openai = None

# Admin Credentials (for a hardcoded admin user, outside Supabase Auth)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sso.com")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", bcrypt.hashpw("adminpass".encode('utf-8'), bcrypt.gensalt()).decode('utf-8'))

# --- Session State Initialization ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_email' not in st.session_state:
    st.session_state['user_email'] = None
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = None # 'admin', 'recruiter', 'candidate'
if 'login_mode' not in st.session_state:
    st.session_state['login_mode'] = 'user' # 'user' or 'admin' for login form

# --- Helper Functions for Supabase Operations ---

def get_supabase_client():
    if 'supabase_client' not in st.session_state:
        st.error("Supabase client not initialized.")
        st.stop()
    return st.session_state['supabase_client']

# --- Auth Operations ---
def login_user(email, password, login_as_admin_attempt=False):
    supabase = get_supabase_client()
    try:
        if login_as_admin_attempt:
            # Check against hardcoded admin credentials
            if email == ADMIN_EMAIL and bcrypt.checkpw(password.encode('utf-8'), ADMIN_PASSWORD_HASH.encode('utf-8')):
                st.session_state['logged_in'] = True
                st.session_state['user_email'] = email
                st.session_state['user_role'] = 'admin'
                st.success("Admin login successful!")
                st.rerun()
            else:
                st.error("Invalid admin credentials.")
                print(f"DEBUG (login_user): Admin login failed for {email}.")
                return False
        else:
            # Attempt to sign in via Supabase Auth
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            if response.user:
                st.session_state['logged_in'] = True
                st.session_state['user_email'] = response.user.email
                # Fetch user's role from your 'users' table
                user_data = get_user_data(response.user.id)
                st.session_state['user_role'] = user_data['role'] if user_data and 'role' in user_data else 'candidate' # Default role
                st.success(f"Welcome, {st.session_state['user_email']}!")
                st.rerun()
                return True
            else:
                st.error("Invalid email or password.")
                print(f"DEBUG (login_user): Supabase login failed for {email}. Response: {response}")
                return False
    except Exception as e:
        st.error(f"Login error: {e.message}")
        print(f"DEBUG (login_user): Supabase API error during login for {email}: {e.message}")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred during login: {e}")
        print(f"DEBUG (login_user): Unexpected error during login for {email}: {e}")
        return False

def register_user(email, password, role='candidate'):
    supabase = get_supabase_client()
    try:
        response = supabase.auth.sign_up({"email": email, "password": password})
        if response.user:
            # Save user data to your 'users' table after successful signup
            user_id = response.user.id
            user_data = {
                "id": user_id, # Supabase user ID
                "email": email,
                "role": role,
                "created_at": datetime.now().isoformat()
            }
            save_user_data(user_data)
            st.success("Registration successful! Please check your email to verify your account.")
            return True
        else:
            st.error(f"Registration failed: {response.session}")
            print(f"DEBUG (register_user): Supabase signup failed for {email}. Response: {response}")
            return False
    except Exception as e:
        st.error(f"Registration error: {e.message}")
        print(f"DEBUG (register_user): Supabase API error during registration for {email}: {e.message}")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred during registration: {e}")
        print(f"DEBUG (register_user): Unexpected error during registration for {email}: {e}")
        return False

def reset_password(email):
    supabase = get_supabase_client()
    try:
        # Supabase sends a password reset email
        response = supabase.auth.reset_password_for_email(email)
        if response: # Supabase's reset_password_for_email doesn't return a user object directly
            st.success("Password reset email sent. Please check your inbox.")
            return True
        else:
            st.error("Failed to send password reset email. Please try again.")
            return False
    except Exception as e:
        st.error(f"Password reset error: {e.message}")
        print(f"DEBUG (reset_password): Supabase API error during password reset for {email}: {e.message}")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred during password reset: {e}")
        print(f"DEBUG (reset_password): Unexpected error during password reset for {email}: {e}")
        return False

def logout_user():
    supabase = get_supabase_client()
    try:
        supabase.auth.sign_out()
        st.session_state['logged_in'] = False
        st.session_state['user_email'] = None
        st.session_state['user_role'] = None
        st.success("Logged out successfully.")
        st.rerun()
    except Exception as e:
        st.error(f"Error logging out: {e}")
        print(f"DEBUG (logout_user): Error during logout: {e}")

# --- Database Operations (Supabase PostgreSQL) ---

# Generic CRUD for 'users'
def get_user_data(user_id):
    supabase = get_supabase_client()
    try:
        response = supabase.table('users').select('*').eq('id', user_id).single().execute()
        return response.data
    except Exception as e:
        if "PGRST204" in e.message: # No rows found
            return None
        st.error(f"Error fetching user data: {e.message}")
        print(f"DEBUG (get_user_data): Error fetching user {user_id}: {e.message}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while fetching user data: {e}")
        print(f"DEBUG (get_user_data): Unexpected error fetching user {user_id}: {e}")
        return None

def save_user_data(data):
    supabase = get_supabase_client()
    try:
        # Using upsert to either insert new or update existing based on 'id'
        response = supabase.table('users').upsert(data).execute()
        return response.data
    except Exception as e:
        st.error(f"Error saving user data: {e}")
        print(f"DEBUG (save_user_data): Error saving user data: {e}")
        return None

def update_user_data(user_id, data):
    supabase = get_supabase_client()
    try:
        response = supabase.table('users').update(data).eq('id', user_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error updating user data: {e}")
        print(f"DEBUG (update_user_data): Error updating user {user_id}: {e}")
        return None

def delete_user_data(user_id):
    supabase = get_supabase_client()
    try:
        response = supabase.table('users').delete().eq('id', user_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error deleting user data: {e}")
        print(f"DEBUG (delete_user_data): Error deleting user {user_id}: {e}")
        return None

# Operations for Candidates
def get_all_candidates():
    supabase = get_supabase_client()
    try:
        response = supabase.table('candidates').select('*').execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching candidates: {e}")
        print(f"DEBUG (get_all_candidates): Error fetching candidates: {e}")
        return []

def get_candidate_by_id(candidate_id):
    supabase = get_supabase_client()
    try:
        response = supabase.table('candidates').select('*').eq('id', candidate_id).single().execute()
        return response.data
    except Exception as e:
        if "PGRST204" in e.message:
            return None
        st.error(f"Error fetching candidate: {e.message}")
        print(f"DEBUG (get_candidate_by_id): Error fetching candidate {candidate_id}: {e.message}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while fetching candidate: {e}")
        print(f"DEBUG (get_candidate_by_id): Unexpected error fetching candidate {candidate_id}: {e}")
        return None

def add_candidate_profile(data):
    supabase = get_supabase_client()
    try:
        response = supabase.table('candidates').insert(data).execute()
        return response.data
    except Exception as e:
        st.error(f"Error adding candidate profile: {e}")
        print(f"DEBUG (add_candidate_profile): Error adding candidate profile: {e}")
        return None

def update_candidate_profile(candidate_id, data):
    supabase = get_supabase_client()
    try:
        response = supabase.table('candidates').update(data).eq('id', candidate_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error updating candidate profile: {e}")
        print(f"DEBUG (update_candidate_profile): Error updating candidate {candidate_id}: {e}")
        return None

def delete_candidate_profile(candidate_id):
    supabase = get_supabase_client()
    try:
        response = supabase.table('candidates').delete().eq('id', candidate_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error deleting candidate profile: {e}")
        print(f"DEBUG (delete_candidate_profile): Error deleting candidate {candidate_id}: {e}")
        return None

# Operations for Jobs
def get_all_jobs():
    supabase = get_supabase_client()
    try:
        response = supabase.table('jobs').select('*').execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching jobs: {e}")
        print(f"DEBUG (get_all_jobs): Error fetching jobs: {e}")
        return []

def get_job_by_id(job_id):
    supabase = get_supabase_client()
    try:
        response = supabase.table('jobs').select('*').eq('id', job_id).single().execute()
        return response.data
    except Exception as e:
        if "PGRST204" in e.message:
            return None
        st.error(f"Error fetching job: {e.message}")
        print(f"DEBUG (get_job_by_id): Error fetching job {job_id}: {e.message}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while fetching job: {e}")
        print(f"DEBUG (get_job_by_id): Unexpected error fetching job {job_id}: {e}")
        return None

def add_job_posting(data):
    supabase = get_supabase_client()
    try:
        response = supabase.table('jobs').insert(data).execute()
        return response.data
    except Exception as e:
        st.error(f"Error adding job posting: {e}")
        print(f"DEBUG (add_job_posting): Error adding job posting: {e}")
        return None

def update_job_posting(job_id, data):
    supabase = get_supabase_client()
    try:
        response = supabase.table('jobs').update(data).eq('id', job_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error updating job posting: {e}")
        print(f"DEBUG (update_job_posting): Error updating job {job_id}: {e}")
        return None

def delete_job_posting(job_id):
    supabase = get_supabase_client()
    try:
        response = supabase.table('jobs').delete().eq('id', job_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error deleting job posting: {e}")
        print(f"DEBUG (delete_job_posting): Error deleting job {job_id}: {e}")
        return None

# Operations for Applications
def add_application(data):
    supabase = get_supabase_client()
    try:
        response = supabase.table('applications').insert(data).execute()
        return response.data
    except Exception as e:
        st.error(f"Error submitting application: {e}")
        print(f"DEBUG (add_application): Error submitting application: {e}")
        return None

def get_applications_by_job_id(job_id):
    supabase = get_supabase_client()
    try:
        response = supabase.table('applications').select('*').eq('job_id', job_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching applications for job {job_id}: {e}")
        print(f"DEBUG (get_applications_by_job_id): Error fetching applications for job {job_id}: {e}")
        return []

def get_applications_by_candidate_id(candidate_id):
    supabase = get_supabase_client()
    try:
        response = supabase.table('applications').select('*').eq('candidate_id', candidate_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching applications for candidate {candidate_id}: {e}")
        print(f"DEBUG (get_applications_by_candidate_id): Error fetching applications for candidate {candidate_id}: {e}")
        return []

def update_application_status(application_id, new_status):
    supabase = get_supabase_client()
    try:
        response = supabase.table('applications').update({"status": new_status}).eq('id', application_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error updating application status: {e}")
        print(f"DEBUG (update_application_status): Error updating application {application_id} status to {new_status}: {e}")
        return None

# --- Storage Operations (Supabase Storage) ---
def upload_file_to_supabase(bucket_name, file_path_in_storage, file_bytes):
    supabase = get_supabase_client()
    try:
        response = supabase.storage.from_(bucket_name).upload(file_path_in_storage, file_bytes)
        if response.status_code in [200, 201]: # 200 for existing, 201 for new
            public_url_response = supabase.storage.from_(bucket_name).get_public_url(file_path_in_storage)
            return public_url_response
        else:
            print(f"DEBUG (upload_file_to_supabase): Supabase upload failed: {response.status_code}, {response.json()}")
            return None
    except Exception as e:
        st.error(f"Error uploading file to storage: {e}")
        print(f"DEBUG (upload_file_to_supabase): Error uploading file to {bucket_name}/{file_path_in_storage}: {e}")
        return None

def download_file_from_supabase(bucket_name, file_path_in_storage):
    supabase = get_supabase_client()
    try:
        response = supabase.storage.from_(bucket_name).download(file_path_in_storage)
        if response:
            return response # Returns bytes
        else:
            print(f"DEBUG (download_file_from_supabase): Supabase download failed for {file_path_in_storage}: No content received.")
            return None
    except Exception as e:
        st.error(f"Error downloading file from storage: {e}")
        print(f"DEBUG (download_file_from_supabase): Error downloading file from {bucket_name}/{file_path_in_storage}: {e}")
        return None

def delete_file_from_supabase(bucket_name, file_path_in_storage):
    supabase = get_supabase_client()
    try:
        response = supabase.storage.from_(bucket_name).remove([file_path_in_storage])
        if response.status_code == 200:
            return True
        else:
            print(f"DEBUG (delete_file_from_supabase): Supabase delete failed: {response.status_code}, {response.json()}")
            return False
    except Exception as e:
        st.error(f"Error deleting file from storage: {e}")
        print(f"DEBUG (delete_file_from_supabase): Error deleting file from {bucket_name}/{file_path_in_storage}: {e}")
        return False

# --- AI and Document Processing Functions (No change, as they are independent of backend) ---

def extract_text_from_pdf(pdf_file):
    pdf_reader = PdfReader(pdf_file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() or ""
    return text

def extract_text_from_docx(docx_file):
    document = Document(docx_file)
    text = ""
    for paragraph in document.paragraphs:
        text += paragraph.text + "\n"
    return text

def generate_resume_summary(resume_text):
    if not client_openai:
        st.warning("OpenAI client not initialized. Cannot generate summary.")
        return "AI features are disabled."
    try:
        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an AI assistant that summarizes resumes."},
                {"role": "user", "content": f"Summarize the following resume text:\n\n{resume_text}"}
            ],
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"Error generating resume summary: {e}")
        return "Error generating summary."

def generate_job_description_summary(job_description_text):
    if not client_openai:
        st.warning("OpenAI client not initialized. Cannot generate summary.")
        return "AI features are disabled."
    try:
        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an AI assistant that summarizes job descriptions."},
                {"role": "user", "content": f"Summarize the following job description:\n\n{job_description_text}"}
            ],
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"Error generating job description summary: {e}")
        return "Error generating summary."

def match_resume_to_job(resume_text, job_description_text):
    if not client_openai:
        st.warning("OpenAI client not initialized. Cannot perform matching.")
        return "AI features are disabled."
    try:
        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an AI assistant that matches resumes to job descriptions and provides a match percentage and key reasons."},
                {"role": "user", "content": f"Given the following resume and job description, provide a match percentage and key reasons for the match. Focus on skills, experience, and qualifications.\n\nResume:\n{resume_text}\n\nJob Description:\n{job_description_text}"}
            ],
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"Error matching resume to job: {e}")
        return "Error performing match."

# --- Streamlit UI Pages ---

def show_home_page():
    st.markdown("<h1 class='main-title'>Welcome to SSO Consultants AI Recruitment</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Your intelligent partner for seamless hiring.</p>", unsafe_allow_html=True)

    st.image("https://placehold.co/600x300/FF8C00/FFFFFF?text=SSO+Consultants+AI", use_column_width=True)

    st.markdown("""
        <div style="background-color: #F9F9F9; padding: 20px; border-radius: 10px; margin-top: 30px;">
            <h3 style="color: #FF8C00;">About Us</h3>
            <p style="color: #000000;">
                SSO Consultants leverages cutting-edge AI to revolutionize the recruitment process.
                From intelligent resume parsing to precise job matching and streamlined application management,
                we empower recruiters to find the perfect candidates faster and candidates to discover their dream jobs.
            </p>
            <h3 style="color: #FF8C00; margin-top: 20px;">Our Features</h3>
            <ul style="color: #000000;">
                <li>AI-powered resume analysis and summarization.</li>
                <li>Intelligent job description generation and summarization.</li>
                <li>Automated resume-to-job matching with detailed insights.</li>
                <li>Comprehensive candidate and job posting management.</li>
                <li>Streamlined application tracking and status updates.</li>
            </ul>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<p class='powered-by'>Powered by Supabase & OpenAI</p>", unsafe_allow_html=True)


def show_recruiter_dashboard():
    st.markdown("<h2 style='text-align: center; color: #FF8C00;'>Recruiter Dashboard</h2>", unsafe_allow_html=True)
    st.write(f"Welcome, {st.session_state['user_email']} ({st.session_state['user_role']})!")

    tab1, tab2, tab3 = st.tabs(["Manage Job Postings", "View Candidates", "Manage Applications"])

    with tab1:
        st.subheader("Manage Job Postings")
        jobs = get_all_jobs()
        if st.button("Add New Job Posting", key="add_job_btn"):
            st.session_state['current_page'] = 'add_job'
            st.rerun()

        if jobs:
            df_jobs = pd.DataFrame(jobs)
            st.dataframe(df_jobs, use_container_width=True)

            col_edit, col_delete = st.columns(2)
            with col_edit:
                job_id_to_edit = st.text_input("Enter Job ID to Edit:")
                if st.button("Edit Job", key="edit_job_btn") and job_id_to_edit:
                    job_to_edit = get_job_by_id(job_id_to_edit)
                    if job_to_edit:
                        st.session_state['job_to_edit'] = job_to_edit
                        st.session_state['current_page'] = 'edit_job'
                        st.rerun()
                    else:
                        st.error("Job not found.")
            with col_delete:
                job_id_to_delete = st.text_input("Enter Job ID to Delete:")
                if st.button("Delete Job", key="delete_job_btn") and job_id_to_delete:
                    if delete_job_posting(job_id_to_delete):
                        st.success("Job deleted successfully.")
                        st.rerun()
                    else:
                        st.error("Failed to delete job.")
        else:
            st.info("No job postings available. Add one!")

    with tab2:
        st.subheader("View All Candidates")
        candidates = get_all_candidates()
        if candidates:
            df_candidates = pd.DataFrame(candidates)
            st.dataframe(df_candidates, use_container_width=True)

            candidate_id_to_view = st.text_input("Enter Candidate ID to View Profile:")
            if st.button("View Candidate Profile", key="view_candidate_btn") and candidate_id_to_view:
                candidate_profile = get_candidate_by_id(candidate_id_to_view)
                if candidate_profile:
                    st.session_state['candidate_to_view'] = candidate_profile
                    st.session_state['current_page'] = 'view_candidate_profile'
                    st.rerun()
                else:
                    st.error("Candidate not found.")
        else:
            st.info("No candidate profiles available.")

    with tab3:
        st.subheader("Manage Job Applications")
        jobs_for_applications = get_all_jobs()
        if jobs_for_applications:
            job_titles = {job['id']: job['title'] for job in jobs_for_applications}
            selected_job_id = st.selectbox("Select a Job to View Applications:", options=list(job_titles.keys()), format_func=lambda x: job_titles[x])

            if selected_job_id:
                applications = get_applications_by_job_id(selected_job_id)
                if applications:
                    st.write(f"Applications for: **{job_titles[selected_job_id]}**")
                    for app in applications:
                        candidate_info = get_candidate_by_id(app['candidate_id'])
                        candidate_name = candidate_info['name'] if candidate_info else "N/A"
                        st.markdown(f"""
                            <div style="border: 1px solid #E0E0E0; border-radius: 8px; padding: 15px; margin-bottom: 10px; background-color: #FFFFFF;">
                                <p><strong>Candidate:</strong> {candidate_name}</p>
                                <p><strong>Applied On:</strong> {app['applied_date']}</p>
                                <p><strong>Status:</strong> <span class='status-badge status-{app['status']}'>{app['status']}</span></p>
                                <p><strong>Resume URL:</strong> <a href="{app['resume_url']}" target="_blank" style="color: #FF8C00;">View Resume</a></p>
                            </div>
                        """, unsafe_allow_html=True)
                        new_status = st.selectbox(
                            f"Update status for {candidate_name} (Application ID: {app['id']}):",
                            options=["Pending", "Reviewed", "Interview", "Rejected", "Hired"],
                            index=["Pending", "Reviewed", "Interview", "Rejected", "Hired"].index(app['status']),
                            key=f"status_select_{app['id']}"
                        )
                        if st.button(f"Update Status for {candidate_name}", key=f"update_status_btn_{app['id']}"):
                            if update_application_status(app['id'], new_status):
                                st.success(f"Status updated to {new_status} for {candidate_name}.")
                                st.rerun()
                            else:
                                st.error("Failed to update status.")
                        st.markdown("---")
                else:
                    st.info("No applications for this job yet.")
        else:
            st.info("No jobs available to view applications for.")


def show_candidate_dashboard():
    st.markdown("<h2 style='text-align: center; color: #FF8C00;'>Candidate Dashboard</h2>", unsafe_allow_html=True)
    st.write(f"Welcome, {st.session_state['user_email']} ({st.session_state['user_role']})!")

    tab1, tab2, tab3 = st.tabs(["My Profile", "Browse Jobs", "My Applications"])

    with tab1:
        st.subheader("My Profile")
        user_id = supabase.auth.get_user().user.id # Get current Supabase user ID
        candidate_profile = get_candidate_by_id(user_id) # Assuming candidate ID is same as user ID

        if candidate_profile:
            st.write(f"**Name:** {candidate_profile.get('name', 'N/A')}")
            st.write(f"**Email:** {candidate_profile.get('email', 'N/A')}")
            st.write(f"**Skills:** {candidate_profile.get('skills', 'N/A')}")
            st.write(f"**Experience:** {candidate_profile.get('experience', 'N/A')}")
            if candidate_profile.get('resume_url'):
                st.markdown(f"**Resume:** [View Resume]({candidate_profile['resume_url']})", unsafe_allow_html=True)

            if st.button("Edit Profile", key="edit_candidate_profile_btn"):
                st.session_state['candidate_to_edit'] = candidate_profile
                st.session_state['current_page'] = 'edit_candidate_profile'
                st.rerun()
        else:
            st.info("You don't have a candidate profile yet. Create one!")
            if st.button("Create Profile", key="create_candidate_profile_btn"):
                st.session_state['current_page'] = 'create_candidate_profile'
                st.rerun()

    with tab2:
        st.subheader("Browse Available Jobs")
        jobs = get_all_jobs()
        if jobs:
            for job in jobs:
                with st.expander(f"**{job['title']}** at {job['company']}"):
                    st.write(f"**Location:** {job['location']}")
                    st.write(f"**Salary:** {job['salary']}")
                    st.write(f"**Description:** {job['description']}")
                    st.write(f"**Requirements:** {job['requirements']}")
                    st.write(f"**Posted On:** {job['posted_date']}")

                    if st.button(f"Apply for {job['title']}", key=f"apply_job_{job['id']}"):
                        st.session_state['job_to_apply'] = job
                        st.session_state['current_page'] = 'apply_for_job'
                        st.rerun()
                    st.markdown("---")
        else:
            st.info("No jobs available at the moment. Check back later!")

    with tab3:
        st.subheader("My Applications")
        user_id = supabase.auth.get_user().user.id
        my_applications = get_applications_by_candidate_id(user_id)

        if my_applications:
            for app in my_applications:
                job_info = get_job_by_id(app['job_id'])
                job_title = job_info['title'] if job_info else "N/A"
                st.markdown(f"""
                    <div style="border: 1px solid #E0E0E0; border-radius: 8px; padding: 15px; margin-bottom: 10px; background-color: #FFFFFF;">
                        <p><strong>Job Title:</strong> {job_title}</p>
                        <p><strong>Applied On:</strong> {app['applied_date']}</p>
                        <p><strong>Status:</strong> <span class='status-badge status-{app['status']}'>{app['status']}</span></p>
                        <p><strong>Resume Used:</strong> <a href="{app['resume_url']}" target="_blank" style="color: #FF8C00;">View Resume</a></p>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown("---")
        else:
            st.info("You haven't applied for any jobs yet.")

def show_add_job_page():
    st.markdown("<h2 style='text-align: center; color: #FF8C00;'>Add New Job Posting</h2>", unsafe_allow_html=True)
    with st.form("add_job_form"):
        title = st.text_input("Job Title", placeholder="e.g., Senior Software Engineer")
        company = st.text_input("Company Name", placeholder="e.g., Tech Solutions Inc.")
        location = st.text_input("Location", placeholder="e.g., Remote, New York, London")
        salary = st.text_input("Salary", placeholder="e.g., $100,000 - $150,000 annually")
        description = st.text_area("Job Description", height=200, placeholder="Provide a detailed description of the role.")
        requirements = st.text_area("Key Requirements", height=150, placeholder="List essential skills and qualifications.")
        posted_date = st.date_input("Posted Date", datetime.now().date())

        submit_button = st.form_submit_button("Add Job")

        if submit_button:
            if title and company and description and requirements:
                job_data = {
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary": salary,
                    "description": description,
                    "requirements": requirements,
                    "posted_date": posted_date.isoformat(),
                    "created_by": st.session_state['user_email'] # Store who created it
                }
                if add_job_posting(job_data):
                    st.success("Job posting added successfully!")
                    st.session_state['current_page'] = 'recruiter_dashboard'
                    st.rerun()
                else:
                    st.error("Failed to add job posting.")
            else:
                st.warning("Please fill in all required fields (Title, Company, Description, Requirements).")
    if st.button("Back to Dashboard", key="back_to_recruiter_dashboard_from_add_job"):
        st.session_state['current_page'] = 'recruiter_dashboard'
        st.rerun()

def show_edit_job_page():
    st.markdown("<h2 style='text-align: center; color: #FF8C00;'>Edit Job Posting</h2>", unsafe_allow_html=True)
    job_to_edit = st.session_state.get('job_to_edit')
    if not job_to_edit:
        st.error("No job selected for editing.")
        if st.button("Back to Dashboard", key="back_to_recruiter_dashboard_from_edit_job_no_job"):
            st.session_state['current_page'] = 'recruiter_dashboard'
            st.rerun()
        return

    with st.form("edit_job_form"):
        st.write(f"Editing Job ID: **{job_to_edit['id']}**")
        title = st.text_input("Job Title", value=job_to_edit.get('title', ''))
        company = st.text_input("Company Name", value=job_to_edit.get('company', ''))
        location = st.text_input("Location", value=job_to_edit.get('location', ''))
        salary = st.text_input("Salary", value=job_to_edit.get('salary', ''))
        description = st.text_area("Job Description", value=job_to_edit.get('description', ''), height=200)
        requirements = st.text_area("Key Requirements", value=job_to_edit.get('requirements', ''), height=150)
        posted_date_str = job_to_edit.get('posted_date', datetime.now().isoformat())
        posted_date = st.date_input("Posted Date", value=datetime.fromisoformat(posted_date_str).date())

        submit_button = st.form_submit_button("Update Job")

        if submit_button:
            if title and company and description and requirements:
                updated_data = {
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary": salary,
                    "description": description,
                    "requirements": requirements,
                    "posted_date": posted_date.isoformat()
                }
                if update_job_posting(job_to_edit['id'], updated_data):
                    st.success("Job posting updated successfully!")
                    del st.session_state['job_to_edit']
                    st.session_state['current_page'] = 'recruiter_dashboard'
                    st.rerun()
                else:
                    st.error("Failed to update job posting.")
            else:
                st.warning("Please fill in all required fields.")
    if st.button("Back to Dashboard", key="back_to_recruiter_dashboard_from_edit_job"):
        del st.session_state['job_to_edit']
        st.session_state['current_page'] = 'recruiter_dashboard'
        st.rerun()

def show_create_candidate_profile_page():
    st.markdown("<h2 style='text-align: center; color: #FF8C00;'>Create Candidate Profile</h2>", unsafe_allow_html=True)
    user_id = supabase.auth.get_user().user.id # Get current Supabase user ID

    with st.form("create_candidate_profile_form"):
        name = st.text_input("Full Name", placeholder="e.g., Jane Doe")
        email = st.text_input("Email (auto-filled)", value=st.session_state['user_email'], disabled=True)
        skills = st.text_area("Skills (comma-separated)", placeholder="e.g., Python, SQL, Machine Learning, AWS")
        experience = st.text_area("Experience Summary", height=150, placeholder="Briefly describe your professional experience.")
        resume_file = st.file_uploader("Upload Resume (PDF or DOCX)", type=["pdf", "docx"])

        submit_button = st.form_submit_button("Create Profile")

        if submit_button:
            if name and skills and experience and resume_file:
                resume_url = None
                if resume_file:
                    file_bytes = resume_file.read()
                    file_extension = os.path.splitext(resume_file.name)[1]
                    # Use user_id as part of the file path to ensure uniqueness and user-specificity
                    file_path_in_storage = f"resumes/{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{file_extension}"
                    resume_url = upload_file_to_supabase("app_files", file_path_in_storage, file_bytes) # Use a dedicated bucket

                if resume_url:
                    candidate_data = {
                        "id": user_id, # Link candidate profile to Supabase Auth user ID
                        "name": name,
                        "email": email,
                        "skills": skills,
                        "experience": experience,
                        "resume_url": resume_url,
                        "created_at": datetime.now().isoformat()
                    }
                    if add_candidate_profile(candidate_data):
                        st.success("Candidate profile created successfully!")
                        st.session_state['current_page'] = 'candidate_dashboard'
                        st.rerun()
                    else:
                        st.error("Failed to create candidate profile in database.")
                else:
                    st.error("Failed to upload resume. Please try again.")
            else:
                st.warning("Please fill in all required fields and upload your resume.")
    if st.button("Back to Dashboard", key="back_to_candidate_dashboard_from_create_profile"):
        st.session_state['current_page'] = 'candidate_dashboard'
        st.rerun()

def show_edit_candidate_profile_page():
    st.markdown("<h2 style='text-align: center; color: #FF8C00;'>Edit Candidate Profile</h2>", unsafe_allow_html=True)
    candidate_profile = st.session_state.get('candidate_to_edit')
    if not candidate_profile:
        st.error("No candidate profile selected for editing.")
        if st.button("Back to Dashboard", key="back_to_candidate_dashboard_from_edit_profile_no_profile"):
            st.session_state['current_page'] = 'candidate_dashboard'
            st.rerun()
        return

    user_id = supabase.auth.get_user().user.id # Get current Supabase user ID

    with st.form("edit_candidate_profile_form"):
        name = st.text_input("Full Name", value=candidate_profile.get('name', ''))
        email = st.text_input("Email (auto-filled)", value=candidate_profile.get('email', ''), disabled=True)
        skills = st.text_area("Skills (comma-separated)", value=candidate_profile.get('skills', ''))
        experience = st.text_area("Experience Summary", value=candidate_profile.get('experience', ''), height=150)
        current_resume_url = candidate_profile.get('resume_url')
        if current_resume_url:
            st.markdown(f"**Current Resume:** [View]({current_resume_url})", unsafe_allow_html=True)
        resume_file = st.file_uploader("Upload New Resume (PDF or DOCX) (Optional)", type=["pdf", "docx"])

        submit_button = st.form_submit_button("Update Profile")

        if submit_button:
            if name and skills and experience:
                updated_resume_url = current_resume_url
                if resume_file:
                    file_bytes = resume_file.read()
                    file_extension = os.path.splitext(resume_file.name)[1]
                    file_path_in_storage = f"resumes/{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{file_extension}"
                    new_url = upload_file_to_supabase("app_files", file_path_in_storage, file_bytes)
                    if new_url:
                        updated_resume_url = new_url
                        # Optional: Delete old resume if a new one is uploaded
                        # if current_resume_url:
                        #     old_file_path = current_resume_url.split("app_files/")[1] # Extract path from URL
                        #     delete_file_from_supabase("app_files", old_file_path)
                    else:
                        st.error("Failed to upload new resume. Profile not updated.")
                        return

                updated_data = {
                    "name": name,
                    "skills": skills,
                    "experience": experience,
                    "resume_url": updated_resume_url
                }
                if update_candidate_profile(user_id, updated_data):
                    st.success("Candidate profile updated successfully!")
                    del st.session_state['candidate_to_edit']
                    st.session_state['current_page'] = 'candidate_dashboard'
                    st.rerun()
                else:
                    st.error("Failed to update candidate profile.")
            else:
                st.warning("Please fill in all required fields.")
    if st.button("Back to Dashboard", key="back_to_candidate_dashboard_from_edit_profile"):
        del st.session_state['candidate_to_edit']
        st.session_state['current_page'] = 'candidate_dashboard'
        st.rerun()

def show_apply_for_job_page():
    st.markdown("<h2 style='text-align: center; color: #FF8C00;'>Apply for Job</h2>", unsafe_allow_html=True)
    job = st.session_state.get('job_to_apply')
    if not job:
        st.error("No job selected to apply for.")
        if st.button("Back to Browse Jobs", key="back_to_browse_jobs_no_job"):
            st.session_state['current_page'] = 'candidate_dashboard'
            st.rerun()
        return

    st.write(f"Applying for: **{job['title']}** at **{job['company']}**")
    st.markdown(f"**Job Description:** {job['description']}")

    user_id = supabase.auth.get_user().user.id
    candidate_profile = get_candidate_by_id(user_id)

    if not candidate_profile or not candidate_profile.get('resume_url'):
        st.warning("You need a complete profile with a resume to apply. Please create/edit your profile first.")
        if st.button("Go to My Profile", key="go_to_profile_from_apply"):
            st.session_state['current_page'] = 'candidate_dashboard'
            st.rerun()
        return

    st.write(f"Your current resume: [View]({candidate_profile['resume_url']})")

    # AI Matching Section
    st.subheader("AI Resume Match")
    if st.button("Analyze Resume vs. Job Description", key="analyze_match_btn"):
        with st.spinner("Analyzing..."):
            # Download resume to extract text
            resume_bytes = download_file_from_supabase("app_files", candidate_profile['resume_url'].split("app_files/")[1])
            if resume_bytes:
                # Determine file type and extract text
                file_extension = os.path.splitext(candidate_profile['resume_url'])[1].lower()
                resume_text = ""
                if file_extension == '.pdf':
                    resume_text = extract_text_from_pdf(io.BytesIO(resume_bytes))
                elif file_extension == '.docx':
                    resume_text = extract_text_from_docx(io.BytesIO(resume_bytes))
                else:
                    st.error("Unsupported resume file type for AI analysis.")

                if resume_text:
                    match_result = match_resume_to_job(resume_text, job['description'])
                    st.markdown(f"<div class='ai-response-box'>{match_result}</div>", unsafe_allow_html=True)
                else:
                    st.error("Could not extract text from your resume for AI analysis.")
            else:
                st.error("Could not download your resume for AI analysis.")

    if st.button("Confirm Application", key="confirm_application_btn"):
        application_data = {
            "job_id": job['id'],
            "candidate_id": user_id,
            "applied_date": datetime.now().isoformat(),
            "status": "Pending",
            "resume_url": candidate_profile['resume_url'] # Use the URL from candidate's profile
        }
        if add_application(application_data):
            st.success(f"Successfully applied for {job['title']}!")
            del st.session_state['job_to_apply']
            st.session_state['current_page'] = 'candidate_dashboard'
            st.rerun()
        else:
            st.error("Failed to submit application.")

    if st.button("Back to Browse Jobs", key="back_to_browse_jobs_from_apply"):
        del st.session_state['job_to_apply']
        st.session_state['current_page'] = 'candidate_dashboard'
        st.rerun()

def show_view_candidate_profile_page():
    st.markdown("<h2 style='text-align: center; color: #FF8C00;'>Candidate Profile</h2>", unsafe_allow_html=True)
    candidate_profile = st.session_state.get('candidate_to_view')
    if not candidate_profile:
        st.error("No candidate selected to view.")
        if st.button("Back to All Candidates", key="back_to_all_candidates_no_profile"):
            st.session_state['current_page'] = 'recruiter_dashboard'
            st.rerun()
        return

    st.write(f"**Name:** {candidate_profile.get('name', 'N/A')}")
    st.write(f"**Email:** {candidate_profile.get('email', 'N/A')}")
    st.write(f"**Skills:** {candidate_profile.get('skills', 'N/A')}")
    st.write(f"**Experience:** {candidate_profile.get('experience', 'N/A')}")
    if candidate_profile.get('resume_url'):
        st.markdown(f"**Resume:** [View Resume]({candidate_profile['resume_url']})", unsafe_allow_html=True)

    st.subheader("AI Resume Summary")
    if st.button("Generate Resume Summary", key="generate_resume_summary_btn"):
        with st.spinner("Generating summary..."):
            resume_url = candidate_profile.get('resume_url')
            if resume_url:
                # Download resume to extract text
                resume_bytes = download_file_from_supabase("app_files", resume_url.split("app_files/")[1])
                if resume_bytes:
                    file_extension = os.path.splitext(resume_url)[1].lower()
                    resume_text = ""
                    if file_extension == '.pdf':
                        resume_text = extract_text_from_pdf(io.BytesIO(resume_bytes))
                    elif file_extension == '.docx':
                        resume_text = extract_text_from_docx(io.BytesIO(resume_bytes))
                    else:
                        st.error("Unsupported resume file type for AI analysis.")

                    if resume_text:
                        summary = generate_resume_summary(resume_text)
                        st.markdown(f"<div class='ai-response-box'>{summary}</div>", unsafe_allow_html=True)
                    else:
                        st.error("Could not extract text from resume for summary generation.")
                else:
                    st.error("Could not download resume for summary generation.")
            else:
                st.info("No resume available for this candidate to summarize.")

    if st.button("Back to All Candidates", key="back_to_all_candidates_from_view_profile"):
        del st.session_state['candidate_to_view']
        st.session_state['current_page'] = 'recruiter_dashboard'
        st.rerun()

# --- Main Application Logic ---
def main():
    # Sidebar for navigation and authentication
    with st.sidebar:
        st.image("https://placehold.co/150x50/FF8C00/FFFFFF?text=SSO+Logo", use_column_width=True)
        st.markdown("---")

        if st.session_state['logged_in']:
            st.write(f"Logged in as: **{st.session_state['user_email']}**")
            st.write(f"Role: **{st.session_state['user_role'].capitalize()}**")
            st.markdown("---")

            if st.session_state['user_role'] == 'admin' or st.session_state['user_role'] == 'recruiter':
                if st.button("Recruiter Dashboard", key="sidebar_recruiter_dashboard"):
                    st.session_state['current_page'] = 'recruiter_dashboard'
                    st.rerun()
            if st.session_state['user_role'] == 'admin' or st.session_state['user_role'] == 'candidate':
                if st.button("Candidate Dashboard", key="sidebar_candidate_dashboard"):
                    st.session_state['current_page'] = 'candidate_dashboard'
                    st.rerun()

            st.markdown("---")
            if st.button("Logout", key="sidebar_logout"):
                logout_user()
        else:
            st.subheader("Login / Register")
            login_tab, register_tab = st.tabs(["Login", "Register"])

            with login_tab:
                st.markdown(f"<h3>Login as { 'Admin' if st.session_state['login_mode'] == 'admin' else 'User'}</h3>", unsafe_allow_html=True)
                with st.form("login_form"):
                    email = st.text_input("Email")
                    password = st.text_input("Password", type="password")
                    submit_button = st.form_submit_button("Login")
                    if submit_button:
                        print(f"DEBUG (main): Login form submitted for {email}.")
                        if email and password:
                            login_user(email, password, login_as_admin_attempt=(st.session_state['login_mode'] == 'admin'))
                        else:
                            st.warning("Please enter both email and password.")
                # Toggle between user/admin login mode
                if st.session_state['login_mode'] == 'user':
                    if st.button("Login as Admin"):
                        st.session_state['login_mode'] = 'admin'
                        st.rerun()
                else:
                    if st.button("Login as User"):
                        st.session_state['login_mode'] = 'user'
                        st.rerun()

                st.markdown("---")
                if st.button("Forgot Password?", key="forgot_password_btn"):
                    st.session_state['current_page'] = 'forgot_password'
                    st.rerun()

            with register_tab:
                with st.form("register_form"):
                    reg_email = st.text_input("Email", key="reg_email")
                    reg_password = st.text_input("Password", type="password", key="reg_password")
                    reg_role = st.selectbox("Register as:", ["candidate", "recruiter"], key="reg_role")
                    reg_submit_button = st.form_submit_button("Register")
                    if reg_submit_button:
                        if reg_email and reg_password:
                            register_user(reg_email, reg_password, reg_role)
                        else:
                            st.warning("Please enter both email and password.")

    # Main content area based on session state
    if st.session_state['logged_in']:
        if st.session_state.get('current_page') == 'recruiter_dashboard' and (st.session_state['user_role'] == 'recruiter' or st.session_state['user_role'] == 'admin'):
            show_recruiter_dashboard()
        elif st.session_state.get('current_page') == 'add_job' and (st.session_state['user_role'] == 'recruiter' or st.session_state['user_role'] == 'admin'):
            show_add_job_page()
        elif st.session_state.get('current_page') == 'edit_job' and (st.session_state['user_role'] == 'recruiter' or st.session_state['user_role'] == 'admin'):
            show_edit_job_page()
        elif st.session_state.get('current_page') == 'view_candidate_profile' and (st.session_state['user_role'] == 'recruiter' or st.session_state['user_role'] == 'admin'):
            show_view_candidate_profile_page()
        elif st.session_state.get('current_page') == 'candidate_dashboard' and (st.session_state['user_role'] == 'candidate' or st.session_state['user_role'] == 'admin'):
            show_candidate_dashboard()
        elif st.session_state.get('current_page') == 'create_candidate_profile' and (st.session_state['user_role'] == 'candidate' or st.session_state['user_role'] == 'admin'):
            show_create_candidate_profile_page()
        elif st.session_state.get('current_page') == 'edit_candidate_profile' and (st.session_state['user_role'] == 'candidate' or st.session_state['user_role'] == 'admin'):
            show_edit_candidate_profile_page()
        elif st.session_state.get('current_page') == 'apply_for_job' and (st.session_state['user_role'] == 'candidate' or st.session_state['user_role'] == 'admin'):
            show_apply_for_job_page()
        else:
            # Default logged-in view based on role
            if st.session_state['user_role'] == 'recruiter' or st.session_state['user_role'] == 'admin':
                show_recruiter_dashboard()
            elif st.session_state['user_role'] == 'candidate':
                show_candidate_dashboard()
            else:
                show_home_page() # Fallback
    else:
        if st.session_state.get('current_page') == 'forgot_password':
            st.markdown("<h2 style='text-align: center; color: #FF8C00;'>Forgot Password</h2>", unsafe_allow_html=True)
            with st.form("forgot_password_form"):
                email = st.text_input("Enter your email address to reset password:")
                submit_button = st.form_submit_button("Send Reset Link")
                if submit_button:
                    if email:
                        reset_password(email)
                    else:
                        st.warning("Please enter your email.")
            if st.button("Back to Login", key="back_to_login_from_forgot_password"):
                st.session_state['current_page'] = None # Go back to default login view
                st.rerun()
        else:
            show_home_page()

    # --- Custom FOOTER (Always visible at the bottom of the page) ---
    st.markdown(
        """
        <div style="
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            text-align: center;
            color: #FF8C00 !important; /* Orange text for footer - IMPORTANT for visibility */
            padding: 10px;
            background-color: #FFFFFF; /* Match page background */
            font-size: 0.8em;
            border-top: 1px solid #E0E0E0; /* Subtle border for separation */
            z-index: 999;
        ">
            ©copyright SSO Consultants
        </div>
        """,
        unsafe_allow_html=True
    )

# Entry point for the Streamlit application
if __name__ == "__main__":
    main()
    
