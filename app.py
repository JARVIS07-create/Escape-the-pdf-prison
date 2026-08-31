from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google import genai
from dotenv import load_dotenv

import os
import tempfile
import json


# ==========================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================

load_dotenv()

api_key = os.getenv("GOOGLE_GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "Gemini API key was not found. "
        "Make sure GOOGLE_GEMINI_API_KEY is present in your .env file."
    )

# Optional Supabase credentials — /api/save-portfolio works even without
# these, it just won't actually persist to Supabase until you add them.
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client

        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

        print("Supabase client initialized.")

    except ImportError:
        print(
            "SUPABASE_URL/SUPABASE_KEY are set but the 'supabase' "
            "package isn't installed. Run: pip install supabase"
        )

    except Exception as error:
        print("Could not initialize Supabase client:", error)

else:
    print(
        "SUPABASE_URL / SUPABASE_KEY not set — "
        "/api/save-portfolio will accept requests but won't persist "
        "anything to Supabase until you add them to .env."
    )


# ==========================================
# GEMINI CLIENT
# ==========================================

client = genai.Client(api_key=api_key)

# NOTE: verify this model name is still current in Google AI Studio —
# Gemini model names change fairly often. gemini-2.5-flash is a
# well-established, generally-available model as of writing.
GEMINI_MODEL = "gemini-2.5-flash"


# ==========================================
# FLASK APP
# ==========================================

app = Flask(__name__)

# FIX: CORS(app) currently allows every origin. Fine for local dev,
# but once this is deployed with real user data (especially with
# Supabase persistence turned on) restrict this to your actual
# frontend origin(s), e.g.:
#   CORS(app, resources={r"/*": {"origins": ["https://yourdomain.com"]}})
CORS(app)

# Maximum upload size = 10 MB
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# FIX: read debug/host/port from environment so this is safe to deploy
# as-is without editing code. Defaults preserve your original local
# dev behavior (debug on, default Flask host/port).
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
FLASK_HOST = os.getenv("HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("PORT", 5000))


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# ==========================================
# UPLOAD RESUME PAGE
# ==========================================

@app.route("/upload_resume.html")
def upload_page():

    return send_from_directory(
        ".",
        "upload_resume.html"
    )


# ==========================================
# ANALYZE RESUME
# ==========================================

@app.route("/analyze-resume", methods=["POST"])
def analyze_resume():

    # --------------------------------------
    # CHECK WHETHER FILE EXISTS
    # --------------------------------------

    if "resume" not in request.files:

        return jsonify({
            "success": False,
            "error": "No resume file was uploaded."
        }), 400


    resume = request.files["resume"]


    # --------------------------------------
    # CHECK FILE NAME
    # --------------------------------------

    if not resume.filename:

        return jsonify({
            "success": False,
            "error": "No file was selected."
        }), 400


    # --------------------------------------
    # CHECK FILE TYPE
    # --------------------------------------

    allowed_extensions = {
        ".pdf",
        ".docx"
    }

    file_extension = os.path.splitext(
        resume.filename
    )[1].lower()


    if file_extension not in allowed_extensions:

        return jsonify({
            "success": False,
            "error": "Only PDF and DOCX files are supported."
        }), 400


    # --------------------------------------
    # CHECK FILE SIZE
    # --------------------------------------

    resume.seek(0, os.SEEK_END)

    file_size = resume.tell()

    resume.seek(0)

    max_file_size = 10 * 1024 * 1024


    if file_size > max_file_size:

        return jsonify({
            "success": False,
            "error": "File size must be less than 10 MB."
        }), 400


    # --------------------------------------
    # CREATE TEMPORARY FILE
    # --------------------------------------

    file_path = None
    # FIX: track the Gemini-hosted file so we can delete it after use
    uploaded_file = None


    try:

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=file_extension
        ) as temp_file:

            resume.save(temp_file.name)

            file_path = temp_file.name


        print("\n========================================")
        print("Uploading resume to Gemini...")
        print("========================================")


        # ----------------------------------
        # UPLOAD FILE TO GEMINI
        # ----------------------------------

        uploaded_file = client.files.upload(
            file=file_path
        )


        print("Resume uploaded successfully.")


        # ----------------------------------
        # GEMINI PROMPT
        # ----------------------------------

        prompt = """
You are a professional resume information extraction AI.

Carefully read the uploaded resume.

Your task is to extract ONLY information that is actually
present in the resume.

IMPORTANT RULES:

1. DO NOT invent information.
2. DO NOT guess information.
3. DO NOT assume information.
4. If information is not present, return an empty string
   or empty array.
5. Keep the extracted information accurate.
6. Keep descriptions concise.
7. Return ONLY valid JSON.
8. Do NOT return Markdown.
9. Do NOT use ```json.
10. Do NOT include explanations or comments.

Use EXACTLY this JSON structure:

{
    "name": "",
    "email": "",
    "phone": "",
    "summary": "",
    "education": [],
    "skills": [],
    "projects": [],
    "experience": [],
    "certifications": [],
    "achievements": [],
    "linkedin": "",
    "github": ""
}

EDUCATION FORMAT:

"education": [
    {
        "degree": "",
        "institution": "",
        "year": ""
    }
]

PROJECT FORMAT:

"projects": [
    {
        "name": "",
        "description": ""
    }
]

EXPERIENCE FORMAT:

"experience": [
    {
        "job_title": "",
        "company": "",
        "duration": "",
        "description": ""
    }
]

SKILLS FORMAT:

"skills": [
    "Python",
    "SQL",
    "JavaScript"
]

CERTIFICATIONS FORMAT:

"certifications": [
    "Certification name"
]

ACHIEVEMENTS FORMAT:

"achievements": [
    "Achievement"
]

If a section does not exist in the resume,
return an empty array for that section.

Return JSON only.
"""


        # ----------------------------------
        # SEND RESUME TO GEMINI
        # ----------------------------------

        print("Gemini is analyzing the resume...")


        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                prompt,
                uploaded_file
            ]
        )


        # ----------------------------------
        # GET GEMINI RESPONSE
        # ----------------------------------

        raw_text = response.text.strip()


        print("\n========== GEMINI RESPONSE ==========\n")

        print(raw_text)

        print("\n=====================================\n")


        # ----------------------------------
        # CLEAN MARKDOWN CODE BLOCKS
        # ----------------------------------

        if raw_text.startswith("```"):

            raw_text = raw_text.replace(
                "```json",
                "",
                1
            )

            raw_text = raw_text.replace(
                "```",
                "",
                1
            )

            raw_text = raw_text.strip()


        # ----------------------------------
        # CONVERT JSON TO PYTHON DICTIONARY
        # ----------------------------------

        try:

            profile_data = json.loads(
                raw_text
            )

        except json.JSONDecodeError:

            print(
                "Gemini returned invalid JSON."
            )

            return jsonify({

                "success": False,

                "error":
                    "Gemini returned invalid JSON.",

                "raw_analysis":
                    raw_text

            }), 500


        # ----------------------------------
        # CHECK DATA TYPE
        # ----------------------------------

        if not isinstance(
            profile_data,
            dict
        ):

            return jsonify({

                "success": False,

                "error":
                    "Gemini returned an invalid data structure."

            }), 500


        # ----------------------------------
        # REQUIRED FIELDS
        # ----------------------------------

        required_fields = {

            "name": "",

            "email": "",

            "phone": "",

            "summary": "",

            "education": [],

            "skills": [],

            "projects": [],

            "experience": [],

            "certifications": [],

            "achievements": [],

            "linkedin": "",

            "github": ""

        }


        # ----------------------------------
        # ADD MISSING FIELDS
        # ----------------------------------

        for field, default_value in required_fields.items():

            if field not in profile_data:

                profile_data[field] = default_value


        # ----------------------------------
        # MAKE SURE LIST FIELDS ARE LISTS
        # ----------------------------------

        list_fields = [

            "education",

            "skills",

            "projects",

            "experience",

            "certifications",

            "achievements"

        ]


        for field in list_fields:

            if not isinstance(
                profile_data[field],
                list
            ):

                profile_data[field] = []


        # ----------------------------------
        # SEND DATA TO JAVASCRIPT
        # ----------------------------------

        return jsonify({

            "success": True,

            "data": profile_data

        })


    # ======================================
    # ERROR HANDLING
    # ======================================

    except Exception as error:

        print("\n========== ERROR ==========")

        print(error)

        print("===========================\n")

        # FIX: don't leak raw internal error strings (paths, SDK
        # internals, etc.) back to the client — log full detail
        # server-side, return a generic message to the caller.
        return jsonify({

            "success": False,

            "error": "Something went wrong while analyzing the resume."

        }), 500


    # ======================================
    # DELETE TEMPORARY FILE + GEMINI FILE
    # ======================================

    finally:

        if (
            file_path
            and os.path.exists(file_path)
        ):

            try:

                os.remove(file_path)

                print(
                    "Temporary file deleted."
                )

            except Exception as cleanup_error:

                print(
                    "Could not delete temporary file:",
                    cleanup_error
                )

        # FIX: also delete the file from Gemini's file storage —
        # otherwise every resume you process stays uploaded there
        # indefinitely.
        if uploaded_file:

            try:

                client.files.delete(name=uploaded_file.name)

                print("Gemini-hosted file deleted.")

            except Exception as cleanup_error:

                print(
                    "Could not delete Gemini-hosted file:",
                    cleanup_error
                )


# ==========================================
# SAVE PORTFOLIO (used by upload_resume.html
# after a successful analysis)
# ==========================================

@app.route("/api/save-portfolio", methods=["POST"])
def save_portfolio():

    profile_data = request.get_json(silent=True)

    if not profile_data or not isinstance(profile_data, dict):

        return jsonify({
            "success": False,
            "error": "No valid portfolio data received."
        }), 400

    # --------------------------------------
    # NO SUPABASE CONFIGURED — accept and
    # move on without erroring the frontend.
    # --------------------------------------

    if not supabase_client:

        print(
            "Received portfolio data (Supabase not configured, "
            "not persisted):",
            profile_data.get("name", "Unknown")
        )

        return jsonify({
            "success": True,
            "persisted": False,
            "message": "Supabase not configured — data was not saved server-side."
        })

    # --------------------------------------
    # SUPABASE CONFIGURED — upsert the row.
    # Adjust table/column names to match your
    # actual Supabase schema.
    # --------------------------------------

    try:

        result = (
            supabase_client
            .table("portfolios")
            .upsert(profile_data)
            .execute()
        )

        return jsonify({
            "success": True,
            "persisted": True,
            "data": result.data
        })

    except Exception as error:

        print("Supabase save error:", error)

        return jsonify({
            "success": False,
            "error": "Could not save portfolio."
        }), 500


# ==========================================
# STATIC FILES
# (must be registered LAST so it doesn't
# shadow the routes above)
# ==========================================

@app.route("/<path:filename>")
def static_files(filename):

    # FIX: block dotfiles (.env, .git/..., etc.) and any path that
    # tries to reach outside the current directory. send_from_directory
    # already blocks "../" traversal, but it will happily serve a
    # literal ".env" if requested by name — this closes that gap.
    normalized = filename.replace("\\", "/")

    if any(part.startswith(".") for part in
