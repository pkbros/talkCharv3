// src/renderer/Player.jsx
import React, { useEffect, useState, useRef } from "react";
import { PHONEME_TO_VISEME } from "./viseme_map";

export default function Player({ batch, clearSignal, viseme, setViseme, emotion, setEmotion, pose, setPose}) {
    const [text, setText] = useState("");

    
    const [phoneme, setPhoneme] = useState("");

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

    // Pre-warm AudioContext on any user interaction so it's ready before first audio
    useEffect(() => {
        const warmUp = () => {
            audioCtxRef.current?.resume();
        };
        window.addEventListener("click", warmUp, { once: true });
        window.addEventListener("keydown", warmUp, { once: true });
        return () => {
            window.removeEventListener("click", warmUp);
            window.removeEventListener("keydown", warmUp);
        };
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
        const binaryString = atob(audio_base64);
        const byteArray = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            byteArray[i] = binaryString.charCodeAt(i);
        }

        const alignedBuffer = byteArray.buffer.slice(
            byteArray.byteOffset,
            byteArray.byteOffset + byteArray.byteLength
        );

        const floatArray = new Float32Array(alignedBuffer);

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

    const playNext = async () => {
        if (queueRef.current.length === 0) {
            isPlayingRef.current = false;
            setPose("default");
            setEmotion("neutral")
            return;
        }

        const item = queueRef.current.shift();
        if (!item) {
            playNext();
            return;
        }

        try {
            const audioCtx = audioCtxRef.current;

            // Wake up AudioContext and wait until it's actually running
            // This is the key fix — on first call the context may be suspended
            await audioCtx.resume();

            const floatArray = decodeAudioData(item.audio_base64);

            const sampleRate = item.sample_rate || 44100;
            const audioBuffer = audioCtx.createBuffer(1, floatArray.length, sampleRate);
            audioBuffer.copyToChannel(floatArray, 0);

            const source = audioCtx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioCtx.destination);

            // Schedule audio 50ms into the future so timeouts can align perfectly.
            // This small lookahead eliminates the wake-up stutter on first play.
            const LOOKAHEAD_MS = 50;
            const startAt = audioCtx.currentTime + LOOKAHEAD_MS / 1000;

            // Metadata fires exactly when audio starts
            const metaId = setTimeout(() => {
                setText(item.text || "");
                setEmotion(item.emotion || "");
                setPose(item.pose || "");
            }, LOOKAHEAD_MS);
            timeoutIdsRef.current.push(metaId);

            // Phonemes + visemes anchored to the same start point
            if (Array.isArray(item.phonemes)) {
                item.phonemes.forEach((ph) => {
                    if (!ph || !ph.phoneme) return;

                    const startDelay = LOOKAHEAD_MS + ph.start * 1000;
                    const endDelay   = LOOKAHEAD_MS + ph.end   * 1000;

                    const startId = setTimeout(() => {
                        setPhoneme(ph.phoneme);
                        setViseme(PHONEME_TO_VISEME[ph.phoneme] || "");
                    }, startDelay);

                    const endId = setTimeout(() => {
                        setPhoneme("");
                        setViseme("sil");
                    }, endDelay);

                    timeoutIdsRef.current.push(startId, endId);
                });
            }

            source.start(startAt);
            source.onended = () => { playNext(); };
            isPlayingRef.current = true;

        } catch (err) {
            console.error("Audio play error:", err);
            playNext();
        }
    };

    return (
        <div style={{display:"flex", flexDirection:"column", justifyContent:"center", alignItems:"center"}}>
            <h2>Text: {text}</h2>
            <h3>Emotion: {emotion}</h3>
            <h3>Pose: {pose}</h3>
            <h4>Phoneme: {phoneme}</h4>
            <h4>Viseme: {viseme}</h4>
        </div>
    );
}