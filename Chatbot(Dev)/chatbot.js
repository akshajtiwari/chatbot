let currentLanguage = 'en';
let messages = [];

const languages = {
    'en': { name: 'English', flag: '🇺🇸' },
};
const welcomeMessages = {
    'en': "👋 Hello! I'm your college assistant. What would you like to know?"
};
const quickSuggestions = [
    "Fee payment deadlines",
    "Admission process", 
    "Exam schedule",
    "Library timings"
];

function openChatbot() {
    document.getElementById('chatBubble').style.display = 'none';
    document.getElementById('chatbotWidget').classList.add('open');
    if (messages.length === 0) {
        showWelcomeMessage();
    }
}

function closeChatbot() {
    document.getElementById('chatbotWidget').classList.remove('open');
    document.getElementById('chatBubble').style.display = 'block';
}

function showWelcomeMessage() {
    messages = [];
    messages.push({
        id: Date.now(),
        text: welcomeMessages[currentLanguage],
        sender: 'bot',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });
    renderMessages();
    showQuickSuggestions();
}

function handleInput(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = (textarea.scrollHeight) + 'px';
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const messageText = input.value.trim();
    
    if (messageText) {
        messages.push({
            id: Date.now(),
            text: messageText,
            sender: 'user',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        });
        
        input.value = '';
        handleInput(input);
        renderMessages();
        removeQuickSuggestions();
        
        showTypingIndicator();
        
        setTimeout(() => {
            hideTypingIndicator();
            messages.push({
                id: Date.now() + 1,
                text: "Thank you for your question! I'm here to help you with all your college-related queries. Let me find the most accurate information for you.",
                sender: 'bot',
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            });
            renderMessages();
        }, 1500);
    }
}

function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function renderMessages() {
    const container = document.getElementById('messagesContainer');
    container.innerHTML = '';
    
    messages.forEach(message => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${message.sender}`;
        
        const avatar = `<div class="message-avatar ${message.sender}">
            ${message.sender === 'user' ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/></svg>' : ''}
        </div>`;
        
        const content = `<div class="message-content ${message.sender}">
            <div class="message-text">${message.text}</div>
            <div class="message-time">${message.timestamp}</div>
        </div>`;

        messageDiv.innerHTML = avatar + content;
        container.appendChild(messageDiv);
    });
    
    scrollToBottom();
}

function showQuickSuggestions() {
    const container = document.getElementById('messagesContainer');
    const suggestionsDiv = document.createElement('div');
    suggestionsDiv.className = 'quick-suggestions';
    suggestionsDiv.id = 'quickSuggestions';
    
    let buttonsHTML = quickSuggestions.map(suggestion => 
        `<button class="suggestion-btn" onclick="handleSuggestion('${suggestion}')">${suggestion}</button>`
    ).join('');
    
    suggestionsDiv.innerHTML = `<div class="suggestions-label">Quick questions:</div><div class="suggestions-grid">${buttonsHTML}</div>`;
    container.appendChild(suggestionsDiv);
    scrollToBottom();
}

function removeQuickSuggestions() {
    const suggestions = document.getElementById('quickSuggestions');
    if (suggestions) suggestions.remove();
}

function handleSuggestion(suggestion) {
    messages.push({
        id: Date.now(),
        text: suggestion,
        sender: 'user',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });
    renderMessages();
    removeQuickSuggestions();
    
    showTypingIndicator();
    setTimeout(() => {
        hideTypingIndicator();
        messages.push({
            id: Date.now() + 1,
            text: `Here's what you need to know about ${suggestion.toLowerCase()}. I'll provide you with the most up-to-date information from our college database.`,
            sender: 'bot',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        });
        renderMessages();
    }, 1200);
}

function showTypingIndicator() {
    const container = document.getElementById('messagesContainer');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-indicator';
    typingDiv.id = 'typingIndicator';
    typingDiv.innerHTML = `
        <div class="message-avatar bot"></div>
        <div class="typing-dots">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>`;
    container.appendChild(typingDiv);
    scrollToBottom();
}

function hideTypingIndicator() {
    const typing = document.getElementById('typingIndicator');
    if (typing) typing.remove();
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    container.scrollTop = container.scrollHeight;
}

document.addEventListener('DOMContentLoaded', function() {
    setTimeout(() => {
        const chatBubble = document.getElementById('chatBubble');
        if (chatBubble) chatBubble.style.display = 'block';
    }, 1000);

    document.addEventListener('mousedown', function(event) {
        const widget = document.getElementById('chatbotWidget');
        const bubble = document.getElementById('chatBubble');
        if (widget && bubble && widget.classList.contains('open')) {
            if (!widget.contains(event.target) && !bubble.contains(event.target)) {
                closeChatbot();
            }
        }
    });
});