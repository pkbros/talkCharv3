// src/renderer/Player.jsx
import React, { useEffect, useState, useRef } from "react";
import { PHONEME_TO_VISEME } from "./viseme_map";

export default function Player({ batch, clearSignal }) {
    const [text, setText] = useState("");
    const [emotion, setEmotion] = useState("");
    const [pose, setPose] = useState("");
    const [phoneme, setPhoneme] = useState("");
    const [viseme, setViseme] = useState("");

    const queueRef = useRef([]);
    const isPlayingRef = useRef(false);
    const audioCtxRef = useRef(null);
    const playedCountRef = useRef(0);
    const timeoutIdsRef = useRef([]);

    // Initialize AudioContext once
    useEffect(() => {
        if (!audioCtxRef.current) {
            audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
        }
    }, []);

    // Handle clear signal
    useEffect(() => {
        if (!clearSignal) return;

        timeoutIdsRef.current.forEach((id) => clearTimeout(id));
        timeoutIdsRef.current = [];

        queueRef.current = [];
        playedCountRef.current = 0;
        isPlayingRef.current = false;
        setText("");
        setEmotion("");
        setPose("");
        setPhoneme("");
        setViseme("");
    }, [clearSignal]);

    // Single unified effect for batch updates
    useEffect(() => {
        if (!batch) return;

        if (batch.length === 0) {
            timeoutIdsRef.current.forEach((id) => clearTimeout(id));
            timeoutIdsRef.current = [];
            playedCountRef.current = 0;
            queueRef.current = [];
            isPlayingRef.current = false;
            return;
        }

        const newItems = batch.slice(playedCountRef.current);
        if (newItems.length > 0) {
            queueRef.current.push(...newItems);
            playedCountRef.current = batch.length;
        }

        if (!isPlayingRef.current) {
            playNext();
        }
    }, [batch]);

    const decodeAudioData = (audio_base64) => {
        // Step 1: base64 → raw bytes
        const binaryString = atob(audio_base64);
        const byteArray = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            byteArray[i] = binaryString.charCodeAt(i);
        }

        // Step 2: slice to get a fresh, properly aligned ArrayBuffer
        // This fixes the "damaged radio voice" caused by misaligned float reads
        const alignedBuffer = byteArray.buffer.slice(
            byteArray.byteOffset,
            byteArray.byteOffset + byteArray.byteLength
        );

        // Step 3: interpret aligned bytes as float32 PCM
        const floatArray = new Float32Array(alignedBuffer);

        // Step 4: sanity check — float32 PCM must be in [-1.0, 1.0]
        // If values are way out of range, backend is sending int16, not float32
        const sample = floatArray[0];
        if (Math.abs(sample) > 1.5) {
            console.warn(
                "PCM samples out of float32 range — backend may be sending int16. " +
                "First sample value:", sample,
                "Converting int16 → float32..."
            );
            const int16Array = new Int16Array(alignedBuffer);
            const converted = new Float32Array(int16Array.length);
            for (let i = 0; i < int16Array.length; i++) {
                converted[i] = int16Array[i] / 32768.0;
            }
            return converted;
        }

        return floatArray;
    };

    const playNext = () => {
        if (queueRef.current.length === 0) {
            isPlayingRef.current = false;
            return;
        }

        const item = queueRef.current.shift();
        if (!item) {
            playNext();
            return;
        }

        try {
            const audioCtx = audioCtxRef.current;

            // Decode base64 PCM → Float32Array (with alignment + int16 fallback)
            const floatArray = decodeAudioData(item.audio_base64);

            const sampleRate = item.sample_rate || 44100;
            const audioBuffer = audioCtx.createBuffer(1, floatArray.length, sampleRate);
            audioBuffer.copyToChannel(floatArray, 0);

            const source = audioCtx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioCtx.destination);

            // Capture audio start time as anchor for all timeouts
            const scheduledStartTime = audioCtx.currentTime;
            const msUntilStart = Math.max(0, (scheduledStartTime - audioCtx.currentTime) * 1000);

            // Metadata fires in sync with audio start
            const metaId = setTimeout(() => {
                setText(item.text || "");
                setEmotion(item.emotion || "");
                setPose(item.pose || "");
            }, msUntilStart);
            timeoutIdsRef.current.push(metaId);

            // Phonemes + visemes anchored to same audio start time
            if (Array.isArray(item.phonemes)) {
                item.phonemes.forEach((ph) => {
                    if (!ph || !ph.phoneme) return;

                    const startDelay = msUntilStart + ph.start * 1000;
                    const endDelay = msUntilStart + ph.end * 1000;

                    const startId = setTimeout(() => {
                        setPhoneme(ph.phoneme);
                        setViseme(PHONEME_TO_VISEME[ph.phoneme] || "");
                    }, startDelay);

                    const endId = setTimeout(() => {
                        setPhoneme("");
                        setViseme("");
                    }, endDelay);

                    timeoutIdsRef.current.push(startId, endId);
                });
            }

            source.start(scheduledStartTime);
            source.onended = () => { playNext(); };
            isPlayingRef.current = true;

        } catch (err) {
            console.error("Audio play error:", err);
            playNext();
        }
    };

    return (
        <div>
            <h2>Text: {text}</h2>
            <h3>Emotion: {emotion}</h3>
            <h3>Pose: {pose}</h3>
            <h4>Phoneme: {phoneme}</h4>
            <h4>Viseme: {viseme}</h4>
        </div>
    );
}