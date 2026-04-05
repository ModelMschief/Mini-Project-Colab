document.addEventListener('DOMContentLoaded', () => {

    const faqButtons = document.querySelectorAll('.faq-btn');
    const chatLog = document.getElementById('chat-log');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');

    const faqResponses = {
        admissions: "To apply for admissions, visit our website and fill out the online form. Entrance exams are required.",
        fees: "Tuition fees vary by course. Scholarships are available.",
        courses: "We offer Computer Science, Mechanical, Electrical, Civil, and AI & Data Science.",
        contact: "Email us at info@holygrace.edu or call +1-123-456-7890."
    };

    // FAQ buttons
    faqButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.getAttribute('data-question');
            appendMessage(btn.textContent, "user");
            appendMessage(faqResponses[question], "bot");
        });
    });

    // Send button
    sendBtn.addEventListener('click', sendMessage);

    // Enter key support
    userInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        appendMessage(message, "user");

        const response = getBotResponse(message);

        setTimeout(() => {
            appendMessage(response, "bot");
        }, 400);

        userInput.value = '';
    }

    function getBotResponse(message) {
        const msg = message.toLowerCase();

        if (msg === "hi" || msg === "hello") {
            return "Hii 👋 Welcome to Holy Grace Academy!";
        }

        if (msg.includes('admission')) return faqResponses.admissions;
        if (msg.includes('fee')) return faqResponses.fees;
        if (msg.includes('course')) return faqResponses.courses;
        if (msg.includes('contact')) return faqResponses.contact;

        return "Ask me about admissions, fees, courses or contact 😊";
    }

    function appendMessage(text, sender) {
    const chatLog = document.getElementById("chat-log");

    const msgWrapper = document.createElement("div");
    msgWrapper.classList.add("chat-message");

    const bubble = document.createElement("div");
    bubble.classList.add("message");

    if (sender === "bot") {

        const avatar = document.createElement("img");
        avatar.src = "images/ai-man.jpeg";
        avatar.classList.add("avatar");

        bubble.classList.add("bot");
        bubble.textContent = text;

        msgWrapper.appendChild(avatar);
        msgWrapper.appendChild(bubble);

    } else {

        bubble.classList.add("user");
        bubble.textContent = text;
        msgWrapper.style.justifyContent = "flex-end";
        msgWrapper.appendChild(bubble);
    }

    chatLog.appendChild(msgWrapper);
    chatLog.scrollTop = chatLog.scrollHeight;
}

});

// Keep this OUTSIDE
