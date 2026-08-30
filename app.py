from flask import Flask, request, jsonify, send_from_directory
from google import genai
from dotenv import load_dotenv
import os
import tempfile


# -----------------------------
# LOAD ENVIRONMENT VARIABLES
# -----------------------------

load_dotenv()

api_key = os.getenv("GOOGLE_GEMINI_API_KEY")

if not api_key:
    raise ValueError("Gemini API key was not found.")


# -----------------------------
# CREATE GEMINI CLIENT
# -----------------------------

client = genai.Client(api_key=api_key)


# -----------------------------
# CREATE FLASK APP
# -----------------------------

app = Flask(__name__)


# -----------------------------
# OPEN YOUR WEBSITE
# -----------------------------

@app.route("/")
def home():

    return send_from_directory(".", "index.html")


@app.route("/upload_resume.html")
def upload_page():

    return send_from_directory(".", "upload_resume.html")


# -----------------------------
# ANALYZE RESUME
# -----------------------------

@app.route("/analyze-resume", methods=["POST"])
def analyze_resume():

    # Check if a file was uploaded

    if "resume" not in request.files:

        return jsonify({
            "success": False,
            "error": "No resume file was uploaded."
        }), 400


    resume = request.files["resume"]


    # Check filename

    if resume.filename == "":

        return jsonify({
            "success": False,
            "error": "No file was selected."
        }), 400


    # Save uploaded file temporarily

    file_extension = os.path.splitext(resume.filename)[1]

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=file_extension
    ) as temp_file:

        resume.save(temp_file.name)

        file_path = temp_file.name


    try:

        # -----------------------------
        # UPLOAD FILE TO GEMINI
        # -----------------------------

        uploaded_file = client.files.upload(
            file=file_path
        )


        # -----------------------------
        # PROMPT
        # -----------------------------

        prompt = """
You are a professional resume information extraction AI.

Carefully read the uploaded resume.

Extract ONLY information that is actually present
in the resume.

DO NOT invent, assume, or create information.

Extract:

1. Full name
2. Email
3. Phone number
4. Professional summary
5. Education
6. Skills
7. Projects
8. Work experience
9. Certifications
10. Achievements
11. LinkedIn URL
12. GitHub URL

Return the result as JSON.

Use an empty string if a single piece of
information is not available.

Use an empty array if a category has
no information.

Example structure:

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
"""


        # -----------------------------
        # SEND TO GEMINI
        # -----------------------------

        response = client.models.generate_content(

            model="gemini-3.7-flash",

            contents=[
                prompt,
                uploaded_file
            ]

        )


        # -----------------------------
        # SEND GEMINI RESPONSE
        # TO WEBSITE
        # -----------------------------

        return jsonify({
            "success": True,
            "data": response.text
        })


    except Exception as error:

        print("ERROR:", error)

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


    finally:

        # Delete temporary file

        if os.path.exists(file_path):

            os.remove(file_path)


# -----------------------------
# START SERVER
# -----------------------------

if __name__ == "__main__":

    app.run(
        debug=True
    )