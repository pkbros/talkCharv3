import { useState, useRef, useEffect } from "react";

export const VoiceInput = ({ setChatInput, handleSend }) => {
    const [listening, setListening] = useState(false);
    const [text, setText] = useState("");
    const recognitionRef = useRef(null);
    const transcriptRef = useRef("");
    const isListeningRef = useRef(false); // source of truth for onend guard
    const setChatInputRef = useRef(setChatInput);
    const handleSendRef = useRef(handleSend);

    // Keep callback refs up to date on every render
    useEffect(() => {
        setChatInputRef.current = setChatInput;
        handleSendRef.current = handleSend;
    });

    useEffect(() => {
        const SpeechRecognition =
            window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            console.warn("Speech Recognition not supported in this browser.");
            return;
        }

        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.lang = "en-US";

        recognition.onresult = (event) => {
            const transcript = Array.from(event.results)
                .map(result => result[0].transcript)
                .join(" ");

            transcriptRef.current = transcript;
            setText(transcript);
            console.log("Recognized so far:", transcript);
        };

        recognition.onend = () => {
            // If user is still listening, restart recognition (browser ended the segment)
            if (isListeningRef.current) {
                recognition.start(); // restart to keep listening
                return;
            }

            // User clicked stop — now actually send
            setListening(false);
            if (transcriptRef.current) {
                setChatInputRef.current(transcriptRef.current);
                handleSendRef.current(transcriptRef.current);
                transcriptRef.current = "";
            }
        };

        recognition.onerror = (event) => {
            console.error("Speech recognition error:", event.error);
            isListeningRef.current = false;
            setListening(false);
        };

        recognitionRef.current = recognition;
    }, []);

    const handleListen = () => {
        const recognition = recognitionRef.current;
        if (!recognition) return;

        if (!isListeningRef.current) {
            setText("");
            transcriptRef.current = "";
            isListeningRef.current = true;
            setListening(true);
            recognition.start();
        } else {
            isListeningRef.current = false; // signal onend to not restart
            recognition.stop();
        }
    };

    return (
        <div>
            <button onClick={handleListen}>
                {listening ? "Stop Voice Input" : "Start Voice Input"}
            </button>
            <p>Output: {text}</p>
        </div>
    );
};

export default VoiceInput;