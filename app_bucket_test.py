import streamlit as st
import firebase_admin
from firebase_admin import credentials, storage
import json
import base64
import time
import os # For os.path.splitext, though not critical here

st.set_page_config(
    page_title="Firebase Storage Connectivity Test",
    layout="centered"
)

st.title("☁️ Firebase Storage Connectivity Test")
st.write("This app tests if your Streamlit deployment can successfully connect to and interact with your specified Firebase Storage bucket.")

# --- Configuration: Get from Streamlit Secrets ---
# Ensure these secrets are set in your .streamlit/secrets.toml
# FIREBASE_SERVICE_ACCOUNT_KEY_BASE64 and FIREBASE_STORAGE_BUCKET_NAME
FIREBASE_STORAGE_BUCKET_NAME = 'sso-recruitment-data.appspot.com' 

# --- Firebase Initialization Function ---
def initialize_firebase_app_test():
    """
    Initializes the Firebase Admin SDK for testing.
    """
    st.info("Attempting to initialize Firebase app...")
    print("DEBUG: Attempting to initialize Firebase app for test...")
    try:
        if "FIREBASE_SERVICE_ACCOUNT_KEY_BASE64" not in st.secrets:
            st.error("Firebase service account key (Base64) not found in Streamlit secrets.")
            st.stop() # Stop the app if secrets are missing

        firebase_service_account_key_base64_raw = st.secrets["FIREBASE_SERVICE_ACCOUNT_KEY_BASE64"].strip()
        print(f"DEBUG: Fetched secret. Length: {len(firebase_service_account_key_base64_raw)} chars.")
        
        # Decode the Base64 key
        decoded_key_bytes = base64.urlsafe_b64decode(firebase_service_account_key_base64_raw.encode('utf-8'))
        FIREBASE_SERVICE_ACCOUNT_CONFIG = json.loads(decoded_key_bytes)
        print("DEBUG: Service account key decoded and parsed.")
        
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_CONFIG)
        print("DEBUG: Firebase credentials created.")
        
        if not firebase_admin._apps:
            firebase_app_instance = firebase_admin.initialize_app(cred, {
                'storageBucket': FIREBASE_STORAGE_BUCKET_NAME 
            })
            st.success("Firebase app initialized!")
            print("DEBUG: Firebase app instance initialized for test.")
        else:
            firebase_app_instance = firebase_admin.get_app() 
            st.info("Firebase app already initialized, reusing existing instance.")
            print("DEBUG: Firebase app instance already initialized, reusing for test.")

        # Get the bucket client
        bucket = storage.bucket(FIREBASE_STORAGE_BUCKET_NAME, app=firebase_app_instance)
        st.session_state['test_bucket_client'] = bucket
        st.success(f"Successfully obtained bucket client for '{FIREBASE_STORAGE_BUCKET_NAME}'.")
        print(f"DEBUG: Successfully obtained bucket client for '{FIREBASE_STORAGE_BUCKET_NAME}'.")
        return bucket

    except Exception as e:
        st.error(f"Error during Firebase initialization or bucket client retrieval: {e}")
        print(f"ERROR: Firebase test initialization failed: {e}") 
        return None

# --- Main Test Logic ---
def run_bucket_test():
    """Performs tests on the Firebase Storage bucket."""
    bucket_client = initialize_firebase_app_test()

    if bucket_client:
        st.subheader("Bucket Existence Check")
        try:
            # The .exists() method is a good direct check for 404
            bucket_exists = bucket_client.exists() 
            if bucket_exists:
                st.success(f"Bucket '{FIREBASE_STORAGE_BUCKET_NAME}' **exists** and is accessible!")
                print(f"DEBUG: Bucket '{FIREBASE_STORAGE_BUCKET_NAME}' exists and is accessible.")
            else:
                st.error(f"Bucket '{FIREBASE_STORAGE_BUCKET_NAME}' does **NOT** exist or is not accessible via .exists()!")
                st.warning("This might indicate a persistent naming/visibility issue or a deeper GCP problem.")
                print(f"ERROR: Bucket '{FIREBASE_STORAGE_BUCKET_NAME}' does NOT exist or is not accessible via .exists().")
            
            st.subheader("Attempting to List Objects (Basic Read Test)")
            try:
                # Try listing a small number of blobs (objects)
                # This will often trigger permission/existence errors if they are present
                blobs_iterator = bucket_client.list_blobs(max_results=1)
                first_blob = next(blobs_iterator, None) # Get the first blob or None
                if first_blob:
                    st.success(f"Successfully listed an object: `{first_blob.name}`. Read access confirmed.")
                    print(f"DEBUG: Successfully listed object: {first_blob.name}. Read access confirmed.")
                else:
                    st.info("Bucket is empty or no objects matched. No read errors encountered so far.")
                    print("DEBUG: Bucket is empty or no objects matched. No read errors encountered.")

            except Exception as e:
                st.error(f"Error listing objects in bucket (read test failed): {e}")
                print(f"ERROR: Error listing objects (read test): {e}")

            st.subheader("Attempting a Dummy Upload (Write Test)")
            try:
                dummy_file_content = "This is a test file for Firebase Storage connectivity."
                dummy_file_name = f"test_uploads/connectivity_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                dummy_blob = bucket_client.blob(dummy_file_name)
                
                # Use upload_from_string for in-memory content
                dummy_blob.upload_from_string(dummy_file_content, content_type="text/plain")
                dummy_blob.make_public() # Try to make public to get a URL
                st.success(f"Successfully uploaded dummy file: [Link to Test File]({dummy_blob.public_url})")
                print(f"DEBUG: Successfully uploaded dummy file to: {dummy_blob.public_url}")

                st.info("Check your Firebase Console -> Storage -> Files tab to confirm the `test_uploads` folder and file exist.")
                
                # Attempt to delete the dummy file
                dummy_blob.delete()
                st.info("Successfully deleted dummy file after upload test.")
                print("DEBUG: Successfully deleted dummy file.")

            except Exception as e:
                st.error(f"Error during dummy file upload (write test failed): {e}")
                st.warning("A 404 here indicates the bucket is still not found/accessible for writes.")
                print(f"ERROR: Dummy upload (write test) failed: {e}")

        except Exception as e:
            st.error(f"An unexpected error occurred during bucket existence check: {e}")
            print(f"ERROR: Unexpected error during bucket existence check: {e}")
    else:
        st.error("Firebase bucket client could not be initialized. Check secrets and initialization logs.")

if st.button("Run Connectivity Test"):
    run_bucket_test()

st.markdown("---")
st.info("Make sure your Firebase service account key (Base64 encoded) and bucket name are correctly configured in `.streamlit/secrets.toml`.")
st.code("""
# .streamlit/secrets.toml
FIREBASE_SERVICE_ACCOUNT_KEY_BASE64="your_base64_encoded_service_account_json_here"
# (e.g., paste the content of your serviceAccountKey.json, then base64 encode it)

# The bucket name from Firebase Console -> Storage (e.g., your-project-id.appspot.com)
FIREBASE_STORAGE_BUCKET_NAME="sso-recruitment-data.appspot.com" 
""")
st.write("Ensure the `FIREBASE_STORAGE_BUCKET_NAME` in this app matches the one in your `secrets.toml` and actual Firebase/GCP bucket.")

