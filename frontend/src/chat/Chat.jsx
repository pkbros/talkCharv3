// src/chat/Chat.jsx
import React, { useState, useEffect } from "react";
import { createWebSocket, sendMessage, reciever } from "../websockets/websocket";
import VoiceInput from "../VoiceInput/VoiceInput";

export default function Chat({ onBatchReady }) {
    const [input, setInput] = useState("");
    const [currentBatch, setCurrentBatch] = useState([]);

    useEffect(() => {
        createWebSocket();
        reciever((data) => {
            setCurrentBatch((prev) => [...prev, data]);
        });
    }, []);

    // Notify parent whenever currentBatch changes
    useEffect(() => {
        if (onBatchReady) {
            onBatchReady(currentBatch);
        }
    }, [currentBatch, onBatchReady]);

    // Chat.jsx
    const handleSend = (msg) => {
        const toSend = msg ?? input;
        if (!toSend.trim()) return;
        console.log("input trimmed")
        setCurrentBatch([]); // clear before new request
        console.log("cleared batch")
        onBatchReady([]);    // clear in parent too
        console.log("clear in parent too")
        sendMessage({ text: input });
        console.log("message sent")
        setInput("");
    };

    return (
        <div>
            <VoiceInput setChatInput={setInput} handleSend={handleSend}/>
            <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type your message..."
            />
            <button onClick={handleSend}>Send</button>
        </div>
    );
}