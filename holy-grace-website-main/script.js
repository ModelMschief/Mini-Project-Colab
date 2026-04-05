document.addEventListener('DOMContentLoaded', () => {
    let sessionId = localStorage.getItem('gracebot_session_id');
    let userName = localStorage.getItem('gracebot_user_name');

    const chatLog = document.getElementById('chat-log');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const faqButtons = document.querySelectorAll('.faq-btn');
     
    userInput.addEventListener('input', () => {
    sendBtn.disabled = userInput.value.trim() === "";
});

    async function initializeChat() {
        if (!sessionId) {
            try {
                const response = await fetch('http://127.0.0.1:5000/get-session');
                const data = await response.json();
                sessionId = data.session_id;
                localStorage.setItem('gracebot_session_id', sessionId);
            } catch (err) {
                console.error("Connection error");
                return;
            }
        }

        // If we don't know their name yet, start the "onboarding"
        if (!userName) {
            appendMessage("Hi! I'm GraceBot. Before we start, what is your name?", "bot", false);
        } else {
            await loadChatHistory(sessionId);
        }
    }

    async function loadChatHistory(sid) {
        try {
            const response = await fetch('http://127.0.0.1:5000/get-history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sid })
            });
            const data = await response.json();
            if (data.history && data.history.length > 0) {
                chatLog.innerHTML = ''; 
                data.history.forEach(msg => {
                    appendMessage(msg.content, msg.role === 'user' ? 'user' : 'bot', false);
                });
            }
        } catch (e) { console.log("New session started."); }
    }

    // --- LOGIC TO SAVE USER INFO ---
    async function saveUserInfo(name, contact) {
        try {
            await fetch('http://127.0.0.1:5000/get_userinfo', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    name: name,
                    contact: contact
                })
            });
            localStorage.setItem('gracebot_user_name', name);
            userName = name;
            appendMessage(`Nice to meet you, ${name}! How can I help you today?`, "bot", false);
        } catch (err) { console.error("Error saving user info"); }
    }

    async function handleMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        // ONBOARDING FLOW: If we don't have a name, the first message is their name
        if (!userName) {
            userInput.value = '';
            appendMessage(text, "user");
            // For simplicity, we assume the first thing they type is their name
            // and we'll use a generic placeholder for contact for now
            await saveUserInfo(text, "Not Provided");
            return;
        }

        // REGULAR FLOW: Chat with AI
        sendMessage(text);
    }

    async function sendMessage(message) {
        appendMessage(message, "user");
        userInput.value = '';
        const botMsgContainer = createBotLoadingBubble();

        try {
            const response = await fetch('http://127.0.0.1:5000/stream-chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: message, session_id: sessionId })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let botText = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                botText += decoder.decode(value, { stream: true });
                botMsgContainer.innerHTML = marked.parse(botText);
                chatLog.scrollTop = chatLog.scrollHeight;
            }
            addRatingSection();
        } catch (error) {
            botMsgContainer.textContent = "⚠️ Backend error.";
        }
    }

    // --- UI HELPERS ---
    function appendMessage(text, sender, showRating = true) {
        const msgWrapper = document.createElement("div");
        msgWrapper.classList.add("chat-message");
        if (sender === "user") msgWrapper.style.justifyContent = "flex-end";

        const bubble = document.createElement("div");
        bubble.classList.add("message", sender);
        bubble.innerHTML = marked.parse(text);

        if (sender === "bot") {
            const avatar = document.createElement("img");
            avatar.src = "images/ai-man.jpeg";
            avatar.classList.add("avatar");
            msgWrapper.appendChild(avatar);
        }

        msgWrapper.appendChild(bubble);

// ✅ COPY BUTTON (only for bot)
   if (sender === "bot") {
    const actions = document.createElement("div");
    actions.classList.add("message-actions");

    const copyBtn = document.createElement("button");
    copyBtn.textContent = "⧉";
    copyBtn.classList.add("copy-btn");

    // ✅ COPY FUNCTION
    copyBtn.onclick = () => {
        const messageText = bubble.innerText; // gets AI message only
        navigator.clipboard.writeText(messageText);

        copyBtn.textContent = "✅ Copied!";
        setTimeout(() => {
            copyBtn.textContent = "⧉";
        }, 1500);
    };

    actions.appendChild(copyBtn);
    msgWrapper.appendChild(actions);
}
        chatLog.appendChild(msgWrapper);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    function createBotLoadingBubble() {
    const msgWrapper = document.createElement("div");
    msgWrapper.classList.add("chat-message");

    const avatar = document.createElement("img");
    avatar.src = "images/ai-man.jpeg";
    avatar.classList.add("avatar");

    const bubble = document.createElement("div");
    bubble.classList.add("message", "bot");

    // ✅ content (this will update while streaming)
    const content = document.createElement("div");
    content.classList.add("message-content");
    content.textContent = "...";

    // ✅ time (this will stay fixed)
    const time = document.createElement("div");
    time.classList.add("message-time");

    const now = new Date();
    time.textContent = now.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit'
    });

    // add inside bubble
    bubble.appendChild(content);
    bubble.appendChild(time);

    msgWrapper.appendChild(avatar);
    msgWrapper.appendChild(bubble);

    chatLog.appendChild(msgWrapper);

    return content; // ⚠️ VERY IMPORTANT
}

    function addRatingSection() {
        const ratingWrapper = document.createElement("div");
        ratingWrapper.classList.add("rating-wrapper");
        ratingWrapper.innerHTML = `<span>Helpful? </span><span class="rating-btn">👍</span><span class="rating-btn">👎</span>`;
        chatLog.appendChild(ratingWrapper);
    }

    // --- LISTENERS ---
    sendBtn.addEventListener('click', handleMessage);
    userInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleMessage(); });
    faqButtons.forEach(btn => btn.addEventListener('click', () => {
        if (!userName) alert("Please enter your name first!");
        else sendMessage(btn.textContent.trim());
    }));

    initializeChat();
});