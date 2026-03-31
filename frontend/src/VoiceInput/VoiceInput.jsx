import { useState } from "react";
import Chat from "../chat/Chat";

export const VoiceInput = ({setChatInput, handleSend}) => {
    const [listening, setListening] = useState(false);
    const [text, setText] = useState("");

    // Browser speech recognition setup
    const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();

    recognition.continuous = false; // stop after pause
    recognition.interimResults = false; // only final results
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setText(transcript);
        console.log("Recognized:", transcript);
        handleVoiceSend(transcript);
        
    };

    recognition.onend = () => {
        setListening(false);
    };

    const startListening = () => {
        setListening(true);
        recognition.start();
    };

    const stopListening = () => {
        recognition.stop();
        setListening(false);
    };

    const handleListen = () => {
        if (!listening) {
            setListening(true);
            recognition.start();
        } else {
            recognition.stop();
            setListening(false);
        }

    };
    
    const handleVoiceSend = (transcript) => {
        const data = transcript ?? text;
        console.log("handle voice send from voice")
        setChatInput(data);
        handleSend(data);
    };

    return (
        <div>
            <button onClick={handleListen}>{!listening ? "Start Voice Input" : "Stop Voice Input"}</button>
            {/* <button onClick={startListening} disabled={listening}>
                🎤 Start Voice Input
            </button>
            <button onClick={stopListening} disabled={!listening}>
                ⏸ Stop
            </button> */}
            {/* <button onClick={() => handleVoiceSend(text)}>Press me</button> */}
            <p>Output: {text}</p>
        </div>
    );
};

export default VoiceInput;
