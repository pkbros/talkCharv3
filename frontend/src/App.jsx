// src/App.jsx
import React, { useState } from "react";
import Chat from "./chat/Chat";
import Player from "./renderer/Player";

export default function App() {
  const [batch, setBatch] = useState([]);

  return (
    <div style={{display: "flex", width: '100%', height: '100vh'}}>
      <div style={{ width: "30%"}}>
      <Chat onBatchReady={setBatch} />
      <Player batch={batch} />
      </div>
      <div style={{backgroundColor: "#391b1b", width: "70%"}}>
        Player Area
      </div>
    </div>
  );
}