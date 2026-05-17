from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
import os
import base64
from io import BytesIO
import asyncio
import edge_tts
import re

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# Load Knowledge Base
def load_kb():
    if os.path.exists("knowledge_base.txt"):
        with open("knowledge_base.txt", "r", encoding="utf-8") as f:
            return f.read()
    return "No knowledge base found."

KB_CONTENT = load_kb()

@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.json.get("message")
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    # System instructions
    system_instructions = (
        "You are 'Balsam', a professional, caring, and knowledgeable AI Health and First-Aid Assistant. "
        "YOUR PURPOSE IS STRICTLY TO PROVIDE FIRST-AID GUIDANCE AND GENERAL HEALTH INFO. "
        "IMPORTANT DISCLAIMER: Always remind the user that you are an AI, not a doctor, and they should call an ambulance (e.g., 998 in UAE) for real emergencies.\n"
        f"\nKnowledge Base Content (The Golden Rules):\n{KB_CONTENT}\n"
        "\nOPERATIONAL RULES:\n"
        "1. ONLY answer questions related to health, first-aid, CPR, emergencies, and symptoms as defined in the knowledge base.\n"
        "2. If a user asks about ANY OTHER TOPIC (like university rules, programming, sports), you MUST politely decline.\n"
        "3. Maintain a calm, reassuring, and professional medical tone.\n"
        "4. Always respond in the same language as the user.\n"
        "5. IMPORTANT: When responding in Arabic, YOU MUST FULLY DIACRITIZE (تشكيل كامل بالفتحة والضمة والكسرة) every single word in your response to ensure accurate Text-To-Speech pronunciation.\n"
        "\nINTERACTIVE SERVICES MOCKING:\n"
        "If a user asks for a service like calculating BMI (حساب مؤشر كتلة الجسم) or checking symptoms (تقييم الأعراض), you must act as an interactive agent. Ask them for the required details (Weight and Height for BMI, or detailed symptoms). Once provided, calculate the result or give advice based on their input."
    )
    prompt = f"{system_instructions}\n\nUser Question: {user_input}\nBalsam's Response:"

    # Try different models in case of quota/availability issues
    models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash-8b", "gemini-1.5-flash"]
    
    last_error = ""
    for model_name in models_to_try:
        try:
            current_model = genai.GenerativeModel(model_name)
            response = current_model.generate_content(prompt)
            if response and response.text:
                return jsonify({"answer": response.text})
        except Exception as e:
            last_error = str(e)
            print(f"Model {model_name} failed: {last_error}")
            continue

    # LOCAL FALLBACK
    print("All AI models failed. Using local KB search fallback.")
    user_input_lower = user_input.lower()
    is_query_arabic = any('\u0600' <= c <= '\u06FF' for c in user_input)
    
    sections = KB_CONTENT.split('##')
    relevant_text = ""
    relevant_text = load_kb()
    kb_lines = relevant_text.split('\n')
    best_match = ""
    
    # Remove diacritics function
    def strip_diacritics(text):
        return re.sub(r'[\u064B-\u065F\u0670]', '', text)

    user_input_lower = user_input.lower()
    user_input_clean = strip_diacritics(user_input_lower)

    for line in kb_lines:
        line_clean = strip_diacritics(line.lower())
        if any(word in line_clean for word in user_input_clean.split() if len(word) > 3) and len(line) > 15:
            clean_line = line.replace('**', '').strip()
            if ':' in clean_line: clean_line = clean_line.split(':')[-1].strip()
            elif '؟' in clean_line: clean_line = clean_line.split('؟')[-1].strip()
            best_match = clean_line
            break

    if best_match:
        return jsonify({"answer": best_match})

    return jsonify({"error": "I couldn't find a precise answer. Please consult a doctor. لم أستطع العثور على إجابة دقيقة. يرجى استشارة طبيب مختص."}), 500

@app.route('/tts', methods=['POST'])
def tts_generate():
    data = request.json
    text = data.get("text", "")
    lang = data.get("lang", "en")
    
    if not text:
        return jsonify({"error": "No text"}), 400
        
    try:
        voice = "ar-AE-FatimaNeural" if lang == "ar" else "en-US-AvaNeural"
        
        async def generate_speech():
            communicate = edge_tts.Communicate(text, voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
            
        audio_bytes = asyncio.run(generate_speech())
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        return jsonify({"audio": audio_b64})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
