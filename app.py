from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google import genai
from dotenv import load_dotenv
import os
import tempfile

# Load environment variables
load_dotenv()

api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
if not api_key:
    raise ValueError("Gemini API key was not found.")

client = genai.Client(api_key=api_key)

app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/upload_resume.html")
def upload_page():
    return send_from_directory(".", "upload_resume.html")

@app.route("/analyze-resume", methods=["POST"])
def analyze_resume():
    if "resume" not in request.files:
        return jsonify({
            "success": False,
            "error": "No resume file was uploaded."
        }), 400

    resume = request.files["resume"]

    if resume.filename == "":
        return jsonify({
            "success": False,
            "error": "No file was selected."
        }), 400

    file_extension = os.path.splitext(resume.filename)[1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
        resume.save(temp_file.name)
        file_path = temp_file.name

    try:
        uploaded_file = client.files.upload(file=file_path)

        prompt = """
You are a professional resume information extraction AI.
Carefully read the uploaded resume and extract ONLY information that is actually present.
DO NOT invent or assume information.

Return a raw JSON object with this exact structure:
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

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, uploaded_file]
        )

        return jsonify({
            "success": True,
            "raw_analysis": response.text
        })

    except Exception as error:
        print("ERROR:", error)
        return jsonify({
            "success": False,
            "error": str(error)
        }), 500

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    app.run(debug=True)
