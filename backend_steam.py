import os
import time
import sys
from flask import Flask, request, Response, send_from_directory
from flask_cors import CORS
from groq import Groq
from groq import APIError # Groq's equivalent of an API Error

import apis

# ⚠️ SECURITY WARNING: Replace the placeholder with your valid GROQ API key.
# This key must be valid for the high-limit free tier to work.
API_KEY_HARDCODED = apis.groq_api  # <-- MAKE SURE THIS LOADS YOUR GROQ KEY

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
    """Handles the POST request, calls Groq in streaming mode, and yields chunks."""
    
    # 1. Get the prompt from the frontend JSON request
    try:
        data = request.get_json()
        prompt = data.get('prompt', 'Hello, tell me a fun fact.')
    except Exception:
        return Response("Error: Invalid JSON request", status=400)

    # 2. Define the generator function for streaming
    def generate():
        try:
            # Start the streaming chat completion call to the Groq API
            response_stream = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                stream=True
            )

            # Yield each chunk from the model directly to the client
            for chunk in response_stream:
                content = chunk.choices[0].delta.content
                if content:
                    # Send the raw text chunk. The frontend will process this.
                    yield content

        except APIError as e:
            # Handle Groq API errors gracefully (e.g., 401 Invalid Key, 429 Rate Limit)
            yield f"\n\n[API Error: Could not generate response from Groq. Details: {e.code} - {e.body.get('error', {}).get('message', 'Unknown error')}]"
        except Exception as e:
            yield f"\n\n[Server Error: An unexpected error occurred: {e}]"

    # 3. Return a Flask streaming response object
    # Mimetype is text/plain. The frontend handles chunk processing.
    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    # Flask defaults to 127.0.0.1:5000
    print("🚀 Flask Groq server starting...")
    print("🌐 Open http://127.0.0.1:5000 in your browser to start chatting.")
    # Ensure you install the 'groq' library: pip install groq
    app.run(debug=True, host='127.0.0.1', port=5000)