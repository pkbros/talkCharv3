
//setting same socket for each componet
let ws = null;


export const createWebSocket = (onMessage, onOpen, onClose) => {
    if (!ws || ws.readyState === WebSocket.CLOSED) { // only create a new socket if its not already existing
        ws = new WebSocket("ws://localhost:8000/ws");

        ws.onopen = () => {
            console.log("Connected to WebSocket ✅");
            if (onOpen) onOpen();
        };

        ws.onclose = () => {
            console.log("Disconnected ❌");
            if (onClose) onClose();
        };

        ws.onmessage = (event) => {
            console.log("Message from serer: ", event.data);
            if (onMessage) onMessage(event.data);
        };
    }


    return ws;
}

export function sendMessage(jsonObj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(jsonObj));
    } else {
        console.warn("WebSocket not ready");
    }
}

export function reciever(callback) {
    if (ws) {
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                callback(data); // pass raw JSON to frontend
            } catch (err) {
                console.error("error occured when parsing json at frontend: ", err, event.data);
            }
        };
    }
}
