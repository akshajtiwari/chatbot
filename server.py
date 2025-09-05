from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# allow only chat endpoints from any origin (you can tighten for production)
CORS(app, resources={r"/chat/*": {"origins": "*"}})

@app.after_request
def add_cors_headers(response):
    # Ensure the headers exist even on OPTIONS
    response.headers.setdefault('Access-Control-Allow-Origin', '*')
    response.headers.setdefault('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.setdefault('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

@app.route('/chat/text', methods=['POST', 'OPTIONS'])
def receive_text():
    if request.method == 'OPTIONS':
        # quick answer for preflight
        return jsonify({'status': 'ok'}), 200

    data = request.json or {}
    message = data.get('message', '')
    language = data.get('language', 'en')

    response_text = f"You said in {language}: {message}"
    return jsonify({'status': 'success', 'response_text': response_text})

if __name__ == '__main__':
    # explicitly bind to 127.0.0.1 so it's reachable at http://127.0.0.1:5000
    app.run(host='127.0.0.1', port=5000, debug=True)
