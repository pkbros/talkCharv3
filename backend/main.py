# =============================================================================
# main.py
# =============================================================================
# PURPOSE:
#   This is the central nervous system of the backend.
#   It runs a WebSocket server that:
#     1. Accepts a connection from the React frontend
#     2. Receives the user's text message
#     3. Streams it through the LLM (llm_service.py) sentence by sentence
#     4. For each sentence, calls Cartesia TTS (tts_service.py)
#     5. Sends each complete payload to the frontend immediately
#     6. Sends a final "done" signal when everything is sent
#
# WHY WEBSOCKET AND NOT HTTP?
#   HTTP is one request → one response → connection closes.
#   WebSocket is a persistent two-way channel. The server can PUSH data
#   to the frontend at any time without the frontend asking.
#   We need this because we're streaming multiple sentence payloads
#   as they become ready — the frontend doesn't know how many are coming.
#
# WHY THREADPOOLEXECUTOR?
#   The LLM service (llm_service.py) is async — it uses Python's async/await.
#   The TTS service (tts_service.py) is synchronous — it BLOCKS while waiting
#   for Cartesia. If we called it directly inside an async function, it would
#   freeze the entire server for every other connected client.
#   run_in_executor() moves blocking code to a background thread, so the
#   async event loop stays free to handle other connections while Cartesia works.
#
# PIPELINE TIMING (why this feels fast):
#   LLM streams sentence 1 → TTS starts immediately → payload sent to frontend
#   While frontend plays sentence 1, LLM is already generating sentence 2
#   While sentence 2 goes through TTS, sentence 3 is being written by LLM
#   Each stage runs as soon as its input is ready — nothing waits for the whole.
#
# FILE STRUCTURE THIS TIES TOGETHER:
#   llm_prompts.py  → character config (imported by llm_service)
#   llm_service.py  → streams sentence dicts from Groq
#   tts_service.py  → converts each sentence dict to audio+phoneme payload
#   main.py         → WebSocket server that orchestrates the above two
# =============================================================================

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Import the two pipeline stages we built
from llm_service import generate_response  # async generator → sentence dicts
from tts_service import synthesize_sentence  # blocking function → payload dict

load_dotenv()

# ─── APP SETUP ────────────────────────────────────────────────────────────────

# FastAPI is our web framework. It handles both HTTP routes and WebSocket
# connections using the same event loop.
app = FastAPI(title="2D Character Backend")

# CORS = Cross-Origin Resource Sharing.
# Browsers block JavaScript from calling a server on a different origin
# (different port counts as different origin — localhost:5173 vs localhost:8000).
# This middleware tells the browser: "yes, the frontend is allowed to connect."
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: replace * with your exact frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for running the blocking TTS calls.
# max_workers=4 means up to 4 sentences can be synthesized simultaneously.
# In practice with one user, sentences are processed one at a time anyway —
# this headroom just helps if you add multi-user support later.
executor = ThreadPoolExecutor(max_workers=4)


# ─── WEBSOCKET ENDPOINT ───────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    The main WebSocket handler. Every frontend client that connects gets its
    own independent instance of this function running concurrently.

    ── MESSAGES FROM FRONTEND → BACKEND ──────────────────────────────────────

    The frontend sends JSON strings. Two formats are supported:

    Simple (no memory):
      {"text": "What is machine learning?"}

    With conversation history (multi-turn memory):
      {
        "text": "Tell me more about that",
        "history": [
          {"role": "user",      "content": "What is machine learning?"},
          {"role": "assistant", "content": "Machine learning is..."}
        ]
      }

    ── MESSAGES FROM BACKEND → FRONTEND ──────────────────────────────────────

    For each sentence:
      {
        "type":         "sentence",
        "text":         "Machine learning is a subset of AI.",
        "emotion":      "neutral",
        "pose":         "idle",
        "audio_base64": "<base64 encoded raw PCM f32le audio>",
        "sample_rate":  44100,
        "phonemes": [
          {"phoneme": "M",  "start": 0.0,   "end": 0.08},
          {"phoneme": "AH", "start": 0.08,  "end": 0.15},
          ...
        ]
      }

    After all sentences:
      {"type": "done"}

    On error:
      {"type": "error", "message": "Something went wrong: ..."}
    """

    # Accept the WebSocket handshake. Until this is called, the connection
    # is pending — the frontend is waiting for the server to acknowledge it.
    await websocket.accept()
    client_info = websocket.client  # Contains IP and port, useful for logging
    print(f"\n🔗 [WS] Client connected: {client_info}")

    try:
        # Keep listening for messages in a loop.
        # Each iteration handles one full user message + character response.
        # The loop continues until the client disconnects.
        while True:

            # Wait for the next message from the frontend.
            # This line BLOCKS (in an async way) until a message arrives.
            # While waiting, the event loop is free to serve other clients.
            raw_message = await websocket.receive_text()

            # ── PARSE THE INCOMING MESSAGE ────────────────────────────────

            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                # Frontend sent something that isn't valid JSON.
                # Tell it and go back to listening — don't crash.
                await _send(
                    websocket, {"type": "error", "message": "Invalid JSON received"}
                )
                continue

            # Extract the user's text. .strip() removes leading/trailing whitespace.
            user_text = message.get("text", "").strip()
            if not user_text:
                await _send(websocket, {"type": "error", "message": "Empty message"})
                continue

            # Extract optional conversation history for multi-turn memory.
            # If not provided, defaults to empty list → single-turn conversation.
            history = message.get("history", [])

            print(f"📨 [WS] Message from {client_info}: {user_text!r}")

            # ── PIPELINE: LLM → TTS → FRONTEND ───────────────────────────

            try:
                # Stage 1: Stream sentence dicts from the LLM.
                #
                # generate_response() is an ASYNC GENERATOR.
                # "async for" means: wait for each yielded value asynchronously.
                # Each iteration gives us one sentence dict as soon as the LLM
                # finishes writing that sentence — we don't wait for all of them.
                async for sentence_data in generate_response(user_text, history):
                    # sentence_data at this point:
                    # {"text": "Hey there!", "emotion": "happy", "pose": "wave"}

                    # Stage 2: Convert sentence to audio + phonemes via Cartesia.
                    #
                    # synthesize_sentence() is BLOCKING — it waits for Cartesia.
                    # We run it in a background thread using run_in_executor() so
                    # it doesn't freeze the async event loop.
                    #
                    # asyncio.get_event_loop() gets the currently running event loop.
                    # run_in_executor(executor, fn, arg) calls fn(arg) in a thread
                    # and returns an awaitable — so we can await it like any async call.
                    loop = asyncio.get_event_loop()
                    payload = await loop.run_in_executor(
                        executor,  # Thread pool to use
                        synthesize_sentence,  # The blocking function
                        sentence_data,  # Its single argument
                    )
                    # payload at this point:
                    # {
                    #   "text": "Hey there!", "emotion": "happy", "pose": "wave",
                    #   "audio_base64": "...", "sample_rate": 44100,
                    #   "phonemes": [{"phoneme": "HH", "start": 0.0, "end": 0.07}, ...]
                    # }

                    # Stage 3: Tag the payload with its type and send to frontend.
                    # The frontend checks message["type"] to know how to handle it.
                    payload["type"] = "sentence"
                    await _send(websocket, payload)
                    print(f"📤 [WS] Sent: {sentence_data['text']!r}")

                # All sentences have been sent. Tell the frontend we're done.
                # The frontend uses this signal to stop its "thinking" indicator
                # and know no more sentences are coming for this response.
                await _send(websocket, {"type": "done"})
                print(f"✅ [WS] Response complete for: {user_text!r}")

            except Exception as e:
                # Something broke in the LLM or TTS — log it and tell the frontend.
                # We don't crash the server — we continue listening for new messages.
                error_msg = f"Pipeline error: {str(e)}"
                print(f"🚨 [WS] {error_msg}")
                await _send(websocket, {"type": "error", "message": error_msg})

    except WebSocketDisconnect:
        # This is the normal way a connection ends.
        # The user closed the tab, refreshed, or lost network.
        # Not an error — just clean up and move on.
        print(f"🔌 [WS] Client disconnected: {client_info}")

    except Exception as e:
        # Unexpected crash at the connection level.
        print(f"🚨 [WS] Unexpected connection error: {e}")


# ─── HELPER: SEND JSON ────────────────────────────────────────────────────────


async def _send(websocket: WebSocket, data: dict):
    """
    Serialize a dict to JSON and send it over the WebSocket.

    We wrap this in a helper so we don't repeat json.dumps() everywhere,
    and so we have one place to add error handling for send failures.

    Args:
        websocket: The active WebSocket connection.
        data:      A dict. Will be JSON-encoded and sent as a text frame.
    """
    await websocket.send_text(json.dumps(data))


# ─── HTTP HEALTH CHECK ────────────────────────────────────────────────────────


@app.get("/")
async def root():
    """
    Basic HTTP check. Visit http://localhost:8000/ in a browser to confirm
    the server is running. Returns a simple JSON response.
    """
    return {"status": "ok", "message": "2D Character backend is running."}


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # uvicorn is the ASGI server that runs FastAPI.
    # ASGI = Asynchronous Server Gateway Interface — it's what allows FastAPI
    # to handle WebSockets and async code properly.
    #
    # Running this file directly with `python main.py` starts the server.
    # Alternatively use: `uvicorn main:app --reload` from the terminal.
    import uvicorn

    uvicorn.run(
        "main:app",  # "filename:FastAPI_instance_name"
        host="0.0.0.0",  # Listen on all network interfaces (not just localhost)
        port=8000,  # Frontend will connect to ws://localhost:8000/ws
        reload=True,  # Auto-restart server when you save any .py file
        log_level="info",  # Show info-level logs in the terminal
    )
