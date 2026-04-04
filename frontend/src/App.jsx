// src/App.jsx
import React, { useState } from "react";
import Chat from "./chat/Chat";
import Character from "./Character/Character";
import Player from "./renderer/Player";

export default function App() {
  const [batch, setBatch] = useState([]);
  const [viseme, setViseme] = useState("sil");
  const [emotion, setEmotion] = useState("neutral");
  const [pose, setPose] = useState("default");

  return (
    <div style={{display: "flex", width: '100%', height: '100vh'}}>
      <div style={{ width: "30%"}}>
      <Chat onBatchReady={setBatch} />
      <Player batch={batch} viseme={viseme} setViseme={setViseme} emotion={emotion} setEmotion={setEmotion} pose={pose} setPose={setPose}/>
      </div>
      <div style={{backgroundColor: "#bf9595", width: "70%",height: "100vh"}}>
        <Character  viseme={viseme} pose={pose} emotion={emotion}/>
      </div>
    </div>
  );
}