document.addEventListener('DOMContentLoaded', () => {
    const chatHistory = document.getElementById('chat-history');
    const chatInput = document.getElementById('chat-input');
    const sendButton = document.getElementById('send-button');
    
    // --- Configuration ---
    const baseUrl = 'http://127.0.0.1:5000'; 
    const streamEndpoint = `${baseUrl}/stream-chat`;
    
    // **NEW CONFIGURATION:** Typing speed in milliseconds per character
    const TYPING_SPEED_MS = 3; // Keep this low for Groq's speed
    
    // --- Helper Functions (Same as before) ---
    function appendUserMessage(message) {
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message', 'user-message');
        msgDiv.innerHTML = `You: ${message}`;
        chatHistory.appendChild(msgDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight; // Scroll to bottom
    }

    // Renamed from createGeminiMessageContainer for Groq/General Use
    function createLLMMessageContainer() {
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message');
        
        const contentDiv = document.createElement('div');
        contentDiv.classList.add('gemini-message'); // Keep the CSS class for styling
        contentDiv.innerHTML = 'Groq: <span id="response-text"></span>'; // Display "Groq"
        
        msgDiv.appendChild(contentDiv);
        chatHistory.appendChild(msgDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        
        return contentDiv.querySelector('#response-text');
    }
    
    function setControlsDisabled(disabled) {
        chatInput.disabled = disabled;
        sendButton.disabled = disabled;
    }

    // --- Character Typing Promise Function ---
    function typeCharacters(element, text) {
        return new Promise(resolve => {
            let i = 0;
            function typeNext() {
                if (i < text.length) {
                    element.textContent += text.charAt(i);
                    i++;
                    setTimeout(typeNext, TYPING_SPEED_MS);
                } else {
                    resolve(); // Resolve the promise when the text chunk is finished typing
                }
            }
            typeNext();
        });
    }

    // --- Main Streaming Logic (MODIFIED) ---
    async function handleChat() {
        const prompt = chatInput.value.trim();
        if (!prompt) return;

        appendUserMessage(prompt);
        setControlsDisabled(true);
        chatInput.value = '';

        const responseTextElement = createLLMMessageContainer();
        
        try {
            const response = await fetch(streamEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: prompt })
            });

            if (!response.ok) {
                // If the HTTP status code is an error (e.g., 500)
                const errorText = await response.text();
                responseTextElement.textContent = `HTTP Error ${response.status}: ${errorText.substring(0, 100)}`;
                return;
            }
            
            if (!response.body) {
                responseTextElement.textContent = "Error: Stream not available.";
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');

            while (true) {
                const { value, done } = await reader.read();
                
                if (done) {
                    break; 
                }

                const chunk = decoder.decode(value, { stream: true });
                
                // Wait for the chunk to finish typing
                await typeCharacters(responseTextElement, chunk);
                
                chatHistory.scrollTop = chatHistory.scrollHeight; // Keep scrolling to the bottom
            }

        } catch (error) {
            console.error('Streaming error:', error);
            responseTextElement.textContent = `Error connecting to server or processing stream: ${error.message}`;
        } finally {
            setControlsDisabled(false);
            chatInput.focus();
        }
    }

    // --- Event Listeners (Same as before) ---
    sendButton.addEventListener('click', handleChat);
    
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            handleChat();
        }
    });
});