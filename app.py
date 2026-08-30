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


# ==========================================
# GEMINI CLIENT
# ==========================================

client = genai.Client(api_key=api_key)


# ==========================================
# FLASK APP
# ==========================================

app = Flask(__name__)

CORS(app)

# Maximum upload size = 10 MB
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


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
# STATIC FILES
# ==========================================

@app.route("/<path:filename>")
def static_files(filename):

    return send_from_directory(
        ".",
        filename
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
            model="gemini-3.6-flash",
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


        return jsonify({

            "success": False,

            "error": str(error)

        }), 500


    # ======================================
    # DELETE TEMPORARY FILE
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


# ==========================================
# RUN FLASK SERVER
# ==========================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
