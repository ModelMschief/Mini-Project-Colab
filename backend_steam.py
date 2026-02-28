import os
import time
import sys
from flask import Flask, request, Response, send_from_directory,jsonify
from flask_cors import CORS
from groq import Groq
from groq import APIError # Groq's equivalent of an API Error
import uuid


# Import your RAG search functions
# Note: This will trigger the loading of the model and DB into RAM
try:
    from rag_engine.vector_search import fast_search
except Exception as e:
    print(f"CRITICAL: Could not load RAG engine. Ensure DB is built. Error: {e}")
    sys.exit(1)
import apis
# ⚠️ SECURITY WARNING: Replace the placeholder with your valid GROQ API key.
# This key must be valid for the high-limit free tier to work.
API_KEY_HARDCODED = apis.api  # <-- MAKE SURE THIS LOADS YOUR GROQ KEY
session_timeout = 600
sessions = {}

# --- FLASK SETUP ---
app = Flask(__name__, static_folder='static', template_folder='static')
CORS(app) 

# --- GROQ SETUP ---
try:
    if API_KEY_HARDCODED == "YOUR_VALID_GROQ_API_KEY_HERE":
        print("ERROR: Please update API_KEY_HARDCODED in app.py with your GROQ Key.")
        sys.exit(1)
        
    # Initialize the Groq client
    client = Groq(api_key=API_KEY_HARDCODED)
    # Using the fast, high-limit free tier model confirmed in testing
    MODEL = "llama-3.1-8b-instant" 
    
except Exception as e:
    print(f"FATAL ERROR initializing Groq client: {e}")
    sys.exit(1)


# --- ROUTING ---

# --- Helper: Validate and Update Session ---
def validate_session(session_id):
    """Checks if session exists and is within the timeout window; resets timer if valid."""
    if not session_id or session_id not in sessions:
        return False
        
    current_time = time.time()
    # Access the timestamp inside the session dictionary
    last_activity = sessions[session_id]['last_activity']
    
    if (current_time - last_activity) > session_timeout:
        # Session expired: clean up RAM and return False
        del sessions[session_id]
        return False
        
    # Valid session: Update activity timestamp (Sliding Window)
    sessions[session_id]['last_activity'] = current_time
    return True

# --- Route: Initialize Session ---
@app.route('/get-session', methods=['GET'])
def get_session():
    """Generates a new session ID and initializes its history in RAM."""
    sid = str(uuid.uuid4())
    # Initialize session as a dictionary to support activity tracking and history
    sessions[sid] = {
        'last_activity': time.time(),
        'history': []
    }
    return jsonify({"session_id": sid})

# --- Route: Retrieve Chat History ---
@app.route('/get-history', methods=['POST'])
def get_history():
    """Returns the stored history for an active session ID."""
    data = request.get_json()
    sid = data.get('session_id')
    
    if validate_session(sid):
        return jsonify({"history": sessions[sid]['history']})
    
    # Return 401 so the frontend knows to clear the expired ID
    return jsonify({"error": "Expired"}), 401

# --- Route: Streaming Chat with History Persistence ---
@app.route('/stream-chat', methods=['POST'])
def stream_chat():
    data = request.get_json()
    user_prompt = data.get('prompt', '')
    session_id = data.get('session_id', '')
    
    print(f"\n[DEBUG] Received prompt: {user_prompt}")

    # 1. Validate session activity
    if not validate_session(session_id):
        # Return 401 for unauthorized/expired sessions
        return jsonify({"error": "Invalid or expired session"}), 401
    
    # 2. Append user prompt to history immediately
    sessions[session_id]['history'].append({"role": "user", "content": user_prompt})

    # 3. Broad Retrieval (RAG Logic)
    results, _ = fast_search(user_prompt, top_k=5)
    raw_context = "\n".join(results['documents'][0])

    # 4. AI Shortener Call
    shortener_response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "Summarize the context below to be as short as possible."},
            {"role": "user", "content": f"User Question: {user_prompt}\n\nContext: {raw_context}"}
        ]
    )
    concise_context = shortener_response.choices[0].message.content
    print(f"\n[DEBUG] Concise Context:\n{concise_context}\n")

    # 5. Real Answer (Streaming call)
    def generate():
        full_res = "" # Capture the full response to save to history
        
        # Include history context for conversational memory (Optional but Recommended)
        # To strictly use context + prompt as you have:
        response_stream = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": f"Use this summarized context: {concise_context}"},
                {"role": "user", "content": user_prompt}
            ],
            stream=True
        )
        
        for chunk in response_stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_res += content # Build the complete assistant message
                yield content
        
        # 6. Save assistant message to RAM history once stream completes
        sessions[session_id]['history'].append({"role": "assistant", "content": full_res})

    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    # Flask defaults to 127.0.0.1:5000
    print("🚀 Flask Groq server starting...")
    print("🌐 Open http://127.0.0.1:5000 in your browser to start chatting.")
    # Ensure you install the 'groq' library: pip install groq
    app.run(debug=True, host='127.0.0.1', port=5000)