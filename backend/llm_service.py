# =============================================================================
# llm_service.py
# =============================================================================
# PURPOSE:
#   Handles all communication with the LLM (Groq + Llama).
#   Streams the response token by token, assembles complete JSONL lines,
#   validates them, and yields clean sentence dicts one at a time.
#
# WHY STREAMING?
#   Without streaming, we'd wait for the ENTIRE LLM response before doing
#   anything. With streaming, we get the first sentence in ~300ms and can
#   immediately start the TTS pipeline for it — while the LLM is still
#   writing sentences 2, 3, 4...
#   This makes the character feel instant and alive, not laggy.
#
# OUTPUT:
#   An async generator that yields dicts like:
#   {"text": "Hey there!", "emotion": "happy", "pose": "wave"}
#
# CALLED BY: main.py (the WebSocket server)
# =============================================================================

import asyncio
import json
import os
from dotenv import load_dotenv
from groq import AsyncGroq
from llm_prompts import SYSTEM_PROMPT, EMOTIONS, POSES

# load_dotenv() reads your .env file and loads the variables into the environment.
# After this line, os.getenv("GROQ_API_KEY") will return your actual key.
load_dotenv()

# Fetch the Groq API key from the environment.
# We fail loudly here (at startup) rather than getting a cryptic error mid-conversation.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("🚨 GROQ_API_KEY is missing! Add it to your backend/.env file.")

# The Groq model to use.
# "llama-3.1-8b-instant" = very fast, good quality, free tier friendly.
# Change to "llama-3.3-70b-versatile" for smarter but slower responses.
LLM_MODEL = "llama-3.3-70b-versatile"

# Create the async Groq client. "Async" means it works with Python's async/await
# system so it doesn't block the server while waiting for a response.
client = AsyncGroq(api_key=GROQ_API_KEY)


# ─── HELPER: FIX COMMON LLM FORMATTING MISTAKES ───────────────────────────────

def _fix_missing_commas(line: str) -> str:
    """
    LLMs sometimes forget to put commas between JSON key-value pairs.
    This catches the most common patterns before we try to parse.

    Example of what this fixes:
      Input:  {"text": "Hello" "emotion": "happy", "pose": "idle"}
                              ↑ missing comma!
      Output: {"text": "Hello", "emotion": "happy", "pose": "idle"}
    """
    # These are the three places a comma is most often forgotten.
    # We check for a closing quote followed immediately by a space + opening quote-key.
    line = line.replace('" "emotion"', '", "emotion"')
    line = line.replace('" "pose"',    '", "pose"')
    line = line.replace('" "text"',    '", "text"')
    return line


# ─── HELPER: VALIDATE A PARSED JSON DICT ──────────────────────────────────────

def _validate(data: dict) -> dict | None:
    """
    Check a parsed JSON dict from the LLM and fix anything we can.
    Returns the cleaned dict if it's usable, or None if it's too broken.

    Three checks:
      1. "text" must exist and be a non-empty string. If not → discard.
      2. "emotion" must be in our allowed list. If not → reset to "neutral".
      3. "pose" must be in our allowed list. If not → reset to "idle".
    """

    # Check 1: We can't do anything without text to speak.
    text = data.get("text", "")
    if not isinstance(text, str) or not text.strip():
        print(f"⚠️  [LLM] Dropped line — missing or empty 'text': {data}")
        return None

    # Check 2: Validate emotion. LLMs sometimes hallucinate values like "calm",
    # "cheerful", "excited-but-not-too-much", etc. We silently fix them.
    if data.get("emotion") not in EMOTIONS:
        print(f"⚠️  [LLM] Unknown emotion '{data.get('emotion')}' → using 'neutral'")
        data["emotion"] = "neutral"

    # Check 3: Validate pose. Same issue — hallucinated values like "shock", "run".
    if data.get("pose") not in POSES:
        print(f"⚠️  [LLM] Unknown pose '{data.get('pose')}' → using 'idle'")
        data["pose"] = "idle"

    return data


# ─── MAIN FUNCTION ────────────────────────────────────────────────────────────

async def generate_response(user_message: str, conversation_history: list = None):
    """
    Send a user message to the LLM and stream back sentence dicts one at a time.

    This is an ASYNC GENERATOR — it uses "yield" instead of "return".
    The caller (main.py) loops over it with:
        async for sentence in generate_response(text):
            ...

    Args:
        user_message:         What the user typed or said.
        conversation_history: Optional list of previous turns for multi-turn memory.
                              Format: [{"role": "user", "content": "..."}, ...]

    Yields:
        dict — one validated sentence, e.g.:
        {"text": "Oh, interesting!", "emotion": "surprised", "pose": "idle"}
    """

    print(f"\n🧠 [LLM] New request: {user_message!r}")

    # Build the messages list for the API call.
    # Structure: [system prompt] + [past conversation] + [new user message]
    #
    # The system prompt always goes first — it's the character's "brain config".
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # If we have conversation history, inject it between system prompt and new message.
    # This gives the LLM memory of what was said before.
    if conversation_history:
        messages.extend(conversation_history)

    # Add the current user message at the very end.
    messages.append({"role": "user", "content": user_message})

    # ── Open a streaming connection to Groq ──────────────────────────────────
    # stream=True means Groq sends us tokens as they're generated,
    # rather than waiting for the full response.
    stream = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        stream=True,
        temperature=0.8,    # Controls creativity. 0.0 = robotic, 1.0 = chaotic. 0.8 = natural.
        max_tokens=1024,    # Max total tokens in the response. Prevents runaway long replies.
    )

    # ── Buffer: accumulate tokens until we have a complete line ───────────────
    # The LLM sends tiny pieces at a time. For example, the line:
    #   {"text": "Hey!", "emotion": "happy", "pose": "wave"}
    # might arrive as: '{"t'  →  'ext":'  →  ' "Hey!'  →  '", "emot'  → ...
    #
    # We add each piece to this buffer. When we see a newline character (\n),
    # we know we have a complete JSON line and can try to parse it.
    buffer = ""

    async for chunk in stream:
        # Each chunk from Groq contains a tiny piece of the response text.
        # chunk.choices[0].delta.content is the new text in this chunk.
        # It can be None at the end-of-stream, so we guard against that.
        content = chunk.choices[0].delta.content
        if not content:
            continue  # Skip empty chunks (usually the final end-of-stream signal)

        # Append the new piece to our running buffer.
        buffer += content

        # Check if we now have at least one complete line.
        # The LLM is supposed to end each JSON object with a newline character.
        if "\n" not in buffer:
            continue  # No complete line yet — keep buffering

        # Split on newlines. If buffer = 'line1\nline2\npartial', we get:
        #   lines = ['line1', 'line2', 'partial']
        lines = buffer.split("\n")

        # The last element might be an incomplete line (no closing \n yet).
        # We put it back in the buffer and process everything else.
        buffer = lines.pop()  # lines is now ['line1', 'line2'], buffer = 'partial'

        for line in lines:
            line = line.strip()

            # Skip blank lines — LLMs sometimes emit extra newlines.
            if not line:
                continue

            # Apply our defensive comma-fixing before attempting to parse.
            line = _fix_missing_commas(line)

            # Try to parse the line as JSON.
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                # The line is malformed JSON we can't fix. Log it and move on.
                # We do NOT crash the whole stream for one bad line.
                print(f"⚠️  [LLM] Unparseable line (skipping): {line!r}")
                continue

            # Validate and fix the parsed dict.
            validated = _validate(data)
            if validated:
                print(f"✅ [LLM] Sentence ready → {validated}")
                yield validated  # ← Hand this sentence to main.py for TTS processing

    # ── Flush the buffer after the stream ends ────────────────────────────────
    # The LLM's final line might not end with a newline character.
    # If the buffer has anything left after the loop, process it now.
    if buffer.strip():
        line = _fix_missing_commas(buffer.strip())
        try:
            data = json.loads(line)
            validated = _validate(data)
            if validated:
                print(f"✅ [LLM] Final sentence (from buffer) → {validated}")
                yield validated
        except json.JSONDecodeError:
            print(f"⚠️  [LLM] Could not parse final buffer: {line!r}")


# runner to test it right here:
async def main():
    async for item in generate_response("Who are you?"):
        print("Got: ", item)

if __name__ == "__main__":
    asyncio.run(main())