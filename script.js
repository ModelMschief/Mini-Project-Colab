document.addEventListener('DOMContentLoaded', async () => {
    const viewport = document.getElementById('chat-viewport');
    const inputField = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-trigger');
    const hero = document.getElementById('hero-section');
    const resetBtn = document.getElementById('reset-trigger');
    
    const API_BASE = 'http://127.0.0.1:5000';
    let isLocked = false;

    // --- Core Session Sync ---

    async function initializeSession() {
        let sid = localStorage.getItem('chat_session_id');
        if (!sid) {
            try {
                const res = await fetch(`${API_BASE}/get-session`);
                const data = await res.json();
                localStorage.setItem('chat_session_id', data.session_id);
                return data.session_id;
            } catch (err) {
                console.error("Critical: Session init failed", err);
                return null;
            }
        }
        return sid;
    }

    async function syncHistory() {
        const sid = localStorage.getItem('chat_session_id');
        if (!sid) return;

        try {
            const res = await fetch(`${API_BASE}/get-history`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sid })
            });

            if (res.ok) {
                const { history } = await res.json();
                if (history && history.length > 0) {
                    clearHero();
                    viewport.innerHTML = ''; 
                    history.forEach(m => renderBubble(m.role === 'user' ? 'user' : 'bot', m.content, true));
                    scrollSync();
                }
            } else if (res.status === 401) {
                localStorage.removeItem('chat_session_id');
            }
        } catch (e) { console.warn("History sync bypassed", e); }
    }

    // --- UI Operations ---

    function clearHero() {
        if (hero) hero.style.display = 'none';
    }

    function renderBubble(role, text, isStatic = false) {
        const group = document.createElement('div');
        group.classList.add('msg-group', role);
        
        const bubble = document.createElement('div');
        bubble.classList.add('bubble');
        bubble.textContent = isStatic ? text : '';
        
        group.appendChild(bubble);
        viewport.appendChild(group);
        scrollSync();
        return bubble;
    }

    function showTyping() {
        const group = document.createElement('div');
        group.classList.add('msg-group', 'bot');
        group.id = 'active-indicator';
        group.innerHTML = `
            <div class="bubble">
                <div class="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
            </div>`;
        viewport.appendChild(group);
        scrollSync();
    }

    function hideTyping() {
        const el = document.getElementById('active-indicator');
        if (el) el.remove();
    }

    function scrollSync() {
        viewport.scrollTop = viewport.scrollHeight;
    }

    // --- Execution ---

    async function performInquiry() {
        const prompt = inputField.value.trim();
        if (!prompt || isLocked) return;

        isLocked = true;
        clearHero();
        
        // Ensure session exists BEFORE appending UI to prevent ID mismatch
        const sid = await initializeSession();
        
        renderBubble('user', prompt, true);
        inputField.value = '';
        inputField.disabled = true;
        
        showTyping();

        try {
            const response = await fetch(`${API_BASE}/stream-chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: prompt, session_id: sid })
            });

            if (response.status === 401) {
                localStorage.removeItem('chat_session_id');
                hideTyping();
                renderBubble('bot', "Your session has expired. Please refresh to start a new inquiry.", true);
                return;
            }

            hideTyping();
            const bubble = renderBubble('bot', '');
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value, { stream: true });
                // Direct injection for high-performance feel
                bubble.textContent += chunk;
                scrollSync();
            }
        } catch (err) {
            hideTyping();
            renderBubble('bot', "A communication error occurred. Verify backend connectivity.", true);
        } finally {
            isLocked = false;
            inputField.disabled = false;
            inputField.focus();
        }
    }

    // --- Listeners ---
    sendBtn.addEventListener('click', performInquiry);
    inputField.addEventListener('keypress', (e) => { if (e.key === 'Enter') performInquiry(); });
    resetBtn.addEventListener('click', () => {
        localStorage.removeItem('chat_session_id');
        window.location.reload();
    });

    // Startup
    syncHistory();
});