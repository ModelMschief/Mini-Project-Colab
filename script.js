document.addEventListener('DOMContentLoaded', async () => {
    const chatHistory = document.getElementById('chat-history');
    const chatInput = document.getElementById('chat-input');
    const sendButton = document.getElementById('send-button');
    
    const baseUrl = 'http://127.0.0.1:5000'; 
    const TYPING_SPEED_MS = 3;

    // --- 1. Session & History Management ---

    async function getSessionId() {
        let sid = localStorage.getItem('chat_session_id');
        if (!sid) {
            const res = await fetch(`${baseUrl}/get-session`);
            const data = await res.json();
            sid = data.session_id;
            localStorage.setItem('chat_session_id', sid);
        }
        return sid;
    }

    async function loadHistory() {
        const sid = localStorage.getItem('chat_session_id');
        if (!sid) return;

        try {
            const response = await fetch(`${baseUrl}/get-history`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sid })
            });

            if (response.ok) {
                const data = await response.json();
                chatHistory.innerHTML = ''; // Clear welcome message
                data.history.forEach(msg => {
                    if (msg.role === 'user') appendUserMessage(msg.content);
                    else renderStaticLLMMessage(msg.content);
                });
            } else if (response.status === 401) {
                localStorage.removeItem('chat_session_id');
            }
        } catch (e) { console.error("History load failed", e); }
    }

    // --- 2. UI Helpers ---

    function appendUserMessage(message) {
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message', 'user-message');
        msgDiv.innerHTML = `You: ${message}`;
        chatHistory.appendChild(msgDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function createLLMMessageContainer() {
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message');
        const contentDiv = document.createElement('div');
        contentDiv.classList.add('gemini-message'); 
        contentDiv.innerHTML = 'Groq: <span class="response-text"></span>';
        msgDiv.appendChild(contentDiv);
        chatHistory.appendChild(msgDiv);
        return contentDiv.querySelector('.response-text');
    }

    function renderStaticLLMMessage(text) {
        const el = createLLMMessageContainer();
        el.textContent = text;
    }

    async function typeCharacters(element, text) {
        for (let i = 0; i < text.length; i++) {
            element.textContent += text.charAt(i);
            await new Promise(r => setTimeout(r, TYPING_SPEED_MS));
        }
    }

    // --- 3. Main Chat Logic ---

    async function handleChat() {
        const prompt = chatInput.value.trim();
        if (!prompt) return;

        const sessionId = await getSessionId();
        appendUserMessage(prompt);
        chatInput.value = '';
        chatInput.disabled = true;

        const responseTextElement = createLLMMessageContainer();
        
        try {
            const response = await fetch(`${baseUrl}/stream-chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: prompt, session_id: sessionId })
            });

            if (response.status === 401) {
                localStorage.removeItem('chat_session_id');
                responseTextElement.textContent = "Session expired. Please refresh the page.";
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                await typeCharacters(responseTextElement, chunk);
                chatHistory.scrollTop = chatHistory.scrollHeight;
            }
        } catch (error) {
            responseTextElement.textContent = "Error connecting to server.";
        } finally {
            chatInput.disabled = false;
            chatInput.focus();
        }
    }

    sendButton.addEventListener('click', handleChat);
    chatInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleChat(); });
    
    // Initialize history on load
    loadHistory();
});