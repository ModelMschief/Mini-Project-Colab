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
    history = sessions[session_id]['history']
    
    if len(history) < HISTORY_THRESHOLD:
        return history
    await asyncio.sleep(0.3)  # Simulate processing delay
    
    print(f"[DEBUG] History threshold hit ({len(history)}). Summarizing...")
    
    history_string = "\n".join([f"{m['role']}: {m['content']}" for m in history])
    
    summary_res = await client.chat.completions.create(
        model=SUMMARY_MODEL, 
        messages=[
            {"role": "system", "content": "You are a memory module. Summarize the following chat history into a detailed short paragraph. Focus on the user's specific questions, the core facts provided in the replies, and any unresolved topics. Maintain the context of the current goal."},
            {"role": "user", "content": history_string}
        ]
    )
    
    memory = summary_res.choices[0].message.content
    return [{"role": "system", "content": f"Previous conversation memory: {memory}"}]

# --- ROUTING ---
@app.route('/get-session', methods=['GET'])
async def get_session():
    sid = str(uuid.uuid4())
    sessions[sid] = {
        'last_activity': time.time(),
        'history': []
    }
    return jsonify({"session_id": sid})

@app.route('/get-history', methods=['POST'])
async def get_history():
    data = await request.get_json()
    sid = data.get('session_id')
    
    if await validate_session(sid):
        return jsonify({"history": sessions[sid]['history']})
    
    return jsonify({"error": "Expired"}), 401

# --- Route: Streaming Chat with History Persistence ---
@app.route('/stream-chat', methods=['POST'])
async def stream_chat():
    data = await request.get_json()
    user_prompt = data.get('prompt', '')
    session_id = data.get('session_id', '')
    
    print(f"\n[DEBUG] Received prompt: {user_prompt}")

    # 1. Validate session activity
    if not await validate_session(session_id):
        return jsonify({"error": "Invalid or expired session"}), 401
    
    ai_history = await get_ai_ready_history(session_id)
    
    sessions[session_id]['history'].append({"role": "user", "content": user_prompt})

    # 3. Broad Retrieval (RAG Logic)
    results, _ = await asyncio.to_thread(fast_search, user_prompt, top_k=5)
    raw_context = "\n".join(results['documents'][0])

    # 4. AI Shortener Call
    shortener_response = await client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages= [
            {"role": "system", "content": "Summarize the whole context below to be short as possible without losing the important informations"},
            {"role": "user", "content": f"User Question: {user_prompt}\n\nContext: {raw_context}"}
        ]
    )
    concise_context = shortener_response.choices[0].message.content
    print(f"\n[DEBUG] Concise Context:\n{concise_context}\n")

    # 5. Real Answer (Streaming call)
    async def generate():
        full_res = ""
        
        response_stream = await client.chat.completions.create(
            model=FINAL_MODEL,
            messages=ai_history + [
                {"role": "system", "content": f"YOUR NAME IS 'GraceBot'. Use this summarized context to answer the user query: {concise_context}"},
                {"role": "user", "content":f"Answer this friendly with 2 emojis: {user_prompt}"}
            ],
            stream=True
        )
        
        async for chunk in response_stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_res += content 
                yield content
        
        # 6. Save assistant message to RAM history once stream completes
        sessions[session_id]['history'].append({"role": "assistant", "content": full_res})
    await asyncio.sleep(0.3)  # slight delay to ensure streaming starts properly
    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':

    print("🚀 Flask Groq server starting...")
    app.run(debug=True, host='127.0.0.1', port=5000)