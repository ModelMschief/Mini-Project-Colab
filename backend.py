import os
import time
import sys
import asyncio
from quart import Quart, request, Response, jsonify
from quart_cors import cors
from groq import AsyncGroq
from groq import APIError # Groq's equivalent of an API Error
import uuid

# Note: This will trigger the loading of the model and DB into RAM
try:
    from rag_engine.vector_search import fast_search
except Exception as e:
    print(f"CRITICAL: Could not load RAG engine. Ensure DB is built. Error: {e}")
    sys.exit(1)
import apis


API_KEY_HARDCODED = apis.api 
MONGO_URI = apis.mongo_uri  
session_timeout = 600
sessions = {}
HISTORY_THRESHOLD = 6

app = Quart(__name__, static_folder='static', template_folder='static')
app = cors(app) 


try:
    if API_KEY_HARDCODED == "YOUR_VALID_GROQ_API_KEY_HERE":
        print("ERROR: Please update API_KEY_HARDCODED in app.py with your GROQ Key.")
        sys.exit(1)
        
    client = AsyncGroq(api_key=API_KEY_HARDCODED)
    SUMMARY_MODEL = "llama-3.1-8b-instant" 
    FINAL_MODEL = "llama-3.3-70b-versatile"
    
except Exception as e:
    print(f"FATAL ERROR initializing Groq client: {e}")
    sys.exit(1)


#  Helper: Validate and Update Session 
async def validate_session(session_id):
    if not session_id or session_id not in sessions:
        return False
        
    current_time = time.time()
    # Access the timestamp inside the session dictionary
    last_activity = sessions[session_id]['last_activity']
    
    if (current_time - last_activity) > session_timeout:
        # clean up RAM and return False
        del sessions[session_id]
        return False
        
    # Valid session: Update activity timestamp (Sliding Window)
    sessions[session_id]['last_activity'] = current_time
    return True

async def get_ai_ready_history(session_id):

    session = sessions[session_id]

    memory = session['memory_summary']
    recent = session['recent_history']

    # If too many recent messages, summarize them into memory
    if len(recent) >= HISTORY_THRESHOLD:

        history_string = "\n".join([f"{m['role']}: {m['content']}" for m in recent])

        if memory:
            history_string = f"Previous memory:\n{memory}\n\nNew conversation:\n{history_string}"

        summary_res = await client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[
                {"role": "system", "content": "Summarize this conversation memory while preserving key facts and user goals and user names."},
                {"role": "user", "content": history_string}
            ]
        )

        session['memory_summary'] = summary_res.choices[0].message.content
        session['recent_history'] = []

    ai_messages = []

    if session['memory_summary']:
        ai_messages.append({
            "role": "system",
            "content": f"Conversation memory: {session['memory_summary']}"
        })

    ai_messages.extend(session['recent_history'])

    return ai_messages

# --- ROUTING ---
@app.route('/get_userinfo', methods=['POST'])
async def get_userinfo():
    data = await request.get_json()
    sid = data.get('session_id')
    name = data.get('name')
    contact = data.get('contact')
    
    # Ensure we ALWAYS return a response
    if not sid or sid not in sessions:
        return jsonify({"status": "error", "message": "Session not found. Please start a chat first."}), 401

    try:
        sessions[sid]['user_name'] = name
        sessions[sid]['user_contact'] = contact
        print(f"DEBUG: Profile updated for {name}")
        return jsonify({"status": "success", "message": "Profile updated"}), 200
    except Exception as e:
        print(f"ERROR updating user info: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/get-session', methods=['GET'])
async def get_session():
    sid = str(uuid.uuid4())
    sessions[sid] = {
    'last_activity': time.time(),
    'memory_summary': "",
    'recent_history': [],
    'full_history': [],  # optional, only for frontend reload
    'user_name': None,
    'user_contact': None
    }
    return jsonify({"session_id": sid})

@app.route('/get-history', methods=['POST'])
async def get_history():
    try:
        data = await request.get_json()
        sid = data.get('session_id') if data else None
        
        # Return empty history for unknown/expired sessions instead of 401
        # This prevents the frontend from destroying its session state
        if not sid or sid not in sessions:
            return jsonify({"history": []})
        
        if await validate_session(sid):
            return jsonify({"history": sessions[sid]['full_history']})
        
        # Session expired — return empty history gracefully
        return jsonify({"history": []})
    except Exception as e:
        print(f"ERROR in get-history: {e}")
        return jsonify({"history": []})

# --- Route: Streaming Chat with History Persistence ---
@app.route('/stream-chat', methods=['POST'])
async def stream_chat():
    data = await request.get_json()
    user_prompt = data.get('prompt', '')
    session_id = data.get('session_id', '')
    
    print(f"\n[DEBUG] Received prompt: {user_prompt}")

    if not session_id or session_id not in sessions:
        # Re-initialize the session in RAM if it's missing (e.g. after restart)
        session_id = session_id or str(uuid.uuid4())
        sessions[session_id] = {
            'last_activity': time.time(),
            'memory_summary': "",
            'recent_history': [],
            'full_history': [],
            'user_name': None,
            'user_contact': None
        }
        print(f"DEBUG: Session {session_id} re-initialized on-the-fly.")
    else:
        # Refresh the activity timer for existing sessions
        sessions[session_id]['last_activity'] = time.time()

    # Session is guaranteed valid at this point (re-created or refreshed above)
    
    # 2. Append history and get history context
    sessions[session_id]['recent_history'].append({"role": "user", "content": user_prompt})
    sessions[session_id]['full_history'].append({"role": "user", "content": user_prompt})
    ai_history = await get_ai_ready_history(session_id)
    user_name = sessions[session_id].get('user_name') or "User"

    # 3. Define the Streaming Generator
    async def generate():
        try:
            # Move retrieval and shortening INSIDE the generator to prevent 500 timeouts
            results, _ = await asyncio.to_thread(fast_search, user_prompt, top_k=5)
            raw_context = "\n".join(results['documents'][0])

            # Initialize with a fallback in case the AI shortener fails
            concise_context = "No specific context found."
            
            try:
                shortener_response = await client.chat.completions.create(
                    model=SUMMARY_MODEL,
                    messages=[
                        {"role": "system", "content": "Extract only relevant info for the user question."},
                        {"role": "user", "content": f"User Question: {user_prompt}\n\nContext: {raw_context}"}
                    ]
                )
                concise_context = shortener_response.choices[0].message.content
                print(f"[DEBUG] Concise Context Prepared \n {concise_context}")
            except Exception as e:
                print(f"Warning: AI Shortener failed: {e}")

            # 4. Final Answer Generation
            full_res = ""
            response_stream = await client.chat.completions.create(
                model=FINAL_MODEL,
                messages=ai_history + [
                    {"role": "system", "content": f"YOUR NAME IS 'GraceBot' freindly charming dude. Helping {user_name}. Context: {concise_context}"},
                    {"role": "user", "content": user_prompt}
                ],
                stream=True
            )
            
            async for chunk in response_stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_res += content 
                    yield content
            
            # 5. Finalize history update
            sessions[session_id]['recent_history'].append({"role": "assistant", "content": full_res})
            sessions[session_id]['full_history'].append({"role": "assistant", "content": full_res})

        except Exception as e:
            print(f"CRITICAL STREAM ERROR: {e}")
            yield f"⚠️ GraceBot encountered an error: {str(e)}"

    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':

    print("🚀 Flask Groq server starting...")
    app.run(debug=True, host='127.0.0.1', port=5000)