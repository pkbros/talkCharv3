import { createContext, useContext, useState } from "react";

const ChatContext = createContext(null);

export const ChatProvider = ({ children }) => {
    const [currentBatch, setCurrentBatch] = useState([]);
    const [isReceiving, setIsReceiving] = useState(false);

    return (
        <ChatContext.Provider value={{ currentBatch, setCurrentBatch, isReceiving, setIsReceiving }}>
            {children}
        </ChatContext.Provider>
    );
};

export const useChatStore = () => {
    const context = useContext(ChatContext);
    if (!context) {
        throw new Error("useChatStore must be used inside a ChatProvider");
    }
    return context;
};