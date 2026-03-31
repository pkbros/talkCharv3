# =============================================================================
# tts_service.py
# =============================================================================
# PURPOSE:
#   Takes one sentence dict from llm_service.py and turns it into a complete
#   payload ready to send to the frontend over WebSocket.
#
# WHAT IT DOES, STEP BY STEP:
#   1. Receives: {"text": "Hey!", "emotion": "happy", "pose": "wave"}
#   2. Maps our emotion name → Cartesia's emotion name + speed ratio
#   3. Builds a transcript string with Cartesia SSML tags prepended
#   4. Calls Cartesia's SSE stream with add_phoneme_timestamps=True
#   5. Collects two things from the stream:
#        a. Audio chunks  → raw PCM bytes (32-bit float, 44100 Hz)
#        b. Phoneme events → list of {phoneme, start, end} for lip sync
#   6. Concatenates all audio bytes → encodes as base64 string
#   7. Returns one complete payload dict
#
# CARTESIA SSML (from the docs):
#   Cartesia does NOT use standard W3C SSML like <prosody rate="fast">.
#   It has its own simpler tags that go BEFORE the spoken text:
#
#     <speed ratio="1.2"/>       → 0.6 (slow) to 1.5 (fast)
#     <emotion value="happy"/>   → sets emotional delivery of the voice
#
#   Example full transcript string sent to Cartesia:
#     '<emotion value="happy"/><speed ratio="1.2"/>Hey, that is great news!'
#
# IMPORTANT: Use sonic-3 model only. Emotion controls are sonic-3 exclusive.
#            Use one of the "Emotive" tagged voices for best results.
#
# CALLED BY: main.py — runs inside a ThreadPoolExecutor because the
#            Cartesia Python SDK is synchronous (blocking), not async.
# =============================================================================

import base64
import os
from dotenv import load_dotenv
from cartesia import Cartesia

load_dotenv()


# ─── CONFIG ───────────────────────────────────────────────────────────────────

CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
if not CARTESIA_API_KEY:
    raise ValueError("🚨 CARTESIA_API_KEY is missing! Add it to your backend/.env file.")

# Voice ID. Must be one of Cartesia's "Emotive" voices for emotion tags to work.
# Default: Tessa — clear, expressive female voice.
# Other good options (from docs):
#   Leo:   0834f3df-e650-4766-a20c-5a93a43aa6e3
#   Jace:  6776173b-fd72-460d-89b3-d85812ee518d
#   Maya:  cbaf8084-f009-4838-a096-07ee2e6612b1
#   Kyle:  c961b81c-a935-4c17-bfb3-ba2239de8c2f
CARTESIA_VOICE_ID = os.getenv(
    "CARTESIA_VOICE_ID",
    "6ccbfb76-1fc6-48f7-b71d-91ac6298247b"  # Tessa
)

# sonic-3 is REQUIRED. Emotion SSML tags only work on sonic-3.
CARTESIA_MODEL = "sonic-3"

# Audio format requested from Cartesia.
# raw + pcm_f32le = uncompressed 32-bit float audio, little-endian byte order.
# This is raw samples with NO file header — not a WAV or MP3.
# The frontend decodes this manually using the Web Audio API.
# Sample rate 44100 Hz = CD quality audio.
AUDIO_FORMAT = {
    "container": "raw",
    "encoding":  "pcm_f32le",
    "sample_rate": 44100,
}

# Create the Cartesia client once at module load time.
# It gets reused for every sentence — no need to reconnect each time.
cartesia_client = Cartesia(api_key=CARTESIA_API_KEY)


# ─── EMOTION MAPPING ──────────────────────────────────────────────────────────
# Our character has 8 emotions defined in llm_prompts.py.
# Cartesia has its own emotion vocabulary (from the docs).
# This dict maps ours → theirs, plus a speed ratio for each.
#
# Speed ratio rules (from Cartesia docs):
#   0.6 = slowest possible
#   1.0 = normal speed (default)
#   1.5 = fastest possible
#
# We also map to Cartesia's emotion strings. Their primary supported ones are:
#   neutral, angry, excited, content, sad, scared
# (These have the most training data and most reliable results.)
# We use extended ones like "surprised" and "confused" where appropriate —
# they may be less reliable but are still in their supported list.

CARTESIA_EMOTION_MAP = {
    # our emotion  →  (cartesia emotion string,  speed ratio)
    "neutral":   ("neutral",   1.0),   # Default — no change to delivery
    "happy":     ("excited",   1.15),  # "excited" is closest to happy in Cartesia vocab
    "excited":   ("excited",   1.3),   # Fast and high energy
    "sad":       ("sad",       0.8),   # Slow and low
    "confused":  ("confused",  0.95),  # Slightly hesitant
    "thinking":  ("contemplative", 0.85),  # Slow and deliberate
    "surprised": ("surprised", 1.2),   # Quick reaction
    "angry":     ("angry",     1.0),   # Firm, controlled pace
}

# Fallback if an unmapped emotion somehow slips through
DEFAULT_CARTESIA_EMOTION = ("neutral", 1.0)


# ─── SSML BUILDER ─────────────────────────────────────────────────────────────

def _build_transcript(text: str, emotion: str) -> str:
    """
    Prepend Cartesia SSML tags to the plain text.

    Cartesia SSML tags sit BEFORE the spoken text in the transcript string.
    They are not XML wrappers — they're self-closing prefixes.

    Output example:
      '<emotion value="excited"/><speed ratio="1.3"/>Oh, that is so cool!'

    Args:
        text:    Plain text sentence. e.g. "Oh, that is so cool!"
        emotion: Our emotion key. e.g. "excited"

    Returns:
        Full transcript string with SSML tags prepended.
    """
    # Look up the Cartesia emotion name and speed ratio for this emotion.
    # If the emotion isn't in our map (shouldn't happen after validation),
    # fall back to neutral defaults.
    cartesia_emotion, speed_ratio = CARTESIA_EMOTION_MAP.get(
        emotion, DEFAULT_CARTESIA_EMOTION
    )

    # Build the SSML prefix string.
    # Note: These tags have NO closing tag — they're self-closing prefixes.
    #       The emotion tag sets the voice character.
    #       The speed tag adjusts the pace.
    ssml_prefix = f'<emotion value="{cartesia_emotion}"/><speed ratio="{speed_ratio}"/>'

    # Return the prefix + the plain text.
    # No escaping needed — the text field has already been validated as plain text
    # (no angle brackets) by the LLM's system prompt rules.
    transcript = ssml_prefix + text

    print(f"📝 [TTS] Transcript → {transcript!r}")
    return transcript


# ─── MAIN FUNCTION ────────────────────────────────────────────────────────────

def synthesize_sentence(sentence_data: dict) -> dict:
    """
    Send one sentence to Cartesia and collect the audio + phoneme timestamps.

    This function is SYNCHRONOUS (blocking). It waits for Cartesia to finish
    streaming all events before it returns. That's fine because:
      - It runs in a background thread (via ThreadPoolExecutor in main.py)
      - Cartesia is fast — typically <400ms for a short sentence
      - We need the complete audio buffer before we can send it over WebSocket

    Args:
        sentence_data: Dict from llm_service, e.g.:
                       {"text": "Hey!", "emotion": "happy", "pose": "wave"}

    Returns:
        Complete payload dict:
        {
            "text":         "Hey!",
            "emotion":      "happy",
            "pose":         "wave",
            "audio_base64": "<base64 encoded raw PCM f32le>",
            "sample_rate":  44100,
            "phonemes": [
                {"phoneme": "HH", "start": 0.0,   "end": 0.07},
                {"phoneme": "EY", "start": 0.07,  "end": 0.19},
                ...
            ]
        }
    """
    # Pull the three fields we need from the sentence dict.
    # .get() with a default prevents a KeyError if a field is somehow missing.
    text    = sentence_data.get("text",    "")
    emotion = sentence_data.get("emotion", "neutral")
    pose    = sentence_data.get("pose",    "idle")

    print(f"\n🎙️  [TTS] Synthesizing | emotion={emotion} | pose={pose}")
    print(f"         Text: {text!r}")

    # Step 1: Build the SSML-prefixed transcript string.
    transcript = _build_transcript(text, emotion)

    # Step 2: Open a streaming SSE connection to Cartesia.
    #
    # SSE = Server-Sent Events. Instead of one big response, Cartesia sends
    # a stream of small "events". Each event has a .type field:
    #
    #   "phoneme_timestamps" → phoneme timing data for this chunk of audio
    #   "chunk"              → a small buffer of raw audio bytes
    #   "done"               → stream is finished
    #   "error"              → something went wrong
    #
    # add_phoneme_timestamps=True tells Cartesia to send phoneme events.
    # Without this flag, we'd only get audio chunks — no lip sync data.
    stream = cartesia_client.tts.generate_sse(
        model_id=CARTESIA_MODEL,
        transcript=transcript,                          # Our SSML + text string
        voice={"mode": "id", "id": CARTESIA_VOICE_ID}, # Which voice to use
        output_format=AUDIO_FORMAT,                     # raw PCM f32le 44100Hz
        add_phoneme_timestamps=True,                    # ← CRITICAL for lip sync
    )

    # Step 3: Iterate the SSE event stream and collect data.
    audio_chunks  = []   # Will hold bytes objects from each "chunk" event
    phoneme_list  = []   # Will hold {phoneme, start, end} dicts

    for event in stream:

        if event.type == "phoneme_timestamps":
            # Phoneme timestamp events carry timing data for a group of phonemes.
            # event.phoneme_timestamps has three parallel lists:
            #   .phonemes → ["HH", "EY", "L", "OW"]
            #   .start    → [0.0,  0.07, 0.19, 0.28]  (seconds from audio start)
            #   .end      → [0.07, 0.19, 0.28, 0.40]  (seconds from audio start)
            #
            # We zip() them together so each phoneme has its own start+end.
            pt = event.phoneme_timestamps
            if pt and pt.phonemes:
                for phoneme, start, end in zip(pt.phonemes, pt.start, pt.end):
                    phoneme_list.append({
                        "phoneme": phoneme,  # e.g. "AH", "OW", "SH", "SIL"
                        "start":   start,    # float, seconds
                        "end":     end,      # float, seconds
                    })

        elif event.type == "chunk":
            # Audio chunk — raw bytes of PCM audio.
            # We collect all chunks and join them at the end into one buffer.
            # (Like downloading a file in pieces and assembling it at the end.)
            if event.audio:
                audio_chunks.append(event.audio)

        elif event.type == "done":
            # Stream is complete. Break out of the loop.
            break

        elif event.type == "error":
            # Cartesia reported an error. Raise it so main.py can catch it.
            raise Exception(f"🚨 [TTS] Cartesia stream error: {event.error}")

    # Step 4: Assemble the final audio buffer.
    # b"".join() is the efficient way to concatenate a list of bytes objects.
    # All the small chunks become one contiguous buffer of raw PCM samples.
    full_audio_bytes = b"".join(audio_chunks)

    # Step 5: Encode the raw audio bytes as a base64 string.
    # Why base64? WebSocket messages are text (JSON strings). We can't embed
    # raw binary bytes in a JSON string directly — base64 converts binary data
    # into a safe ASCII string that can travel inside JSON.
    # The frontend will decode this back into bytes and feed it to the Web Audio API.
    audio_base64 = base64.b64encode(full_audio_bytes).decode("utf-8")

    # Log a summary for debugging.
    print(f"✅ [TTS] Done | audio={len(full_audio_bytes):,} bytes | phonemes={len(phoneme_list)}")

    # Step 6: Build and return the complete payload dict.
    # This is exactly what main.py will JSON-encode and send over WebSocket.
    return {
        "text":         text,           # The spoken sentence (for transcript display)
        "emotion":      emotion,        # Frontend loads: /assets/emotions/<emotion>.png
        "pose":         pose,           # Frontend loads: /assets/poses/<pose>.png
        "audio_base64": audio_base64,   # Base64 raw PCM — frontend decodes and plays
        "sample_rate":  44100,          # Frontend needs this to configure AudioContext
        "phonemes":     phoneme_list,   # [{phoneme, start, end}] — for viseme scheduling
    }
