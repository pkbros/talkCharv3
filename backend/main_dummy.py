import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            # Wait for a message from frontend
            data = await websocket.receive_text()
            print(f"Received from frontend: {data}")

            # Load JSON array from file
            with open("projectDetail.json", "r", encoding="utf-8") as file:
                payloads = json.load(file)

            # Send each JSON object one by one
            for payload in payloads:
                await websocket.send_json(payload)
                await asyncio.sleep(0.3)

            # ✅ After finishing, send a special marker
            await websocket.send_json(
                {"status": "done", "message": "All data sent, you can send more now."}
            )

    except WebSocketDisconnect:
        print("Client disconnected")
