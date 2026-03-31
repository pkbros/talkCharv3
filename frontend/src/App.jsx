// src/App.jsx
import React, { useState } from "react";
import Chat from "./chat/Chat";
import Player from "./renderer/Player";
import Character from "../Character/Character";

export default function App() {
  const [batch, setBatch] = useState([]);
  const [viseme, setViseme] = useState("sil");

  return (
    <div style={{display: "flex", width: '100%', height: '100vh'}}>
      <div style={{ width: "30%"}}>
      <Chat onBatchReady={setBatch} />
      <Player batch={batch} viseme={viseme} setViseme={setViseme}/>
      </div>
      <div style={{backgroundColor: "#391b1b", width: "70%"}}>
        <Character viseme={viseme}/>
      </div>
    </div>
  );
}