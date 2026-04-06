#  AVNI: Animated Vector Neural Interface

> A real-time animated AI character that listens, thinks, and speaks with natural emotions and gestures.

![Status](https://img.shields.io/badge/status-stable-green) ![License](https://img.shields.io/badge/license-MIT-blue)

## ✨ Features

- **Live Character Animation** – Watch a 2D animated character respond in real-time with realistic lip-sync
- **AI-Powered Responses** – Leverages Groq's Llama LLM for intelligent, contextual conversations
- **Emotional Expression** – Character conveys emotions (neutral, happy, sad, etc.) through voice and pose
- **Natural Speech** – Cartesia TTS generates expressive, high-quality audio with precise phoneme timing
- **Streaming Pipeline** – No lag: LLM generates → TTS synthesizes → frontend renders, all in parallel
- **Voice Input** – Chat with the character using your microphone
- **Conversation Memory** – Multi-turn dialogue with full conversation history

## 🏗️ Architecture

AVNI follows a **streaming pipeline architecture** for minimal latency:

```
┌─────────────────┐
│   React/Vite    │ (Frontend - Animation & UI)
│   Web App       │
└────────┬────────┘
         │ WebSocket
         │ (persistent two-way channel)
         ▼
┌─────────────────────────────────┐
│   FastAPI WebSocket Server      │ (Backend Orchestrator)
│       (main.py)                  │
└────────┬────────────────────────┘
         │
    ┌────┴───┬──────────────┐
    ▼        ▼              ▼
  ┌───────┐ ┌────────┐ ┌──────────┐
  │ Groq  │ │Cartesia│ │ Frontend │
  │ Llama │ │   TTS  │ │ Renderer │
  │  LLM  │ │        │ │          │
  └───────┘ └────────┘ └──────────┘
```

### Why WebSocket?
- **HTTP**: One request → one response → close connection
- **WebSocket**: Persistent connection where the server can push data to the client anytime

This is crucial because we stream multiple sentence payloads as they become ready, without the frontend knowing how many are coming.

### Pipeline Flow
While the frontend **plays sentence 1**, the backend is already:
1. Generating sentence 2 in the LLM
2. Running TTS on sentence 3
3. All stages run in parallel → feels instant and alive

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+** (backend)
- **Node.js 18+** (frontend)
- **Groq API Key** (free: https://console.groq.com)
- **Cartesia API Key** 

### 1. Backend Setup

```bash
cd backend

# Create a virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn python-dotenv groq cartesia

# Create .env file with your API keys
cat > .env << EOF
GROQ_API_KEY=your_groq_key_here
CARTESIA_API_KEY=your_cartesia_key_here
EOF

# Start the server
python main.py
```

The backend runs on `http://localhost:8000`

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend runs on `http://localhost:5173`

### 3. Open in Browser
Visit `http://localhost:5173` and start chatting!

## 📁 Project Structure

```
talkCharv3/
├── backend/
│   ├── main.py                 # WebSocket server orchestration
│   ├── llm_service.py          # Groq Llama integration (streaming)
│   ├── tts_service.py          # Cartesia TTS integration
│   ├── llm_prompts.py          # Character personality & config
│   ├── ProjectDetail.json      # Reserved for future extensibility
│   └── .env                    # API keys (create this)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main app component
│   │   ├── chat/Chat.jsx       # Chat input & message handling
│   │   ├── Character/
│   │   │   └── Character.jsx   # 2D character renderer
│   │   ├── renderer/
│   │   │   ├── Player.jsx      # Animation player & phoneme sync
│   │   │   └── viseme_map.js   # Phoneme↔viseme (mouth shape) mapping
│   │   ├── VoiceInput/
│   │   │   └── VoiceInput.jsx  # Microphone capture
│   │   └── websockets/
│   │       └── websocket.js    # WebSocket client
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
│
└── README.md
```

## 🔌 Communication Protocol

### Frontend → Backend (WebSocket Message)

**Simple message** (no history):
```json
{
  "text": "What is machine learning?"
}
```

**With conversation history**:
```json
{
  "text": "Tell me more about that",
  "history": [
    {"role": "user", "content": "What is machine learning?"},
    {"role": "assistant", "content": "Machine learning is..."}
  ]
}
```

### Backend → Frontend (WebSocket Message)

**For each sentence**:
```json
{
  "type": "sentence",
  "text": "Machine learning is a subset of AI.",
  "emotion": "neutral",
  "pose": "idle",
  "audio_base64": "...",
  "sample_rate": 44100,
  "phonemes": [
    {"phoneme": "M", "start": 0.0, "end": 0.08},
    {"phoneme": "AH", "start": 0.08, "end": 0.15},
    ...
  ]
}
```

**When done**:
```json
{
  "type": "done"
}
```

**On error**:
```json
{
  "type": "error",
  "message": "Something went wrong: ..."
}
```

## ⚙️ Configuration

### Character Personality
Edit `backend/llm_prompts.py` to customize:
- Character name and personality
- Available emotions
- Available poses
- System prompt (character instructions)

Example emotions: `neutral`, `happy`, `sad`, `surprised`, `angry`
Example poses: `idle`, `wave`, `sit`, `stand`

### Animation Customization
- **Character visual**: Edit `frontend/src/Character/Character.jsx`
- **Mouth shapes (visemes)**: Update `frontend/src/renderer/viseme_map.js`
- **Animation timing**: Adjust in `frontend/src/renderer/Player.jsx`

## 🔧 How It Works (Technical Deep Dive)

### 1. LLM Streaming (llm_service.py)
- Sends user message to Groq's Llama model
- Receives response **token-by-token** (not waiting for full response)
- Parses JSONL format: each line is `{"text": "...", "emotion": "...", "pose": "..."}`
- Validates and fixes common LLM formatting errors
- Yields sentences one at a time as they become complete

### 2. TTS Processing (tts_service.py)
- Takes each sentence dict from LLM
- Maps our emotion names → Cartesia's emotion values ＋ speed ratios
- Builds SSML-like transcript with emotion/speed tags
- Calls Cartesia's streaming API with `add_phoneme_timestamps=True`
- Collects audio chunks and phoneme events
- Converts audio to base64 and packages with metadata

### 3. WebSocket Orchestration (main.py)
- Accepts WebSocket connection from frontend
- Runs LLM and TTS stages **concurrently** using `asyncio`:
  - LLM is async (doesn't block)
  - TTS is blocking → runs in `ThreadPoolExecutor` background thread
- Sends final payload to frontend as soon as each sentence is ready
- Maintains connection throughout conversation

### 4. Frontend Rendering (React)
- Receives sentence payloads from WebSocket
- Triggers character animation
- Maps phonemes to visemes (mouth shapes)
- Plays audio while syncing lip movement
- Displays emotion and pose transitions

## 🎮 Usage Examples

### Chat Mode
```
User: "Hello! What's your name?"
Character: [Animated speaking response with emotions]

User: "Can you explain quantum computing?"
Character: [Detailed explanation with natural expressions]
```

### Voice Input
Click the microphone icon and speak naturally. Your voice is transcribed and sent to the character.

### Multi-turn Conversation
The character remembers previous messages in the conversation and can reference them.

## 📊 Performance Considerations

- **Latency**: First sentence typically appears in **300-500ms**
- **Throughput**: Handles **concurrent users** (limited by API rate limits)
- **Audio Quality**: 44100 Hz PCM f32le (high quality, ~200KB per 10 seconds)
- **Animation**: 60 FPS smooth rendering on modern browsers

## 🛠️ Troubleshooting

### Backend issues:
- **"GROQ_API_KEY is missing"**: Create `.env` file with your API key
- **"CARTESIA_API_KEY is missing"**: Add Cartesia key to `.env`
- **WebSocket connection refused**: Check backend is running on `localhost:8000`

### Frontend issues:
- **WebSocket connection failed**: Ensure CORS is enabled (it is by default)
- **No character animation**: Check browser console for JavaScript errors
- **Audio not playing**: Check browser audio permissions

### Common fixes:
```bash
# Clear frontend cache
rm -rf frontend/node_modules
npm install

# Restart backend fresh
ctrl+c
python main.py

# Check environment variables
cat backend/.env
```

## 🔐 Security Notes

- **CORS**: Currently allows all origins. **For production**, replace `"*"` with your frontend URL in `main.py`
- **API Keys**: Never commit `.env` files. Keep them local only
- **Input validation**: All user inputs are sanitized before reaching the LLM

## 🚀 Deployment

### Backend (example: Railway or Heroku)
```bash
# In backend directory
pip freeze > requirements.txt
# Push to your platform with .env secrets configured
```

### Frontend (example: Vercel or Netlify)
```bash
cd frontend
npm run build
# Deploy the dist/ folder
```

**Important**: Update the frontend's WebSocket URL from `localhost:8000` to your production backend URL.

## 🤝 Contributing

This is a prototype project. Improvements welcome! Some ideas:
- [ ] Multi-character support
- [ ] Gesture recognition (wave hand to make character wave back)
- [ ] Background music/environmental audio
- [ ] 3D character models (Three.js integration)
- [ ] Language support beyond English

## 📝 License

MIT License – Feel free to use and modify!

## 🎯 Future Roadmap

- **v4**: 3D character models with rig-based animation
- **v5**: Real-time dialogue (voice input → live response without typing)
- **v6**: Multi-language support with auto-translation
- **v7**: Character customization (appearance, voice, personality)

## 📚 References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Groq API](https://console.groq.com)
- [Cartesia TTS](https://cartesia.ai/)
- [React Documentation](https://react.dev)
- [WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)

---

**Made with ❤️ as an experiment in AI-powered interactive characters**

Questions? Check out the inline code comments in `backend/main.py` – it's extensively documented!
