import streamlit as st
import os
import io
import json
import re
import bcrypt
from datetime import datetime
import time 

# --- Firebase Imports ---
import firebase_admin
from firebase_admin import credentials, auth, firestore, storage
from firebase_admin import exceptions # Import exceptions module for FirebaseError
import requests 
import base64 # IMPORTANT: This import is necessary for decoding the Base64 key

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
    page_icon="🔍",
    layout="wide" 
)

# --- Configuration: NOW READING FROM STREAMLIT SECRETS ---
# API keys and service account data are accessed via st.secrets,
# ensuring they are not hardcoded or directly committed to the repository.

# Firebase Storage Bucket Name (this can remain hardcoded as it's not a secret itself, but derived from project)
FIREBASE_STORAGE_BUCKET_NAME = 'ecr-app-drive-integration.appspot.com' 

# --- Firebase Initialization ---
# Initialize Firebase Admin SDK if not already initialized to prevent 'duplicate app' errors on Streamlit reruns
if 'db' not in st.session_state:
    st.session_state['db'] = None
if 'bucket' not in st.session_state:
    st.session_state['bucket'] = None

# Check if Firebase is already initialized to prevent re-initialization errors
if not firebase_admin._apps:
    try:
        # Check if the Base64 encoded Firebase service account key is available in Streamlit secrets
        if "FIREBASE_SERVICE_ACCOUNT_KEY_BASE64" not in st.secrets:
            st.error("Firebase service account key (Base64) not found in Streamlit secrets. Please configure it in .streamlit/secrets.toml")
            st.stop() # Stop the app if the secret is missing

        # Decode the Base64 string back to bytes
        encoded_key_bytes = st.secrets["FIREBASE_SERVICE_ACCOUNT_KEY_BASE64"].encode('utf-8')
        decoded_key_bytes = base64.b64decode(encoded_key_bytes)
        
        # Parse the decoded bytes (which is JSON) into a Python dictionary
        FIREBASE_SERVICE_ACCOUNT_CONFIG = json.loads(decoded_key_bytes)
        
        # Use the dictionary to create Firebase credentials
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_CONFIG)
        
        # Initialize the Firebase app with credentials and the correct storage bucket
        firebase_admin.initialize_app(cred, {
            'storageBucket': FIREBASE_STORAGE_BUCKET_NAME
        })
        
        # Get Firestore client and Storage bucket client and store them in session state
        st.session_state['db'] = firestore.client()
        st.session_state['bucket'] = storage.bucket(FIREBASE_STORAGE_BUCKET_NAME)
        st.success("Firebase initialized successfully!")
        print("DEBUG: Firebase initialized successfully in terminal.") # Terminal print for debugging
        print(f"DEBUG: Initialized with Storage Bucket: {st.session_state['bucket'].name}") # Verify bucket name
    except Exception as e:
        # Provide detailed error message for troubleshooting Firebase initialization issues
        st.error(f"Error initializing Firebase: {e}.")
        st.error("Please ensure your Streamlit secrets are correctly configured for Firebase. Specifically check 'FIREBASE_SERVICE_ACCOUNT_KEY_BASE64'.")
        print(f"ERROR: Firebase initialization failed: {e}") # Terminal print for debugging
        st.stop() # Stop the app execution if Firebase fails to initialize

# Assign db and bucket from session_state for easier use in functions
db = st.session_state['db']
bucket = st.session_state['bucket']

# Initialize OpenAI client
try:
    # Check if OpenAI API Key is available in Streamlit secrets
    if "OPENAI_API_KEY" not in st.secrets:
        st.error("OpenAI API key not found in Streamlit secrets. Please configure it in .streamlit/secrets.toml")
        st.stop()
    # Initialize the OpenAI client using the API key from secrets
    openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception as e:
    st.error(f"OpenAI client not initialized: {e}. Please check your OPENAI_API_KEY in Streamlit secrets.")
    print(f"ERROR: OpenAI client initialization failed: {e}") # Terminal print for debugging
    st.stop() # Stop the app if OpenAI fails to initialize


# --- Streamlit Session State Initialization (Crucial for Streamlit) ---
# These variables persist across Streamlit reruns, managing UI state and user data.
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_name' not in st.session_state:
    st.session_state['user_name'] = ''
if 'user_email' not in st.session_state:
    st.session_state['user_email'] = ''
if 'user_uid' not in st.session_state: # Store user UID for Firestore security rules
    st.session_state['user_uid'] = ''
if 'is_admin' not in st.session_state: # Track admin status
    st.session_state['is_admin'] = False
if 'ai_review_result' not in st.session_state:
    st.session_state['ai_review_result'] = None # Stores the full JSON from AI analysis
if 'generated_docx_buffer' not in st.session_state:
    st.session_state['generated_docx_buffer'] = None # Stores the BytesIO object for DOCX download
if 'review_triggered' not in st.session_state:
    st.session_state['review_triggered'] = False # Flag to control display of AI results
if 'current_page' not in st.session_state:
    st.session_state['current_page'] = 'Login' # Default to Login page if not set
if 'jd_filename_for_save' not in st.session_state: # Session state for JD filename to use in save
    st.session_state['jd_filename_for_save'] = "Job Description"
if 'cv_filenames_for_save' not in st.session_state: # Session state for CV filenames to use in save
    st.session_state['cv_filenames_for_save'] = [] # Store as a list
if 'login_mode' not in st.session_state: # New: To distinguish Admin vs User login on the form
    st.session_state['login_mode'] = None
# New session state variables for first-time password update
if 'new_user_email_for_pw_reset' not in st.session_state:
    st.session_state['new_user_email_for_pw_reset'] = ''
if 'new_user_uid_for_pw_reset' not in st.session_state:
    st.session_state['new_user_uid_for_pw_reset'] = ''

# --- Helper Functions for Text Extraction ---

def extract_text_from_pdf(uploaded_file_bytes_io):
    """Extracts text from a PDF file using PyPDF2."""
    try:
        reader = PdfReader(uploaded_file_bytes_io)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        st.error(f"Error extracting text from PDF: {e}")
        print(f"ERROR (extract_text_from_pdf): {e}") # Added terminal print for debugging
        return None

def extract_text_from_docx(uploaded_file_bytes_io):
    """Extracts text from a DOCX file using python-docx."""
    try:
        document = Document(uploaded_file_bytes_io)
        text = ""
        for paragraph in document.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        st.error(f"Error extracting text from DOCX: {e}")
        print(f"ERROR (extract_text_from_docx): {e}") # Added terminal print for debugging
        return None

def get_file_content(uploaded_file_bytes_io, filename):
    """Determines file type based on extension and extracts text content."""
    file_extension = os.path.splitext(filename)[1].lower()

    if file_extension == '.pdf':
        return extract_text_from_pdf(uploaded_file_bytes_io)
    elif file_extension == '.docx':
        return extract_text_from_docx(uploaded_file_bytes_io)
    elif file_extension == '.txt':
        return uploaded_file_bytes_io.read().decode('utf-8')
    else:
        st.error(f"Unsupported file type: {file_extension}. Only PDF, DOCX, TXT are supported.")
        print(f"ERROR (get_file_content): Unsupported file type {file_extension} for {filename}") # Added terminal print
        return None

# --- AI Function: Comparative Analysis ---

def get_comparative_ai_analysis(jd_text, all_cv_data):
    """
    Uses OpenAI to perform a comparative analysis of multiple CVs against a JD.
    Returns a complex JSON object containing a table of candidate evaluations,
    a table of criteria observations, additional observations text, and a final
    shortlist recommendation.
    """
    if not jd_text or not all_cv_data:
        print("DEBUG (get_comparative_ai_analysis): Missing JD or CV data.") # Added terminal print
        return {"error": "Missing Job Description or Candidate CV content for comparative analysis."}

    # System prompt defines the AI's role and the required JSON output format
    system_prompt = """
    You are an expert Talent Acquisition professional in India. Your task is to perform a detailed comparative analysis of multiple candidate CVs against a given Job Description (JD).

    Your output MUST be a single JSON object with the following structure, containing two distinct arrays for tables and two strings for text sections:
    {
      "candidate_evaluations": [
        {
          "Candidate Name": "...",       // Derived from filename (e.g., "Charlie")
          "Match %": "...",              // Numerical percentage as a string (e.g., "85%")
          "Ranking": "...",              // E.g., "1", "2", "3", etc. (NO MEDALS)
          "Shortlist Probability": "...",// E.g., "High", "Moderate", "Low"
          "Key Strengths": "...",        // Concise points, comma-separated or short phrase. Highlight relevant experience.
          "Key Gaps": "...",             // Concise points, comma-separated or short phrase.
          "Location Suitability": "...", // E.g., "Pune", "Delhi (flexible)", "Remote", "Not Specified"
          "Comments": "..."              // Any other relevant observation for this candidate, including fit for Indian context.
        },
        // ... more candidate evaluation objects for each CV ...
      ],
      "criteria_observations": [ // This array is for the second table comparing candidates across common criteria
        {
          "Criteria": "Education (MBA HR)",
          "Candidate 1 Name": "✅/❌/⚠️", // Column for each candidate provided (e.g., "Himanshukulkarni")
          "Candidate 2 Name": "✅/❌/⚠️",
          // ... more candidate columns based on actual input filenames
        },
        {
          "Criteria": "Recruitment / TA Experience",
          "Candidate 1 Name": "✅/❌/⚠️",
          "Candidate 2 Name": "✅/❌/⚠️",
        },
        // ... more criteria rows ...
      ],
      "additional_observations_text": "...", // Comprehensive text for general observations not covered in tables.
      "final_shortlist_recommendation": "..." // Concise text for the final recommendation, explicitly naming shortlisted candidates.
    }

    Ensure "Match %" is a string.
    Ensure "Ranking" is a numerical rank string (e.g., "1", "2") without any emoji symbols (like 🥇, 🥈, 🥉).
    For "criteria_observations", dynamically create columns for each candidate using their names (e.g., "Gauri Deshmukh", "Himanshukulkarni"). Use ✅ for good fit, ❌ for not a fit, ⚠️ for partial fit.
    Make sure all text fields are within the string limits of JSON.
    The "Candidate Name" in "candidate_evaluations" and the dynamic column headers in "criteria_observations" should be derived from the provided filenames (e.g., "Gauri CV.pdf" -> "Gauri").
    """

    user_prompt = f"""
    Here is the Job Description (JD):
    ---
    {jd_text}
    ---

    Here are the Candidate CVs for comparative analysis:
    """
    # Append each CV's content to the user prompt
    for idx, cv_item in enumerate(all_cv_data):
        # Extract name without extension for table headers
        candidate_name_for_prompt = os.path.splitext(cv_item['filename'])[0].replace(" CV", "").strip()
        user_prompt += f"\n--- Candidate {idx+1} (Name: {candidate_name_for_prompt}, Filename: {cv_item['filename']}) ---\n"
        user_prompt += f"{cv_item['text']}\n"
    user_prompt += "--- End of Candidate CVs ---"
    user_prompt += "\n\nPlease provide the comparative analysis in the specified JSON format."

    try:
        with st.spinner("AI is analyzing the JD and CVs... This may take a moment."):
            print("DEBUG (get_comparative_ai_analysis): Sending request to OpenAI API.") # Added terminal print
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini", # Using gpt-4o-mini for cost-effectiveness and speed
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2, # Lower temperature for more deterministic and factual responses
                response_format={"type": "json_object"} # Ensure JSON output
            )
        ai_response_content = response.choices[0].message.content
        print(f"DEBUG (get_comparative_ai_analysis): Raw AI Response: {ai_response_content[:200]}...") # Log first 200 chars
        comparative_data = json.loads(ai_response_content)
        
        # --- Post-processing: Remove medals from Ranking ---
        if "candidate_evaluations" in comparative_data:
            for candidate in comparative_data["candidate_evaluations"]:
                if "Ranking" in candidate and isinstance(candidate["Ranking"], str):
                    # Remove common medal emojis (U+1F3C5 to U+1F3CA and U+1F947 to U+1F949)
                    # and strip any whitespace
                    candidate["Ranking"] = re.sub(r'[\U0001F3C5-\U0001F3CA\U0001F947-\U0001F949]', '', candidate["Ranking"]).strip()

        print("DEBUG (get_comparative_ai_analysis): AI analysis successful.") # Added terminal print
        return comparative_data

    except json.JSONDecodeError as e:
        st.error(f"Error: AI response was not valid JSON. Please try again or refine input. Error: {e}")
        st.code(ai_response_content) # Display raw response for debugging
        print(f"ERROR (get_comparative_ai_analysis): JSON Decode Error: {e}, Response: {ai_response_content}") # Added terminal print
        return {"error": f"AI response format error: {e}"}
    except Exception as e:
        st.error(f"An unexpected error occurred during AI analysis: {e}")
        print(f"ERROR (get_comparative_ai_analysis): Unexpected Error during AI analysis: {e}") # Added terminal print
        return {"error": f"AI processing failed: {e}"}

# --- DOCX Generation Function ---

def generate_docx_report(comparative_data, jd_filename="Job Description", cv_filenames_str="Candidates"):
    """
    Generates a DOCX report based on the comparative AI analysis data.
    Includes two tables and text sections.
    """
    try:
        document = Document()

        # Set document properties for better appearance (margins, font, etc.)
        section = document.sections[0]
        section.start_type = WD_SECTION_START.NEW_PAGE
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)

        # Title and Metadata
        document.add_heading("JD-CV Comparative Analysis Report", level=0)
        document.add_paragraph().add_run("Generated by SSO Consultants AI").italic = True
        document.add_paragraph().add_run(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}").small_caps = True
        document.add_paragraph(f"Job Description: {jd_filename}\nCandidates: {cv_filenames_str}")
        document.add_paragraph("\n") # Add some space

        # Extract data from AI response for easier access
        candidate_evaluations_data = comparative_data.get("candidate_evaluations", [])
        criteria_observations_data = comparative_data.get("criteria_observations", [])
        additional_observations_text = comparative_data.get("additional_observations_text", "No general observations provided.")
        final_shortlist_recommendation = comparative_data.get("final_shortlist_recommendation", "No final recommendation provided.")

        # --- Candidate Evaluation Table ---
        if candidate_evaluations_data:
            document.add_heading("🧾 Candidate Evaluation Table", level=1)
            document.add_paragraph("Detailed assessment of each candidate against the Job Description:")

            df_evaluations = pd.DataFrame(candidate_evaluations_data)

            # Define expected columns and ensure they exist, adding 'N/A' if missing
            expected_cols_eval = ["Candidate Name", "Match %", "Ranking", "Shortlist Probability", "Key Strengths", "Key Gaps", "Location Suitability", "Comments"]
            for col in expected_cols_eval:
                if col not in df_evaluations.columns:
                    df_evaluations[col] = "N/A"
            # Reorder columns as desired
            df_evaluations = df_evaluations[expected_cols_eval]

            # Add table to the document
            table_eval = document.add_table(rows=1, cols=len(df_evaluations.columns))
            table_eval.style = 'Table Grid' # Apply a default table style

            # Add table headers (first row)
            hdr_cells_eval = table_eval.rows[0].cells
            for i, col_name in enumerate(df_evaluations.columns):
                hdr_cells_eval[i].text = col_name
                # Format header text
                for paragraph in hdr_cells_eval[i].paragraphs:
                    for run in paragraph.runs:
                        run.bold = True
                        run.font.size = Pt(9) # Smaller font for headers for better fit
                hdr_cells_eval[i].vertical_alignment = WD_ALIGN_VERTICAL.CENTER

            # Add data rows
            for index, row in df_evaluations.iterrows():
                row_cells = table_eval.add_row().cells
                for i, cell_value in enumerate(row):
                    row_cells[i].text = str(cell_value)
                    # Format body text
                    for paragraph in row_cells[i].paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(9) # Smaller font for body for better fit

            document.add_paragraph("\n") # Add spacing after table

        # --- Additional Observations (Criteria Comparison) Table ---
        if criteria_observations_data:
            document.add_heading("✅ Additional Observations (Criteria Comparison)", level=1)
            
            df_criteria = pd.DataFrame(criteria_observations_data)

            table_criteria = document.add_table(rows=1, cols=len(df_criteria.columns))
            table_criteria.style = 'Table Grid' # Apply a default table style

            # Add table headers (first row)
            hdr_cells_criteria = table_criteria.rows[0].cells
            for i, col_name in enumerate(df_criteria.columns):
                hdr_cells_criteria[i].text = col_name
                # Format header text
                for paragraph in hdr_cells_criteria[i].paragraphs:
                    for run in paragraph.runs:
                        run.bold = True
                        run.font.size = Pt(9)
                hdr_cells_criteria[i].vertical_alignment = WD_ALIGN_VERTICAL.CENTER

            # Add data rows
            for index, row in df_criteria.iterrows():
                row_cells = table_criteria.add_row().cells
                for i, cell_value in enumerate(row):
                    row_cells[i].text = str(cell_value)
                    # Format body text
                    for paragraph in row_cells[i].paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(9)

            document.add_paragraph("\n") # Add spacing after table

        # --- General Additional Observations Text ---
        # Check if text is present and not just the default or empty
        if additional_observations_text and additional_observations_text.strip() not in ["No general observations provided.", ""]:
            document.add_heading("General Observations", level=2)
            document.add_paragraph(additional_observations_text)
            document.add_paragraph("\n")

        # --- Final Shortlist Recommendation ---
        # Check if text is present and not just the default or empty
        if final_shortlist_recommendation and final_shortlist_recommendation.strip() not in ["No final recommendation provided.", ""]:
            document.add_heading("📌 Final Shortlist Recommendation", level=1)
            final_rec_para = document.add_paragraph()
            final_rec_para.add_run(final_shortlist_recommendation).bold = True # Make recommendation bold
            document.add_paragraph("\n")

        # Save the document to a BytesIO object
        doc_io = io.BytesIO()
        document.save(doc_io)
        doc_io.seek(0) # Rewind the buffer to the beginning
        print("DEBUG (generate_docx_report): DOCX generated successfully.") # Added terminal print
        return doc_io
    except Exception as e:
        st.error(f"Error generating DOCX report: {e}")
        print(f"ERROR (generate_docx_report): {e}") # Added terminal print
        return None

# --- Firebase Authentication Functions ---

def register_user(email, password, username):
    """Registers a new user in Firebase Authentication and stores user profile in Firestore."""
    try:
        print(f"DEBUG (register_user): Attempting to create user {email}") # Added terminal print
        # Create user in Firebase Auth
        user = auth.create_user(email=email, password=password, display_name=username)
        
        # Store additional user info in Firestore
        st.session_state['db'].collection('users').document(user.uid).set({
            'email': email,
            'username': username,
            'created_at': firestore.SERVER_TIMESTAMP,
            'isAdmin': False, # New users are NOT admins by default
            'firstLoginRequired': True # New users must change password on first login
        })
        st.success(f"Account created successfully for {username}! Please log in.")
        print(f"DEBUG (register_user): User {username} created and profile saved.") # Added terminal print
        time.sleep(2) # Added for debugging
        return True
    except Exception as e:
        st.error(f"Error creating account: {e}")
        print(f"ERROR (register_user): {e}") # Added terminal print
        time.sleep(2) # Added for debugging
        # Specific error handling for Firebase Auth
        if "EMAIL_EXISTS" in str(e):
            st.error("This email is already registered.")
        return False

def login_user(email, password, login_as_admin_attempt=False):
    """Logs in a user by verifying their existence in Firebase Auth using Admin SDK.
    Also fetches user's admin status from Firestore and enforces login type.
    Redirects to password update if first login is required."""
    try:
        print(f"DEBUG (login_user): Attempting to log in {email}") # Added terminal print
        user = auth.get_user_by_email(email)
        user_doc_ref = st.session_state['db'].collection('users').document(user.uid)
        user_doc = user_doc_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            is_user_admin_in_db = user_data.get('isAdmin', False)
            first_login_required = user_data.get('firstLoginRequired', True) # Default to True if field missing
            print(f"DEBUG (login_user): User {email} data: isAdmin={is_user_admin_in_db}, firstLoginRequired={first_login_required}") # Added terminal print

            # Enforce login type:
            if login_as_admin_attempt and not is_user_admin_in_db:
                st.error("This account does not have administrator privileges. Please log in as a regular user.")
                print(f"DEBUG (login_user): Admin login attempt for non-admin user {email} denied.") # Added terminal print
                return
            elif not login_as_admin_attempt and is_user_admin_in_db:
                st.error("This account has administrator privileges. Please log in as an administrator.")
                print(f"DEBUG (login_user): User login attempt for admin user {email} denied.") # Added terminal print
                return
            
            # If first login is required, redirect to password update page
            if first_login_required:
                st.session_state['new_user_email_for_pw_reset'] = email # Store email
                st.session_state['new_user_uid_for_pw_reset'] = user.uid # Store UID
                st.session_state['current_page'] = 'Update Password'
                st.success("Please update your password before proceeding.")
                print(f"DEBUG (login_user): Redirecting {email} to password update page.") # Added terminal print
                time.sleep(1)
                st.rerun()
                return

            # Proceed with normal login if first login is not required
            st.session_state['logged_in'] = True
            st.session_state['user_email'] = email
            st.session_state['user_name'] = user_data.get('username', email.split('@')[0])
            st.session_state['user_uid'] = user.uid # Store UID
            st.session_state['is_admin'] = is_user_admin_in_db # Get admin status

            st.success(f"Logged in as {st.session_state['user_name']}.")
            if st.session_state['is_admin']:
                st.info("You are logged in as an administrator.")
            print(f"DEBUG (login_user): Successfully logged in {st.session_state['user_name']} (UID: {st.session_state['user_uid']}, Admin: {st.session_state['is_admin']}).") # Added terminal print
            
            time.sleep(1) # Short delay for message to be visible
            st.session_state['current_page'] = 'Dashboard' # Ensure correct page after successful login
            st.rerun() 
        else:
            st.error("User profile not found in Firestore. Please ensure your account is set up correctly.")
            print(f"ERROR (login_user): User profile for {email} not found in Firestore.") # Added terminal print
    except exceptions.FirebaseError as e: 
        st.error(f"Login failed: {e}")
        print(f"ERROR (login_user): Firebase Error during login for {email}: {e}") # Added terminal print
        time.sleep(2)
        if "user-not-found" in str(e):
            st.error("Invalid email. Please check your email or sign up.")
        elif "invalid-argument" in str(e):
            st.error("Invalid email format.")
        else:
            st.error(f"An authentication error occurred: {e}. Please try again.")
    except Exception as e:
        st.error(f"An unexpected error occurred during login: {e}")
        print(f"ERROR (login_user): Unexpected Python Error during login for {email}: {e}") # Added terminal print
        time.sleep(2)

def logout_user():
    """Logs out the current user by resetting session state."""
    print("DEBUG (logout_user): Initiating logout.") # Added terminal print
    st.session_state['logged_in'] = False
    st.session_state['user_name'] = ''
    st.session_state['user_email'] = ''
    st.session_state['user_uid'] = ''
    st.session_state['is_admin'] = False # Reset admin status on logout
    st.session_state['ai_review_result'] = None
    st.session_state['generated_docx_buffer'] = None
    st.session_state['review_triggered'] = False
    st.session_state['current_page'] = 'Login' # Redirect to login page on logout
    st.session_state['login_mode'] = None # Reset login mode
    st.session_state['new_user_email_for_pw_reset'] = '' # Clear reset vars
    st.session_state['new_user_uid_for_pw_reset'] = ''
    st.success("Logged out successfully!")
    print("DEBUG (logout_user): User logged out. Session state reset. Rerunning.") # Added terminal print
    st.rerun() # Rerun to refresh UI and show logged-out state

# --- Streamlit Page Functions ---

def dashboard_page():
    """Displays the user dashboard."""
    st.title(f"Welcome, {st.session_state['user_name']}!")
    st.write("This is your dashboard. Use the sidebar to navigate.")
    st.info("To get started, navigate to 'Upload JD & CV' to perform a new AI-powered comparative analysis.")
    st.write("You can also check 'Review Reports' to see your past analyses.")
    print(f"DEBUG (dashboard_page): Displaying dashboard for {st.session_state['user_name']}.") # Added terminal print
    
    # Placeholder for a relevant image or more dashboard content
    # st.image("path/to/your/sso_logo.png", use_column_width=True, caption="Application Overview") 

def upload_jd_cv_page():
    """Handles JD and CV uploads, triggers AI review, and displays/downloads results."""
    st.title("⬆️ Upload JD & CV for AI Review")
    st.write("Upload your Job Description and multiple Candidate CVs to start the comparative analysis.")
    print("DEBUG (upload_jd_cv_page): Displaying upload page.") # Added terminal print

    # File upload widgets
    uploaded_jd = st.file_uploader("Upload Job Description (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], key="jd_uploader")
    uploaded_cvs = st.file_uploader("Upload Candidate's CVs (Multiple - PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True, key="cv_uploader")

    # Button to start AI review
    if st.button("Start AI Review", key="start_review_button"):
        print("DEBUG (upload_jd_cv_page): 'Start AI Review' button clicked.") # Added terminal print
        if not uploaded_jd:
            st.warning("Please upload a Job Description.")
            return
        if not uploaded_cvs:
            st.warning("Please upload at least one Candidate CV.")
            return

        # Process JD file
        jd_text = get_file_content(uploaded_jd, uploaded_jd.name)
        
        # Process multiple CV files
        all_candidates_data = []
        cv_filenames_list = [] # List to store original CV filenames
        for cv_file in uploaded_cvs:
            cv_text = get_file_content(cv_file, cv_file.name)
            if cv_text:
                all_candidates_data.append({'filename': cv_file.name, 'text': cv_text})
                cv_filenames_list.append(cv_file.name) # Store original filename
            else:
                st.warning(f"Could not process CV: {cv_file.name}. Skipping it.")
        
        # Validate extracted content
        if not jd_text:
            st.error("Failed to extract text from the Job Description.")
            return
        if not all_candidates_data:
            st.error("No valid CVs could be processed for analysis.")
            return

        # Reset state variables before new review
        st.session_state['review_triggered'] = False # Set to false initially, true on success
        st.session_state['ai_review_result'] = None
        st.session_state['generated_docx_buffer'] = None

        # Perform AI analysis
        comparative_results = get_comparative_ai_analysis(jd_text, all_candidates_data)

        if "error" in comparative_results:
            st.error(f"AI analysis failed: {comparative_results['error']}")
        else:
            st.session_state['ai_review_result'] = comparative_results
            st.success("AI review completed successfully!")
            print("DEBUG (upload_jd_cv_page): AI review successful. Preparing DOCX.") # Added terminal print
            
            # Store filenames in session state immediately after successful review
            st.session_state['jd_filename_for_save'] = uploaded_jd.name
            st.session_state['cv_filenames_for_save'] = cv_filenames_list # Store as a list

            # Generate DOCX buffer immediately after successful AI review
            # Pass original filenames for DOCX header
            st.session_state['generated_docx_buffer'] = generate_docx_report(
                comparative_results, 
                st.session_state['jd_filename_for_save'], 
                ", ".join(st.session_state['cv_filenames_for_save'])
            )
            st.session_state['review_triggered'] = True # Set to true to display results

    # --- Display Results and Download Options ---
    # Only display results if a review was successfully triggered and results exist
    if st.session_state['review_triggered'] and st.session_state['ai_review_result']:
        print("DEBUG (upload_jd_cv_page): Displaying AI review results section.") # Added terminal print
        comparative_results = st.session_state['ai_review_result']

        st.subheader("AI Review Results:")

        # Candidate Evaluation Table
        candidate_evaluations_data = comparative_results.get("candidate_evaluations", [])
        if candidate_evaluations_data:
            st.markdown("### 🧾 Candidate Evaluation Table")
            df_evaluations = pd.DataFrame(candidate_evaluations_data)
            # Ensure all expected columns are present for consistent display
            expected_cols_eval = ["Candidate Name", "Match %", "Ranking", "Shortlist Probability", "Key Strengths", "Key Gaps", "Location Suitability", "Comments"]
            for col in expected_cols_eval:
                if col not in df_evaluations.columns:
                    df_evaluations[col] = "N/A"
            df_evaluations = df_evaluations[expected_cols_eval]
            st.dataframe(df_evaluations, use_container_width=True, hide_index=True)
        
        # Additional Observations Table
        criteria_observations_data = comparative_results.get("criteria_observations", [])
        if criteria_observations_data:
            st.markdown("### ✅ Additional Observations (Criteria Comparison)")
            df_criteria = pd.DataFrame(criteria_observations_data)
            st.dataframe(df_criteria, use_container_width=True, hide_index=True)

        # General Observations Text
        additional_observations_text = comparative_results.get("additional_observations_text", "No general observations provided.")
        if additional_observations_text and additional_observations_text.strip() not in ["No general observations provided.", ""]:
            st.markdown("### General Observations")
            st.write(additional_observations_text)

        # Final Shortlist Recommendation
        final_shortlist_recommendation = comparative_results.get("final_shortlist_recommendation", "No final recommendation provided.")
        if final_shortlist_recommendation and final_shortlist_recommendation.strip() not in ["No final recommendation provided.", ""]:
            st.markdown("### 📌 Final Shortlist Recommendation")
            st.write(final_shortlist_recommendation)

        st.markdown("---") # Separator for visual clarity

        # --- Combined Download & Save Button ---
        st.subheader("Download & Save Report")
        
        # Generate the unique filename with username and timestamp
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        download_filename = f"{st.session_state['user_name'].replace(' ', '')}_JD-CV_Comparison_Analysis_{timestamp_str}.docx"

        if st.session_state['generated_docx_buffer']:
            st.download_button(
                label="Download & Save DOCX Report ⬇️☁️", # Combined label
                data=st.session_state['generated_docx_buffer'],
                file_name=download_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="download_and_save_docx",
                on_click=lambda: save_report_on_download(
                    download_filename,
                    st.session_state['generated_docx_buffer'],
                    st.session_state['ai_review_result'],
                    st.session_state['jd_filename_for_save'],
                    st.session_state['cv_filenames_for_save']
                )
            )
        else:
            st.warning("Run an AI review to generate a report for download and save.")

# Callback function for saving report when download button is clicked
def save_report_on_download(filename, docx_buffer, ai_result, jd_original_name, cv_original_names):
    """Saves the report to Firebase Storage and Firestore metadata."""
    st.info("Attempting to save report to cloud...") # New info message in UI
    print("DEBUG (save_report_on_download): Function started. User UID:", st.session_state.get('user_uid', 'N/A')) # Terminal print
    print(f"DEBUG (save_report_on_download): Current bucket name from session_state: {st.session_state['bucket'].name}") # NEW DEBUG PRINT
    
    storage_file_path = f"jd_cv_reports/{st.session_state['user_uid']}/{filename}"
    download_url = None # Initialize download_url

    try:
        # 1. Upload DOCX to Firebase Storage
        print(f"DEBUG (save_report_on_download): Attempting to upload file to Storage at: {storage_file_path}") # Terminal print
        blob = st.session_state['bucket'].blob(storage_file_path)
        docx_buffer.seek(0) # Ensure buffer is at the beginning before uploading
        blob.upload_from_string(docx_buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        
        blob.make_public() # Make the file publicly accessible
        download_url = blob.public_url
        st.success(f"File uploaded to Firebase Storage successfully! URL: {download_url}") # UI success for Storage
        print(f"DEBUG (save_report_on_download): File uploaded to Storage. Public URL: {download_url}") # Terminal print

        # 2. Prepare metadata for Firestore
        report_metadata = {
            "user_email": st.session_state['user_email'],
            "user_name": st.session_state['user_name'],
            "user_uid": st.session_state['user_uid'], # Crucial for security rules
            "jd_filename": jd_original_name,
            "cv_filenames": cv_original_names, # Store as a list of strings
            "review_date": firestore.SERVER_TIMESTAMP, # Use server timestamp for consistency
            "review_date_human": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), # Human-readable date
            "outputDocFileName": filename,
            "outputDocURL": download_url,
            "summary": ai_result.get("final_shortlist_recommendation", "No summary provided.")
        }
        print(f"DEBUG (save_report_on_download): Prepared Firestore metadata: {report_metadata}") # Terminal print

        # 3. Save metadata to Firestore
        try:
            st.session_state['db'].collection('jd_cv_reports').add(report_metadata)
            st.success("Report metadata saved to Firestore successfully!") # Final UI success message
            print("DEBUG (save_report_on_download): Report metadata successfully added to Firestore.") # Terminal print
        except exceptions.FirebaseError as firestore_e: # Catch specific Firebase errors
            st.error(f"Firestore save failed: {firestore_e}. Please check Firestore rules and quotas.")
            print(f"ERROR (save_report_on_download): Firestore specific error: {firestore_e}") # Terminal error
            # Attempt to delete the storage file if Firestore save fails to keep state consistent
            if download_url: # Only try to delete if upload was successful
                try:
                    blob.delete()
                    print("DEBUG: Deleted file from Storage due to Firestore save failure.")
                except Exception as e_del:
                    print(f"ERROR: Failed to delete Storage file after Firestore error: {e_del}")
        except Exception as generic_e: # Catch any other generic Python errors
            st.error(f"An unexpected error occurred during Firestore save: {generic_e}.")
            print(f"ERROR (save_report_on_download): Generic error during Firestore save: {generic_e}") # Terminal error
            # Same cleanup logic
            if download_url:
                try:
                    blob.delete()
                    print("DEBUG: Deleted file from Storage due to generic Firestore save failure.")
                except Exception as e_del:
                    print(f"ERROR: Failed to delete Storage file after generic error: {e_del}")

    except Exception as e: # Catch errors during storage upload or initial setup
        st.error(f"Error during report upload or initial setup: {e}")
        print(f"ERROR (save_report_on_download): Overall error in function (Storage upload or initial setup): {e}")

    finally:
        # Reset flags after attempt to save, regardless of success or failure
        st.session_state['review_triggered'] = False
        st.session_state['ai_review_result'] = None
        st.session_state['generated_docx_buffer'] = None
        st.session_state['jd_filename_for_save'] = "Job Description"
        st.session_state['cv_filenames_for_save'] = []


def review_reports_page():
    """Displays a table of past reports fetched from Firestore for the current user."""
    st.title("📚 Review Your Past Reports")
    st.write("Here you can find a history of your AI-generated comparative analysis reports.")
    print("DEBUG (review_reports_page): Displaying review reports page.") # Added terminal print

    # Ensure user is logged in before trying to fetch reports
    if not st.session_state['logged_in'] or not st.session_state['user_uid']:
        st.info("Please log in to view your past reports.")
        print("DEBUG (review_reports_page): User not logged in, cannot fetch reports.") # Added terminal print
        return

    try:
        # Fetch reports specific to the logged-in user from the 'jd_cv_reports' collection
        print(f"DEBUG (review_reports_page): Fetching reports for UID: {st.session_state['user_uid']}") # Added terminal print
        reports_ref = st.session_state['db'].collection('jd_cv_reports').where('user_uid', '==', st.session_state['user_uid']).order_by('review_date', direction=firestore.Query.DESCENDING)
        docs = reports_ref.stream() # Get all matching documents

        reviews_data = []
        for doc in docs:
            report = doc.to_dict()
            reviews_data.append({
                "Report ID": doc.id, # Added Report ID for deletion in Admin Panel
                "Report Name": report.get('outputDocFileName', 'N/A'),
                "Job Description": report.get('jd_filename', 'N/A'),
                "Candidates": ", ".join(report.get('cv_filenames', [])), # Join list of candidate names
                "Date Generated": report.get('review_date_human', 'N/A'),
                "Summary": report.get('summary', 'No summary provided.'),
                "Download Link": report.get('outputDocURL', '') # Store URL directly
            })
        
        if reviews_data:
            print(f"DEBUG (review_reports_page): Found {len(reviews_data)} reports.") # Added terminal print
            df = pd.DataFrame(reviews_data)
            st.dataframe(df,
                         column_config={
                             "Download Link": st.column_config.LinkColumn("Download File", display_text="⬇️ Download", help="Click to download the report file")
                         },
                         hide_index=True, # Hide default pandas index
                         use_container_width=True) # Make dataframe span full width
        else:
            st.info("No reports found yet for your account. Start by uploading JD & CVs!")
            print("DEBUG (review_reports_page): No reports found for this user.") # Added terminal print
    except Exception as e:
        st.error(f"Error fetching your review reports: {e}")
        print(f"ERROR (review_reports_page): Error fetching user reports: {e}") 


# --- Admin Pages ---

def admin_dashboard_page():
    """Admin dashboard overview."""
    st.title("⚙️ Admin Dashboard")
    st.write("Welcome to the Admin Panel. From here you can manage users and all generated reports.")
    st.info("Use the sidebar navigation to access User Management, Report Management, or Invite New Member.")
    print("DEBUG (admin_dashboard_page): Displaying admin dashboard.") # Added terminal print

def admin_user_management_page():
    """Admin page to manage users."""
    st.title("👥 Admin: User Management")
    st.write("View, manage roles, or delete users.")
    print("DEBUG (admin_user_management_page): Displaying user management page.") # Added terminal print

    users_data = []
    try:
        # Fetch all users from Firestore
        print("DEBUG (admin_user_management_page): Fetching all users from Firestore.") # Added terminal print
        users_ref = st.session_state['db'].collection('users')
        docs = users_ref.stream()

        for doc in docs:
            user_id = doc.id
            user_info = doc.to_dict()
            users_data.append({
                "UID": user_id,
                "Username": user_info.get('username', 'N/A'),
                "Email": user_info.get('email', 'N/A'),
                "Is Admin": user_info.get('isAdmin', False)
            })
        
        if users_data:
            print(f"DEBUG (admin_user_management_page): Found {len(users_data)} users.") # Added terminal print
            df_users = pd.DataFrame(users_data)
            st.dataframe(df_users, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("Manage User Actions")

            col1, col2 = st.columns(2) 

            with col1:
                st.markdown("##### Toggle Admin Status")
                user_email_toggle = st.text_input("User Email to Toggle Admin", key="toggle_admin_email")
                if st.button("Toggle Admin Status", key="toggle_admin_button"):
                    if user_email_toggle:
                        try:
                            print(f"DEBUG (admin_user_management_page): Toggling admin status for {user_email_toggle}.") # Added terminal print
                            # Get user by email to find UID
                            user_record = auth.get_user_by_email(user_email_toggle)
                            user_doc_ref = st.session_state['db'].collection('users').document(user_record.uid)
                            user_doc = user_doc_ref.get()
                            if user_doc.exists:
                                current_admin_status = user_doc.to_dict().get('isAdmin', False)
                                # Prevent admin from revoking their own admin status
                                if user_record.uid == st.session_state['user_uid'] and current_admin_status:
                                    st.error("You cannot revoke your own administrator privileges.")
                                    print("DEBUG (admin_user_management_page): Self-revocation attempt blocked.") # Added terminal print
                                else:
                                    user_doc_ref.update({'isAdmin': not current_admin_status})
                                    st.success(f"Admin status for {user_email_toggle} toggled to {not current_admin_status}.")
                                    print(f"DEBUG (admin_user_management_page): Admin status for {user_email_toggle} set to {not current_admin_status}.") # Added terminal print
                                    time.sleep(1)
                                    st.rerun()
                            else:
                                st.error("User profile not found in Firestore.")
                                print(f"ERROR (admin_user_management_page): User profile for {user_email_toggle} not found.") # Added terminal print
                        except auth.AuthError as e:
                            st.error(f"Error finding user: {e}")
                            print(f"ERROR (admin_user_management_page): Firebase Auth Error toggling: {e}") # Added terminal print
                        except Exception as e:
                            st.error(f"Error toggling admin status: {e}")
                            print(f"ERROR (admin_user_management_page): Generic Error toggling: {e}") # Added terminal print
                    else:
                        st.warning("Please enter a user email to toggle admin status.")
            
            with col2:
                st.markdown("##### Delete User")
                user_email_delete = st.text_input("User Email to Delete", key="delete_user_email")
                if st.button("Delete User", key="delete_user_button"):
                    if user_email_delete:
                        if user_email_delete == st.session_state['user_email']:
                            st.error("You cannot delete your own admin account!")
                            print("DEBUG (admin_user_management_page): Self-deletion attempt blocked.") # Added terminal print
                        else:
                            try:
                                print(f"DEBUG (admin_user_management_page): Deleting user {user_email_delete}.") # Added terminal print
                                # Get user by email to find UID
                                user_record = auth.get_user_by_email(user_email_delete)
                                
                                # Delete all reports associated with this user from Firestore and Storage
                                user_reports_ref = st.session_state['db'].collection('jd_cv_reports').where('user_uid', '==', user_record.uid)
                                user_reports_docs = user_reports_ref.stream()
                                for report_doc in user_reports_docs:
                                    report_data = report_doc.to_dict()
                                    storage_file_path = f"jd_cv_reports/{report_data['user_uid']}/{report_data['outputDocFileName']}"
                                    try:
                                        blob_to_delete = st.session_state['bucket'].blob(storage_file_path)
                                        blob_to_delete.delete()
                                        print(f"DEBUG (admin_user_management_page): Deleted Storage file for {user_email_delete}: {report_data['outputDocFileName']}.") # Added terminal print
                                    except Exception as storage_e:
                                        st.warning(f"Could not delete storage file for {user_email_delete}: {report_data['outputDocFileName']}. Error: {storage_e}")
                                        print(f"ERROR (admin_user_management_page): Storage deletion error for {user_email_delete}: {storage_e}") # Added terminal print
                                    report_doc.reference.delete()
                                    print(f"DEBUG (admin_user_management_page): Deleted Firestore document for {user_email_delete}: {report_doc.id}.") # Added terminal print

                                # Delete user from Firebase Authentication
                                auth.delete_user(user_record.uid)
                                # Delete user's profile from Firestore
                                st.session_state['db'].collection('users').document(user_record.uid).delete()
                                
                                st.success(f"User {user_email_delete} and all their associated data deleted successfully.")
                                print(f"DEBUG (admin_user_management_page): User {user_email_delete} fully deleted.") # Added terminal print
                                time.sleep(1)
                                st.rerun()
                            except auth.AuthError as e:
                                st.error(f"Error finding/deleting user: {e}")
                                print(f"ERROR (admin_user_management_page): Firebase Auth Error deleting: {e}") # Added terminal print
                            except Exception as e:
                                st.error(f"Error deleting user: {e}")
                                print(f"ERROR (admin_user_management_page): Generic Error deleting user: {e}") # Added terminal print
                    else:
                        st.warning("Please enter a user email to delete.")

        else:
            st.info("No users registered yet or error fetching users.")
            print("DEBUG (admin_user_management_page): No users found or fetch error.") # Added terminal print

    except Exception as e:
        st.error(f"Error fetching users for admin management: {e}")
        print(f"ERROR (admin_user_management_page): Error fetching users for admin management: {e}") 


def admin_report_management_page():
    """Admin page to manage all reports."""
    st.title("📊 Admin: Report Management")
    st.write("View and delete all AI-generated comparative analysis reports.")
    print("DEBUG (admin_report_management_page): Displaying report management page.") # Added terminal print

    all_reports_data = []
    try:
        # Fetch ALL reports from Firestore (no user filter)
        print("DEBUG (admin_report_management_page): Fetching all reports from Firestore.") # Added terminal print
        reports_ref = st.session_state['db'].collection('jd_cv_reports').order_by('review_date', direction=firestore.Query.DESCENDING)
        docs = reports_ref.stream()

        for doc in docs:
            report_id = doc.id
            report_info = doc.to_dict()
            all_reports_data.append({
                "Report ID": report_id,
                "Report Name": report_info.get('outputDocFileName', 'N/A'),
                "Uploaded By": report_info.get('user_name', 'N/A'),
                "Uploader Email": report_info.get('user_email', 'N/A'),
                "JD Filename": report_info.get('jd_filename', 'N/A'),
                "CV Filenames": ", ".join(report_info.get('cv_filenames', [])),
                "Date Generated": report_info.get('review_date_human', 'N/A'),
                "Summary": report_info.get('summary', 'No summary provided.'),
                "Download Link": report_info.get('outputDocURL', '')
            })
        
        if all_reports_data:
            print(f"DEBUG (admin_report_management_page): Found {len(all_reports_data)} reports.") # Added terminal print
            df_reports = pd.DataFrame(all_reports_data)
            st.dataframe(df_reports,
                         column_config={
                             "Download Link": st.column_config.LinkColumn("Download File", display_text="⬇️ Download", help="Click to download the report file")
                         },
                         hide_index=True,
                         use_container_width=True)

            st.markdown("---")
            st.subheader("Delete Report")
            report_id_to_delete = st.text_input("Enter Report ID to Delete (from table above)", key="delete_report_id")
            
            if st.button("Delete Report", key="delete_report_button"):
                if report_id_to_delete:
                    try:
                        print(f"DEBUG (admin_report_management_page): Deleting report {report_id_to_delete}.") # Added terminal print
                        report_doc_ref = st.session_state['db'].collection('jd_cv_reports').document(report_id_to_delete)
                        report_doc = report_doc_ref.get()

                        if report_doc.exists:
                            report_data = report_doc.to_dict()
                            storage_file_path = f"jd_cv_reports/{report_data['user_uid']}/{report_data['outputDocFileName']}"
                            
                            # Delete from Storage
                            blob_to_delete = st.session_state['bucket'].blob(storage_file_path)
                            blob_to_delete.delete()
                            st.success(f"File '{report_data['outputDocFileName']}' deleted from Storage.")
                            print(f"DEBUG (admin_report_management_page): Deleted Storage file: {storage_file_path}.") # Added terminal print

                            # Delete from Firestore
                            report_doc_ref.delete()
                            st.success(f"Report '{report_id_to_delete}' deleted from Firestore.")
                            print(f"DEBUG (admin_report_management_page): Deleted Firestore document: {report_id_to_delete}.") # Added terminal print
                            
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Report with this ID not found.")
                            print(f"ERROR (admin_report_management_page): Report {report_id_to_delete} not found.") # Added terminal print
                    except Exception as e:
                        st.error(f"Error deleting report: {e}. Ensure Storage path is correct and rules allow deletion.")
                        print(f"ERROR (admin_report_management_page): Error during report deletion for {report_id_to_delete}: {e}") # Added terminal print
                else:
                    st.warning("Please enter a Report ID to delete.")

        else:
            st.info("No reports found in the database.")
            print("DEBUG (admin_report_management_page): No reports found in database.") # Added terminal print

    except Exception as e:
        st.error(f"Error fetching all reports for admin management: {e}")
        print(f"ERROR (admin_report_management_page): Error fetching all reports: {e}") 

def admin_invite_member_page():
    """Admin page to invite and create new user accounts."""
    st.title("➕ Admin: Invite New Member")
    st.write("Create new user accounts directly and assign their initial role.")
    print("DEBUG (admin_invite_member_page): Displaying invite member page.") # Added terminal print

    # Using st.empty() to control message display more explicitly
    status_message_placeholder = st.empty()

    # Removed clear_on_submit=True to preserve input values on rerun for better UX feedback
    with st.form("invite_member_form"):
        # Initializing keys for inputs for manual clearing
        new_user_email_input = st.text_input("New User Email", help="The email address for the new account.", key="invite_email")
        new_username_input = st.text_input("New User Username", help="A display name for the new user.", key="invite_username")
        new_user_password_input = st.text_input("Temporary Password", type="password", help="A temporary password for the new user. Please communicate this to them securely.", key="invite_password")
        
        assign_role = st.radio(
            "Assign Role:",
            ("User", "Admin"),
            index=0, # Default to 'User'
            key="assign_role_radio"
        )
        
        is_admin_new_user = (assign_role == "Admin")
        
        # Only show confirmation checkbox if 'Admin' role is selected
        confirm_admin_invite = True 
        if is_admin_new_user:
            status_message_placeholder.warning("You are about to invite a new Administrator. Administrators have full control over users and reports.")
            confirm_admin_invite = st.checkbox("Yes, I understand and want to create an Administrator account.", key="confirm_admin_invite")
            
        submit_invite_button = st.form_submit_button("Invite New Member")

        if submit_invite_button:
            print("DEBUG (admin_invite_member_page): 'Invite New Member' button clicked.") # Added terminal print
            # Re-evaluate checkbox state at the time of button click
            if is_admin_new_user and not confirm_admin_invite:
                status_message_placeholder.error("Please confirm to create an Administrator account by checking the box.")
                print("DEBUG (admin_invite_member_page): Admin invite: checkbox not confirmed.") # Added terminal print
                return # Stop further execution if confirmation is missing
            
            if not (new_user_email_input and new_username_input and new_user_password_input):
                status_message_placeholder.warning("Please fill in all fields (Email, Username, Temporary Password).")
                print("DEBUG (admin_invite_member_page): Admin invite: missing fields.") # Added terminal print
                return

            if not re.match(r"[^@]+@[^@]+\.[^@]+", new_user_email_input):
                status_message_placeholder.warning("Please enter a valid email address.")
                print("DEBUG (admin_invite_member_page): Admin invite: invalid email format.") # Added terminal print
                return

            if len(new_user_password_input) < 6:
                status_message_placeholder.warning("Temporary password should be at least 6 characters long (Firebase minimum).")
                print("DEBUG (admin_invite_member_page): Admin invite: weak password.") # Added terminal print
                return
            
            # All validation passed, proceed with creating the user
            try:
                with st.spinner("Inviting new member..."):
                    print(f"DEBUG (admin_invite_member_page): Attempting to create user {new_user_email_input} with role {assign_role}.") # Added terminal print
                    # Create user in Firebase Authentication
                    user_record = auth.create_user(
                        email=new_user_email_input,
                        password=new_user_password_input,
                        display_name=new_username_input
                    )
                    
                    # Store user profile in Firestore with assigned role AND firstLoginRequired flag
                    st.session_state['db'].collection('users').document(user_record.uid).set({
                        'email': new_user_email_input,
                        'username': new_username_input,
                        'created_at': firestore.SERVER_TIMESTAMP,
                        'isAdmin': is_admin_new_user,
                        'firstLoginRequired': True # Force password change on first login for new users
                    })
                    status_message_placeholder.success(f"New user '{new_username_input}' ({new_user_email_input}) created successfully with role: {assign_role}!")
                    print(f"DEBUG (admin_invite_member_page): User {new_user_email_input} created in Auth and Firestore.") # Added terminal print
                    
                    # Manually clear inputs after successful submission for better UX
                    st.session_state['invite_email'] = ""
                    st.session_state['invite_username'] = ""
                    st.session_state['invite_password'] = ""
                    st.session_state['assign_role_radio'] = "User" # Reset radio button to default
                    if 'confirm_admin_invite' in st.session_state:
                        st.session_state['confirm_admin_invite'] = False # Reset checkbox

                    time.sleep(2)
                    st.rerun() # Rerun to clear the form and update possible user lists
            except exceptions.FirebaseError as e:
                error_message = str(e)
                print(f"ERROR (admin_invite_member_page): Firebase Error: {error_message}") # Added terminal print
                if "email-already-exists" in error_message:
                    status_message_placeholder.error("This email is already registered. Please use a different email.")
                elif "auth/weak-password" in error_message:
                     status_message_placeholder.error("The temporary password is too weak. It must be at least 6 characters long.")
                else:
                    status_message_placeholder.error(f"Error inviting new member: {error_message}")
            except Exception as e:
                status_message_placeholder.error(f"An unexpected error occurred while inviting new member: {e}")
                print(f"ERROR (admin_invite_member_page): Unexpected Python Error: {e}") 

def update_password_page():
    """Page for new users to update their temporary password."""
    st.title("🔑 Update Your Password")
    st.write("As a new member, please set your personal password to continue.")
    print("DEBUG (update_password_page): Displaying update password page.") # Added terminal print

    if not st.session_state['new_user_uid_for_pw_reset']:
        st.warning("You must be logged in with a temporary account to access this page. Please log in.")
        print("DEBUG (update_password_page): No user UID found for password reset. Redirecting.") # Added terminal print
        if st.button("Go to Login"):
            st.session_state['current_page'] = 'Login'
            st.rerun()
        return

    st.info(f"Updating password for: **{st.session_state['new_user_email_for_pw_reset']}**")

    update_status_placeholder = st.empty()

    with st.form("update_password_form"):
        current_temp_password = st.text_input("Current Temporary Password", type="password", help="The password you just used to log in.", key="current_temp_password")
        new_password = st.text_input("New Password", type="password", help="Your new permanent password.", key="new_password")
        confirm_new_password = st.text_input("Confirm New Password", type="password", help="Re-enter your new password to confirm.", key="confirm_new_password")
        
        submit_update_button = st.form_submit_button("Update Password")

        if submit_update_button:
            print("DEBUG (update_password_page): 'Update Password' button clicked.") # Added terminal print
            if not (current_temp_password and new_password and confirm_new_password):
                update_status_placeholder.warning("Please fill in all password fields.")
                print("DEBUG (update_password_page): Missing password fields.") # Added terminal print
                return
            
            if new_password != confirm_new_password:
                update_status_placeholder.error("New passwords do not match.")
                print("DEBUG (update_password_page): New passwords mismatch.") # Added terminal print
                return
            
            if len(new_password) < 6:
                update_status_placeholder.warning("New password must be at least 6 characters long.")
                print("DEBUG (update_password_page): New password too short.") # Added terminal print
                return

            try:
                with st.spinner("Updating password..."):
                    print(f"DEBUG (update_password_page): Attempting to update password for UID: {st.session_state['new_user_uid_for_pw_reset']}") # Added terminal print
                    # Update password in Firebase Authentication
                    auth.update_user(
                        uid=st.session_state['new_user_uid_for_pw_reset'],
                        password=new_password
                    )

                    # Update firstLoginRequired to False in Firestore
                    user_doc_ref = st.session_state['db'].collection('users').document(st.session_state['new_user_uid_for_pw_reset'])
                    user_doc_ref.update({'firstLoginRequired': False})

                    update_status_placeholder.success("Password updated successfully! Please log in with your new password.")
                    print("DEBUG (update_password_page): Password updated and firstLoginRequired set to False.") # Added terminal print
                    time.sleep(2)
                    logout_user() # Force logout after password update for re-login

            except exceptions.FirebaseError as e:
                error_message = str(e)
                print(f"ERROR (update_password_page): Firebase Error during password update: {error_message}") # Added terminal print
                if "auth/weak-password" in error_message:
                    update_status_placeholder.error("The new password is too weak. Please choose a stronger one.")
                else:
                    update_status_placeholder.error(f"Error updating password: {error_message}")
            except Exception as e:
                update_status_placeholder.error(f"An unexpected error occurred: {e}")
                print(f"ERROR (update_password_page): Unexpected Python Error during password update: {e}") 


# --- Main Streamlit Application Logic ---

def main():
    """Main function to set up Streamlit page and handle navigation/authentication."""
    # Robustly manage current_page state after login/logout
    if st.session_state['logged_in'] and st.session_state['current_page'] in ['Login', 'Signup']:
        st.session_state['current_page'] = 'Dashboard'
    # If not logged in and on a page other than Login/Signup/Update Password, redirect to Login
    elif not st.session_state['logged_in'] and st.session_state['current_page'] not in ['Login', 'Signup', 'Update Password']:
        st.session_state['current_page'] = 'Login'
        st.session_state['login_mode'] = None # Ensure login mode is reset if logged out unexpectedly

    # --- Sidebar for Logo, Title, and Navigation ---
    with st.sidebar:
        # st.image("path/to/your/sso_logo.png", use_column_width=True) # Uncomment and replace with your logo path
        st.title("SSO Consultants")
        st.subheader("AI Recruitment Dashboard")
        st.markdown("---") # Horizontal rule for separation

        # Conditional rendering based on login status
        if st.session_state['logged_in']:
            st.write(f"Welcome, **{st.session_state['user_name']}**!")
            if st.session_state['is_admin']:
                st.markdown("### Admin Privileges Active")
            
            # Navigation for logged-in users (User & Admin)
            user_pages = ['Dashboard', 'Upload JD & CV', 'Review Reports']
            admin_pages = ['Admin Dashboard', 'Admin: User Management', 'Admin: Report Management', 'Admin: Invite New Member'] 
            
            all_pages = user_pages 
            if st.session_state['is_admin']:
                all_pages.extend(admin_pages)

            # Determine default index for st.radio
            try:
                if st.session_state['current_page'] not in all_pages:
                    st.session_state['current_page'] = 'Dashboard'
                default_index = all_pages.index(st.session_state['current_page'])
            except ValueError:
                default_index = 0 

            # --- Radio buttons for navigation ---
            def update_page_selection():
                st.session_state['current_page'] = st.session_state['sidebar_radio_selection']
                print(f"DEBUG (sidebar_radio): Page selected: {st.session_state['current_page']}") # Added terminal print

            page_selection = st.radio(
                "Navigation",
                all_pages,
                key="sidebar_radio_selection", 
                index=default_index,
                on_change=update_page_selection 
            )

            st.markdown("---")
            # Logout button
            if st.button("Logout", key="logout_button"):
                logout_user()
        else:
            # Login Type Selection
            st.subheader("Choose Login Type")
            col_admin_login, col_user_login = st.columns(2)

            with col_admin_login:
                if st.button("Login as Admin", key="button_login_admin"):
                    st.session_state['login_mode'] = 'admin'
                    st.session_state['current_page'] = 'Login' 
                    print("DEBUG (main): Admin login mode selected.") # Added terminal print
                    st.rerun()
            with col_user_login:
                if st.button("Login as User", key="button_login_user"):
                    st.session_state['login_mode'] = 'user'
                    st.session_state['current_page'] = 'Login' 
                    print("DEBUG (main): User login mode selected.") # Added terminal print
                    st.rerun()
            
            # Only show login form if a mode has been selected
            if st.session_state['login_mode']:
                st.markdown("---")
                # Show login form based on current page
                if st.session_state['current_page'] == 'Login':
                    st.title(f"🔑 Login as {'Administrator' if st.session_state['login_mode'] == 'admin' else 'User'}")
                    with st.form("login_form"):
                        email = st.text_input("Email")
                        password = st.text_input("Password", type="password")
                        submit_button = st.form_submit_button("Login")
                        if submit_button:
                            print(f"DEBUG (main): Login form submitted for {email}.") # Added terminal print
                            if email and password:
                                # Pass login_as_admin_attempt based on login_mode
                                login_user(email, password, login_as_admin_attempt=(st.session_state['login_mode'] == 'admin'))
                            else:
                                st.warning("Please enter both email and password.")
                # The 'Signup' page and its button are now completely removed.
            else: # If no login mode selected, prompt user
                st.info("Please select 'Login as Admin' or 'Login as User' to proceed.")

    # --- Main Content Area Rendering ---
    # This block controls what is displayed based on st.session_state['current_page']

    print(f"DEBUG (main rendering): Current page to render: {st.session_state['current_page']}") # Added terminal print

    if st.session_state['logged_in']:
        if st.session_state['current_page'] == 'Dashboard':
            dashboard_page()
        elif st.session_state['current_page'] == 'Upload JD & CV':
            upload_jd_cv_page()
        elif st.session_state['current_page'] == 'Review Reports':
            review_reports_page()
        # Admin Pages - ENSURE THESE ARE CHECKED WITH is_admin
        elif st.session_state['is_admin'] and st.session_state['current_page'] == 'Admin Dashboard':
            admin_dashboard_page()
        elif st.session_state['is_admin'] and st.session_state['current_page'] == 'Admin: User Management':
            admin_user_management_page()
        elif st.session_state['is_admin'] and st.session_state['current_page'] == 'Admin: Report Management':
            admin_report_management_page()
        elif st.session_state['is_admin'] and st.session_state['current_page'] == 'Admin: Invite New Member': 
            admin_invite_member_page()
        # This case is less likely now as firstLoginRequired handles it, but keeps logic explicit
        elif st.session_state['current_page'] == 'Update Password': 
             update_password_page()
        else:
            st.error("Access Denied or Page Not Found. Please navigate using the sidebar.")
            print(f"ERROR (main rendering): Invalid page state for logged-in user: {st.session_state['current_page']}") # Added terminal print
    elif st.session_state['current_page'] == 'Update Password': # Allow direct access if flagged for reset, even if not 'fully' logged_in yet
        update_password_page()
    else:
        # This part handles the initial login forms, managed by the sidebar's conditional logic
        print("DEBUG (main rendering): Not logged in. Displaying login/mode selection.") # Added terminal print
        pass # The login/mode selection is handled directly in the sidebar block

    # --- FOOTER (Always visible at the bottom of the page) ---
    st.markdown(
        '<div style="text-align:center; color:#FF671F; margin-top:30px; padding:10px;">©copyright SSO Consultants</div>',
        unsafe_allow_html=True
    )

# Entry point for the Streamlit application
if __name__ == "__main__":
    main()
