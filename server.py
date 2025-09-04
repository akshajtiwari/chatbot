from flask import Flask, request, jsonify

app = Flask(__name__)

# Route to receive chat text input
@app.route('/chat/text', methods=['POST'])
def receive_text():
    data = request.json
    message = data.get('message')
    language = data.get('language')  # optional
    # Forward message to your extraction/NLP service here
    # e.g., nlp_service.handle_text(message, language)
    return jsonify({'status': 'received', 'type': 'text'})

# Route to receive chat audio input
@app.route('/chat/audio', methods=['POST'])
def receive_audio():
    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'No audio file received'}), 400
    # Forward audio to your extraction/NLP service here
    # e.g., nlp_service.handle_audio(audio_file)
    return jsonify({'status': 'received', 'type': 'audio'})

# Route to process parsed NLP output and return formatted chatbot text
@app.route('/process_nlp', methods=['POST'])
def process_nlp():
    data = request.get_json()  # Receive parsed NLP JSON from your pipeline
    intent = data.get('intent', 'No intent found')
    entities = data.get('entities', {})
    # Format into a simple chatbot text response
    response_text = f"Intent detected: {intent}. Entities found: {entities}."
    # Return as JSON with text for chatbot display
    return jsonify({"response_text": response_text})

if __name__ == '__main__':
    app.run(debug=True)
