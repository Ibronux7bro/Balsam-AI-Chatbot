from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import google.generativeai as genai
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

# Initialize Gemini safely
AI_AVAILABLE = False
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        AI_AVAILABLE = True
        print(f"Gemini AI configured successfully.")
    else:
        print("WARNING: No GEMINI_API_KEY found. Running in KB-only fallback mode.")
except Exception as e:
    print(f"WARNING: Failed to configure Gemini: {e}. Running in KB-only fallback mode.")

# Load Knowledge Base
def load_kb():
    if os.path.exists("knowledge_base.txt"):
        with open("knowledge_base.txt", "r", encoding="utf-8") as f:
            return f.read()
    return "No knowledge base found."

KB_CONTENT = load_kb()

# Remove diacritics function
def strip_diacritics(text):
    return re.sub(r'[\u064B-\u065F\u0670]', '', text)

# Local KB search function
def search_kb(user_input):
    kb_lines = KB_CONTENT.split('\n')
    user_input_clean = strip_diacritics(user_input.lower())
    user_words = [word for word in user_input_clean.split() if len(word) > 2]
    
    results = []
    for line in kb_lines:
        line_clean = strip_diacritics(line.lower())
        if any(word in line_clean for word in user_words) and len(line.strip()) > 15:
            clean_line = line.replace('**', '').strip()
            if clean_line.startswith('#'):
                continue
            results.append(clean_line)
            if len(results) >= 3:
                break
    
    return '\n'.join(results) if results else ""

@app.route('/chat', methods=['POST'])
def chat():
    try:
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

        # Try AI models if available
        if AI_AVAILABLE:
            models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
            for model_name in models_to_try:
                try:
                    current_model = genai.GenerativeModel(model_name)
                    response = current_model.generate_content(prompt)
                    if response and response.text:
                        return jsonify({"answer": response.text})
                except Exception as e:
                    print(f"Model {model_name} failed: {e}")
                    continue

        # LOCAL FALLBACK - Search Knowledge Base
        print("Using local KB search fallback.")
        best_match = search_kb(user_input)

        if best_match:
            return jsonify({"answer": best_match})

        return jsonify({"answer": "لم أستطع العثور على إجابة دقيقة. يرجى استشارة طبيب مختص.\nI couldn't find a precise answer. Please consult a doctor."})

    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({"answer": "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى."})

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
