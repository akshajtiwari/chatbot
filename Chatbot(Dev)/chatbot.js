
        let isRecording = false;
        let currentLanguage = 'en';
        let messages = [];

        const languages = {
            'en': { name: 'English', flag: '🇺🇸' },
            'hi': { name: 'हिंदी', flag: '🇮🇳' },
            'bn': { name: 'বাংলা', flag: '🇧🇩' },
            'te': { name: 'తెలుగు', flag: '🇮🇳' },
            'ta': { name: 'தமিழ்', flag: '🇮🇳' }
        };

        const welcomeMessages = {
            'en': "👋 Hello! I'm your college assistant. I can help you with admissions, fee payments, course information, exam schedules, library services, and campus facilities. What would you like to know?",
            'hi': "👋 नमस्ते! मैं आपका कॉलेज सहायक हूं। मैं प्रवेश, फीस भुगतान, कोर्स की जानकारी, परीक्षा कार्यक्रम, पुस्तकालय सेवाओं और कैंपस सुविधाओं में मदद कर सकता हूं। आप क्या जानना चाहते हैं?",
            'bn': "👋 হ্যালো! আমি আপনার কলেজ সহায়ক। আমি ভর্তি, ফি পেমেন্ট, কোর্সের তথ্য, পরীক্ষার সময়সূচী, লাইব্রেরি সেবা এবং ক্যাম্পাস সুবিধায় সাহায্য করতে পারি। আপনি কী জানতে চান?",
            'te': "👋 హలో! నేను మీ కాలేజీ సహాయకుడిని. అడ্మిషన్లు, ఫీజు చెల్లింపులు, కోర్స్ సమాచారం, పరీక్ష షెడ్యూల్స్, లైబ్రరీ సేవలు మరియు క్యాంపస్ సౌకర్యాలలో సహాయం చేయగలను. మీరు ఏమి తెలుసుకోవాలనుకుంటున్నారు?",
            'ta': "👋 வணக்கம்! நான் உங்கள் கல்லூரி உதவியாளர். சேர்க்கை, கட்டணம், பாடநெறி தகவல், தேர்வு அட்டவணை, நூலக சேவைகள் மற்றும் வளாக வசதிகளில் உதவ முடியும். நீங்கள் என்ன தெரிந்து கொள்ள விரும்புகிறீர்கள்?"
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

        
        document.addEventListener('mousedown', function(event) {
            const widget = document.getElementById('chatbotWidget');
            const bubble = document.getElementById('chatBubble');
            if (widget.classList.contains('open')) {
                if (!widget.contains(event.target) && !bubble.contains(event.target)) {
                    closeChatbot();
                }
            }
        });

        function showWelcomeMessage() {
            messages = [];
            const welcomeMsg = {
                id: Date.now(),
                text: welcomeMessages[currentLanguage],
                sender: 'bot',
                timestamp: new Date().toLocaleTimeString()
            };
            messages.push(welcomeMsg);
            renderMessages();
            showQuickSuggestions();
        }

        function changeLanguage() {
            currentLanguage = document.getElementById('languageSelect').value;
            document.getElementById('footerText').textContent = `Powered by AI • ${languages[currentLanguage].name}`;
            showWelcomeMessage();
        }

        function handleInputChange() {
            const input = document.getElementById('messageInput');
            const actionBtn = document.getElementById('actionBtn');
            
            if (input.value.trim()) {
                
                actionBtn.className = 'input-action-btn send-btn';
                actionBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22,2 15,22 11,13 2,9 22,2"></polygon></svg>';
                actionBtn.onclick = sendMessage;
            } else {
                
                actionBtn.className = 'input-action-btn mic-btn';
                actionBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>';
                actionBtn.onclick = toggleRecording;
            }
        }

        function toggleAction() {
            const input = document.getElementById('messageInput');
            if (input.value.trim()) {
                sendMessage();
            } else {
                toggleRecording();
            }
        }

        function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    if (!message) return;

    const userMessage = {
        id: Date.now(),
        text: message,
        sender: 'user',
        timestamp: new Date().toLocaleTimeString()
    };
    messages.push(userMessage);
    input.value = '';
    handleInputChange();
    renderMessages();
    removeQuickSuggestions();

    showTypingIndicator();

    // Use 127.0.0.1:5000 (same machine) — helps with some local CORS/hosts issues
    fetch('http://127.0.0.1:5000/chat/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: message,
            language: currentLanguage
        })
    })
    .then(async res => {
        if (!res.ok) {
            const txt = await res.text().catch(()=> 'No body');
            throw new Error(`HTTP ${res.status}: ${txt}`);
        }
        return res.json();
    })
    .then(data => {
        hideTypingIndicator();
        const botResponse = {
            id: Date.now() + 1,
            text: data.response_text || "⚠️ No response from backend",
            sender: 'bot',
            timestamp: new Date().toLocaleTimeString()
        };
        messages.push(botResponse);
        renderMessages();
    })
    .catch(err => {
        console.error("Error connecting to backend:", err);
        hideTypingIndicator();
        const botResponse = {
            id: Date.now() + 1,
            text: "❌ Error connecting to server.",
            sender: 'bot',
            timestamp: new Date().toLocaleTimeString()
        };
        messages.push(botResponse);
        renderMessages();
    });
}


        let recordingStartTime = 0;
        let recordingTimer = null;

        function updateRecordingTime() {
            const now = Date.now();
            const diff = Math.floor((now - recordingStartTime) / 1000);
            const minutes = Math.floor(diff / 60);
            const seconds = diff % 60;
            const timeStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;
            document.querySelector('.recording-time').textContent = timeStr;
        }

        function toggleRecording() {
            isRecording = !isRecording;
            const actionBtn = document.getElementById('actionBtn');
            const recordingIndicator = document.getElementById('recordingIndicator');
            const inputArea = document.querySelector('.input-container');
            const footerInfo = document.getElementById('footerInfo');
            
            if (isRecording) {
                
                inputArea.style.opacity = '0';
                footerInfo.style.opacity = '0';
                setTimeout(() => {
                    inputArea.style.display = 'none';
                    footerInfo.style.display = 'none';
                }, 300);

                
                actionBtn.classList.add('recording');
                recordingIndicator.classList.remove('hidden');
                removeQuickSuggestions();

                
                recordingStartTime = Date.now();
                recordingTimer = setInterval(updateRecordingTime, 1000);
            } else {
                stopRecording();
            }
        }

        function stopRecording(cancelled = false) {
            const actionBtn = document.getElementById('actionBtn');
            const recordingIndicator = document.getElementById('recordingIndicator');
            const inputArea = document.querySelector('.input-container');
            const footerInfo = document.getElementById('footerInfo');

            
            inputArea.style.display = 'flex';
            footerInfo.style.display = 'block';
            setTimeout(() => {
                inputArea.style.opacity = '1';
                footerInfo.style.opacity = '1';
            }, 50);

            
            actionBtn.classList.remove('recording');
            actionBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>';
            recordingIndicator.classList.add('hidden');

            
            if (recordingTimer) {
                clearInterval(recordingTimer);
                recordingTimer = null;
            }

            isRecording = false;
        }

        function sendVoiceMessage() {
            stopRecording();
            
            
            const voiceMessage = {
                id: Date.now(),
                text: "🎤 Voice message sent",
                sender: 'user',
                timestamp: new Date().toLocaleTimeString()
            };
            
            messages.push(voiceMessage);
            renderMessages();
            
            
            showTypingIndicator();
            setTimeout(() => {
                hideTypingIndicator();
                const botResponse = {
                    id: Date.now() + 1,
                    text: "I've received your voice message. Let me process that and respond accordingly.",
                    sender: 'bot',
                    timestamp: new Date().toLocaleTimeString()
                };
                messages.push(botResponse);
                renderMessages();
            }, 1500);
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
                messageDiv.className = 'message ' + message.sender;
                
                let avatarContent = '';
                if (message.sender === 'bot') {
                    avatarContent = ''; // Empty because we're using background-image
                } else {
                    avatarContent = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/></svg>';
                }
                
                messageDiv.innerHTML = 
                    '<div class="message-avatar ' + message.sender + '">' +
                        avatarContent +
                    '</div>' +
                    '<div class="message-content ' + message.sender + '">' +
                        '<div class="message-text">' + message.text + '</div>' +
                        '<div class="message-time">' + message.timestamp + '</div>' +
                    '</div>';
                
                container.appendChild(messageDiv);
            });
            
            scrollToBottom();
        }

        function showQuickSuggestions() {
            const container = document.getElementById('messagesContainer');
            const suggestionsDiv = document.createElement('div');
            suggestionsDiv.className = 'quick-suggestions';
            suggestionsDiv.id = 'quickSuggestions';
            
            let suggestionsHTML = '<div class="suggestions-label">Quick questions:</div><div class="suggestions-grid">';
            quickSuggestions.forEach(suggestion => {
                suggestionsHTML += '<button class="suggestion-btn" onclick="handleSuggestion(\'' + suggestion + '\')">' + suggestion + '</button>';
            });
            suggestionsHTML += '</div>';
            
            suggestionsDiv.innerHTML = suggestionsHTML;
            container.appendChild(suggestionsDiv);
            scrollToBottom();
        }

        function removeQuickSuggestions() {
            const suggestions = document.getElementById('quickSuggestions');
            if (suggestions) {
                suggestions.remove();
            }
        }

        function handleSuggestion(suggestion) {
            const userMessage = {
                id: Date.now(),
                text: suggestion,
                sender: 'user',
                timestamp: new Date().toLocaleTimeString()
            };
            messages.push(userMessage);
            renderMessages();
            removeQuickSuggestions();
            
            
            showTypingIndicator();
            setTimeout(() => {
                hideTypingIndicator();
                const botResponse = {
                    id: Date.now() + 1,
                    text: `Here's what you need to know about ${suggestion.toLowerCase()}. I'll provide you with the most up-to-date information from our college database.`,
                    sender: 'bot',
                    timestamp: new Date().toLocaleTimeString()
                };
                messages.push(botResponse);
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
                </div>
            `;
            
            container.appendChild(typingDiv);
            scrollToBottom();
        }

        function hideTypingIndicator() {
            const typing = document.getElementById('typingIndicator');
            if (typing) {
                typing.remove();
            }
        }

        function scrollToBottom() {
            const container = document.getElementById('messagesContainer');
            container.scrollTop = container.scrollHeight;
        }

        function updateFooter() {
    const footerEl = document.getElementById('footerText');
    if (!footerEl) return; // guard — do nothing if element not present
    footerEl.textContent = 'Powered by AI • ' + (languages[currentLanguage]?.name || 'Unknown');
}

// Ensure DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    updateFooter();
    setTimeout(function() {
        const chatBubble = document.getElementById('chatBubble');
        if (chatBubble) chatBubble.style.display = 'block';
    }, 1000);
});

   