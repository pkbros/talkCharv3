import asyncio
import json
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Pipeline imports
from llm_service import generate_response
from tts_service import synthesize_sentence

load_dotenv()

app = FastAPI(title="2D Character Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=4)
LOG_DIR = "debug_logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def save_to_log(filename: str, data: dict):
    """Appends traffic to a .jsonl file for debugging."""
    with open(filename, "a", encoding="utf-8") as f:
        entry = {"timestamp": datetime.now().isoformat(), **data}
        f.write(json.dumps(entry) + "\n")

async def _log(filename, direction, data):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, save_to_log, filename, {"dir": direction, "data": data})

async def _send(ws: WebSocket, data: dict, log_file: str):
    await ws.send_text(json.dumps(data))
    await _log(log_file, "out", data)

# ─── MAIN WEBSOCKET ───────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Setup session logging
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"session_{session_id}.jsonl")
    print(f"🔗 Connected. Logging to: {log_file}")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                await _log(log_file, "in", msg)
            except:
                continue

            user_text = msg.get("text", "")

            # ─── 1. CHECK FOR SPECIAL TRIGGER ───
            if "!describeYourself" in user_text:
                print("📁 Triggered: describeYourself")
                try:
                    with open("projectDetail.json", "r", encoding="utf-8") as f:
                        payloads = json.load(f)
                    
                    for p in payloads:
                        p["type"] = "project_item" # Helps frontend identify data
                        await _send(websocket, p, log_file)
                        await asyncio.sleep(0.3)
                    
                    await _send(websocket, {"type": "status", "status": "done"}, log_file)
                except Exception as e:
                    await _send(websocket, {"type": "error", "message": str(e)}, log_file)
                
                continue # Skip the normal AI logic

            # ─── 2. NORMAL AI LOGIC ───
            history = msg.get("history", [])
            try:
                async for sentence_data in generate_response(user_text, history):
                    # TTS Stage
                    loop = asyncio.get_event_loop()
                    payload = await loop.run_in_executor(executor, synthesize_sentence, sentence_data)
                    
                    payload["type"] = "sentence"
                    await _send(websocket, payload, log_file)

                await _send(websocket, {"type": "done"}, log_file)
            except Exception as e:
                await _send(websocket, {"type": "error", "message": str(e)}, log_file)

    except WebSocketDisconnect:
        print("🔌 Disconnected")

# ─── STARTUP ───
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)