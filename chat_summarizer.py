"""
chat_summarizer.py — Shared module for end-of-session chat summarization.

This is COMPLETELY SEPARATE from the in-memory conversation summary logic
(update_memory_summary / build_ai_history). This module is a one-time
end-of-session archival pipeline that:

  1. Chunks the full chat history respecting user→assistant pair boundaries
  2. Summarizes each chunk via the lightweight SUMMARY_MODEL
  3. Merges all chunk summaries via the FINAL_MODEL
  4. Saves the polished summary to MongoDB

Designed for Groq API free tier limits:
  - llama-3.1-8b-instant:    6,000 TPM, 30 RPM
  - llama-3.3-70b-versatile: 12,000 TPM, 30 RPM
"""

import asyncio
import math
from datetime import datetime, timezone

#  CONSTANTS
CHUNK_TOKEN_LIMIT = 4000       # Safe input budget per chunk (8b model has 6k TPM)
SUMMARY_MAX_WORDS = 200        # Each chunk summary capped at ~200 words
FINAL_TOKEN_LIMIT = 8000       # Safe input budget for final merge (70b has 12k TPM)
MIN_MESSAGES_FOR_SUMMARY = 4   # Skip summarization for very short chats
RATE_LIMIT_DELAY = 2.5         # Seconds between API calls (30 RPM = 1 every 2s)

#  TOKEN ESTIMATION
def estimate_tokens(text: str) -> int:
    """Estimate token count from text (word_count × 1.3, rounded up)."""
    if not text:
        return 0
    return math.ceil(len(text.split()) * 1.3)


def estimate_messages_tokens(messages: list) -> int:
    """Estimate total tokens for a list of message dicts."""
    total = 0
    for msg in messages:
        # Count role label overhead (~4 tokens) + content
        total += 4 + estimate_tokens(msg.get("content", ""))
    return total

#  SMART CHAT CHUNKING
def chunk_chat_history(messages: list, token_limit: int = CHUNK_TOKEN_LIMIT) -> list:
    """
    Split messages into chunks, never breaking a user→assistant pair.
    Each chunk ends on an assistant message (complete exchange).
    
    Returns: list of lists, each sub-list is a chunk of messages.
    """
    if not messages:
        return []

    total_tokens = estimate_messages_tokens(messages)

    # If everything fits in one chunk, return as-is
    if total_tokens <= token_limit:
        return [messages]

    chunks = []
    current_chunk = []
    current_tokens = 0

    for msg in messages:
        msg_tokens = 4 + estimate_tokens(msg.get("content", ""))

        # If adding this message would exceed the limit AND we have a complete pair
        if (current_tokens + msg_tokens > token_limit
                and current_chunk
                and current_chunk[-1].get("role") == "assistant"):
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(msg)
        current_tokens += msg_tokens

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


# ─────────────────────────────────────────────
#  CHUNK SUMMARIZATION
# ─────────────────────────────────────────────

def _format_chunk_as_text(chunk: list) -> str:
    """Format a list of messages into a readable conversation transcript."""
    lines = []
    for msg in chunk:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def summarize_chunk(client, chunk: list, model: str) -> str:
    """
    Summarize a single chunk of conversation.
    Returns a concise summary (≤200 words).
    """
    chunk_text = _format_chunk_as_text(chunk)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a conversation summarizer. Summarize the following "
                        "conversation segment into a concise paragraph. Preserve:\n"
                        "- User's name if mentioned\n"
                        "- Key topics discussed\n"
                        "- Questions asked and answers given\n"
                        "- Any decisions or conclusions reached\n\n"
                        "Keep the summary under 200 words. Be factual, do not invent."
                    )
                },
                {"role": "user", "content": chunk_text}
            ],
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[SUMMARIZER] Chunk summarization failed: {e}")
        # Fallback: return a truncated version of the conversation
        return chunk_text[:500] + "..."

#  MERGE SUMMARIES
async def merge_summaries(client, summaries: list, summary_model: str, final_model: str) -> str:
    """
    Merge multiple chunk summaries into one cohesive final summary.
    
    If combined summaries exceed FINAL_TOKEN_LIMIT, recursively reduce
    with SUMMARY_MODEL first, then do a final quality merge with FINAL_MODEL.
    """
    if len(summaries) == 1:
        return summaries[0]

    combined = "\n\n---\n\n".join(
        f"Segment {i+1}:\n{s}" for i, s in enumerate(summaries)
    )
    combined_tokens = estimate_tokens(combined)

    # If too large for FINAL_MODEL, reduce with SUMMARY_MODEL first
    if combined_tokens > FINAL_TOKEN_LIMIT:
        print(f"[SUMMARIZER] Combined summaries too large ({combined_tokens} tokens). Pre-reducing...")
        try:
            reduction = await client.chat.completions.create(
                model=summary_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Combine these conversation segment summaries into a single "
                            "cohesive summary. Preserve all key facts. Keep under 500 words."
                        )
                    },
                    {"role": "user", "content": combined}
                ],
                max_tokens=600
            )
            combined = reduction.choices[0].message.content.strip()
        except Exception as e:
            print(f"[SUMMARIZER] Pre-reduction failed: {e}")
            # Truncate as last resort
            combined = combined[:3000]

    # Final quality merge with the stronger model
    try:
        final = await client.chat.completions.create(
            model=final_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are creating a permanent record of a chat conversation. "
                        "Produce a well-written summary that captures:\n"
                        "- Who the user is (name, contact if known)\n"
                        "- What topics were discussed\n"
                        "- Key facts, answers, and conclusions\n"
                        "- The overall purpose/goal of the conversation\n\n"
                        "Write in third person. Be concise but complete."
                    )
                },
                {"role": "user", "content": f"Conversation summaries to merge:\n\n{combined}"}
            ],
            max_tokens=500
        )
        return final.choices[0].message.content.strip()
    except Exception as e:
        print(f"[SUMMARIZER] Final merge failed: {e}")
        return combined  # Return the unmerged summaries as fallback

#  MAIN PIPELINE
async def summarize_and_save(
    client,
    mongo_collection,
    session_id: str,
    full_history: list,
    user_name: str = None,
    user_contact: str = None,
    summary_model: str = "llama-3.1-8b-instant",
    final_model: str = "llama-3.3-70b-versatile"
) -> bool:
    """
    Full end-of-session summarization pipeline.
    
    1. Validates chat is worth summarizing (≥ MIN_MESSAGES_FOR_SUMMARY)
    2. Chunks the history respecting message pair boundaries
    3. Summarizes each chunk with rate limiting
    4. Merges all summaries into a polished final summary
    5. Saves to MongoDB
    
    Returns True on success, False on skip/failure.
    """
    # Guard: skip tiny chats
    if not full_history or len(full_history) < MIN_MESSAGES_FOR_SUMMARY:
        print(f"[SUMMARIZER] Skipping session {session_id[:8]}... ({len(full_history) if full_history else 0} messages < {MIN_MESSAGES_FOR_SUMMARY})")
        return False

    print(f"[SUMMARIZER] Starting summarization for session {session_id[:8]}... ({len(full_history)} messages)")

    # Step 1: Chunk
    chunks = chunk_chat_history(full_history, CHUNK_TOKEN_LIMIT)
    print(f"[SUMMARIZER] Split into {len(chunks)} chunks")

    # Step 2: Summarize each chunk
    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        print(f"[SUMMARIZER] Summarizing chunk {i+1}/{len(chunks)}...")
        summary = await summarize_chunk(client, chunk, summary_model)
        chunk_summaries.append(summary)

        # Rate limit: wait between API calls
        if i < len(chunks) - 1:
            await asyncio.sleep(RATE_LIMIT_DELAY)

    # Step 3: Merge
    if len(chunk_summaries) > 1:
        await asyncio.sleep(RATE_LIMIT_DELAY)
    print(f"[SUMMARIZER] Merging {len(chunk_summaries)} summaries...")
    final_summary = await merge_summaries(client, chunk_summaries, summary_model, final_model)

    # Step 4: Save to MongoDB
    display_name = user_name if user_name else "anonymous"
    display_contact = user_contact if user_contact else None

    doc = {
        "session_id": session_id,
        "user_name": display_name,
        "user_email": display_contact,
        "type": "session_summary",
        "summary": final_summary,
        "message_count": len(full_history),
        "chunks_used": len(chunks),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summarized_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        await mongo_collection.insert_one(doc)
        print(f"[SUMMARIZER] ✅ Summary saved to MongoDB for '{display_name}' (session {session_id[:8]}...)")
        return True
    except Exception as e:
        print(f"[SUMMARIZER] ❌ MongoDB save failed: {e}")
        return False
