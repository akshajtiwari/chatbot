from flask import Flask, request, render_template, jsonify
from threading import Thread, Event, Condition
import pipeline  # Our refactored pipeline logic
from pymongo import MongoClient
from bson.objectid import ObjectId
import os

app = Flask(__name__)

# --- Database Connection ---
client = MongoClient('mongodb://localhost:27017/')
db = client['campus_chatbot_db']
documents_collection = db['raw_documents']
config_collection = db['configurations']

# --- Global State for Running Searchers ---

running_searchers = {}

# --- A Wrapper for our Pipeline to Catch Errors ---
def searcher_wrapper(config, username, password, stop_event, condition, config_id):
    """
    A wrapper function that runs the pipeline and catches any exceptions,
    updating the global state with the error message.
    """
    try:
        pipeline.search_erp_portal(config, username, password, stop_event, condition)
        # If the loop finishes without error (i.e., was stopped manually)
        status_info = running_searchers.get(config_id)
        if status_info:
            status_info['status'] = 'stopped'
    except Exception as e:
        print(f"ERROR in searcher thread for '{config['erp_name']}': {e}")
        # Store the error message in our global state
        status_info = running_searchers.get(config_id)
        if status_info:
            status_info['status'] = 'error'
            status_info['error_message'] = str(e)

# --- Main & Config Routes ---
@app.route('/')
def admin_panel():
    configs = list(config_collection.find({}, {'_id': 1, 'erp_name': 1}))
    for config in configs:
        config['_id'] = str(config['_id'])
    return render_template('index.html', configs=configs)

@app.route('/save_config', methods=['POST'])
def save_config():
    data = request.json
    config_id = data.get('config_id')
    config_doc = {
        'erp_name': data['erp_name'], 'login_url': data['login_url'],
        'username_payload_key': data['username_payload_key'],
        'password_payload_key': data['password_payload_key'],
        'target_urls': data['target_urls'],
        'supported_file_types': data['supported_file_types'],
    }
    if config_id:
        config_collection.update_one({'_id': ObjectId(config_id)}, {"$set": config_doc})
        new_config_id = config_id
    else:
        result = config_collection.insert_one(config_doc)
        new_config_id = str(result.inserted_id)
    return jsonify({"message": "Configuration saved!", "config_id": new_config_id})

@app.route('/get_config/<config_id>')
def get_config(config_id):
    config = config_collection.find_one({'_id': ObjectId(config_id)})
    if config:
        config['_id'] = str(config['_id'])
        return jsonify(config)
    return jsonify({"error": "Config not found"}), 404

# --- Searcher Control Routes ---
@app.route('/start_searching', methods=['POST'])
def start_searching():
    data = request.json
    config_id = data.get('config_id')
    if not config_id: return jsonify({"error": "No configuration selected!"}), 400
    if config_id in running_searchers and running_searchers[config_id].get('status') == 'running':
        return jsonify({"error": "Searcher is already running for this config!"}), 400

    config = config_collection.find_one({'_id': ObjectId(config_id)})
    if not config: return jsonify({"error": "Configuration not found!"}), 404

    username = data.get('username')
    password = data.get('password')
    
    config['download_dir'] = 'downloads'

    stop_event = Event()
    condition = Condition()
    
    # We now call our new wrapper function in the thread
    searcher_thread = Thread(
        target=searcher_wrapper,
        args=(config, username, password, stop_event, condition, config_id)
    )
    searcher_thread.start()
    
    running_searchers[config_id] = {
        'thread': searcher_thread, 'stop_event': stop_event,
        'condition': condition, 'status': 'running', 'error_message': None
    }
    print(f"STARTED searcher for '{config['erp_name']}'.")
    return jsonify({"message": f"Searcher process started for {config['erp_name']}!"})

@app.route('/stop_searching', methods=['POST'])
def stop_searching():
    data = request.json
    config_id = data.get('config_id')
    searcher_info = running_searchers.get(config_id)
    if not searcher_info: return jsonify({"error": "Searcher not running."}), 400

    print(f"STOP signal sent to '{searcher_info.get('erp_name', config_id)}'")
    searcher_info['stop_event'].set()
    with searcher_info['condition']:
        searcher_info['condition'].notify_all()
    return jsonify({"message": "Searcher stop signal sent."})

@app.route('/trigger_search', methods=['POST'])
def trigger_search():
    data = request.json
    config_id = data.get("config_id")
    searcher_info=running_searchers.get(config_id)
    if not searcher_info: return jsonify({"error":"Searcher is not running"}),400

    print(f"MANUAL TRIGGER for searcher with config ID: {config_id}")
    with searcher_info['condition']:
        searcher_info['condition'].notify_all()
    return jsonify({"message":"Manual search triggered!"})

@app.route('/get_status')
def get_status():
    """Returns the status of all searchers."""
    status_report = {}
    # Clean up finished/errored threads
    for config_id, info in list(running_searchers.items()):
        if not info['thread'].is_alive():
            del running_searchers[config_id]
            continue
        status_report[config_id] = {
            "status": info.get('status', 'running'),
            "error_message": info.get('error_message')
        }
    return jsonify(status_report)

# --- Data Management Routes (Unchanged) ---
@app.route('/get_documents')
def get_documents():
    docs = list(documents_collection.find({}))
    for doc in docs: doc['_id'] = str(doc['_id'])
    return jsonify(docs)

@app.route('/delete_document/<doc_id>', methods=['POST'])
def delete_document(doc_id):
    try:
        doc = documents_collection.find_one({'_id': ObjectId(doc_id)})
        if doc and 'file_name' in doc:
            file_path = os.path.join('downloads', doc['file_name'])
            if os.path.exists(file_path): os.remove(file_path)
        documents_collection.delete_one({'_id': ObjectId(doc_id)})
        return jsonify({"message": "Document deleted."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    app.run(debug=True, port=5000)

