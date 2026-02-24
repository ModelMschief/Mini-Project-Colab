import os
import time
import sys
from flask import Flask, request, Response, send_from_directory
from flask_cors import CORS
from groq import Groq
from groq import APIError # Groq's equivalent of an API Error

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

# Route to serve the static HTML file


# The main chat streaming endpoint
@app.route('/stream-chat', methods=['POST'])
def stream_chat():
    data = request.get_json()
    user_prompt = data.get('prompt', '')
    print(f"\n[DEBUG] Received prompt: {user_prompt}")

    # 1. Broad Retrieval
    results, _ = fast_search(user_prompt, top_k=5)
    raw_context = "\n".join(results['documents'][0])

    # 2. AI Shortener (Synchronous call to Groq)
    shortener_response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{
            "role": "system", 
            "content": "Summarize the context below to be as short as possible while keeping all facts needed to answer the user question."
        },
        {"role": "user", "content": f"User Question: {user_prompt}\n\nContext: {raw_context}"}]
    )
    concise_context = shortener_response.choices[0].message.content
    print(f"\n[DEBUG] Concise Context:\n{concise_context}\n")
    time.sleep(0.5)  # Simulate processing delay

    # 3. Real Answer (Streaming call)
    def generate():
        response_stream = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": f"Use this summarized context and answer short and consize: {concise_context}"},
                {"role": "user", "content": user_prompt}
            ],
            stream=True
        )
        for chunk in response_stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    # Flask defaults to 127.0.0.1:5000
    print("🚀 Flask Groq server starting...")
    print("🌐 Open http://127.0.0.1:5000 in your browser to start chatting.")
    # Ensure you install the 'groq' library: pip install groq
    app.run(debug=True, host='127.0.0.1', port=5000)