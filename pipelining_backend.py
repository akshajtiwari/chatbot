from flask import Flask,request, render_template, jsonify
from threading import Thread
import pipeline
from pymongo import MongoClient
from bson.objectid import ObjectId
import os 


app=Flask(__name__)

# ___Database collection___
client = MongoClient('mongodb://localhost:27017/')
db = client['campus_chatbot_db']
documents_collection = db['raw_documents']
config_collection = db['configurations']

# ---- main routes ----

@app.route('/')
def admin_panel():
    """Renders the main admin panel, passing in all saved ERP configurations."""
    configs = list(config_collection.find({},{'_id':1,'erp_name':1}))
    for config in configs:
        config['_id'] = str(config['_id'])
    return render_template('index.html',configs=configs)

@app.route('/save_config',methods=['POST'])
def save_config():
    """Saves or updates the erp config"""
    data = request.json
    config_id = data.get('config_id')

    config_doc = {
        'erp_name':data['erp_name'],
        'login_url':data['login_url'],
        'username_payload_key':data['username_payload_key'],
        'password_payload_key':data['password_payload_key'],
        'target_urls':data['target_urls'],
        'supported_file_types':data['supported_file_types'],
        'download_dir':'downloads'
    }

    if config_id:
        config_collection.update_one({'_id':ObjectId(config_id)},{"$set":config_doc})
        return jsonify({"message":"Configuration updated successfully!",'config_id':config_id})
    else:
        result = config_collection.insert_one(config_doc)
        return jsonify({"message": "New configuration saved successfully!", "config_id": str(result.inserted_id)})
    
@app.route('/get_config/<config_id>')
def get_config(config_id):
    """Fetches the details for a single ERP configuration."""
    config = config_collection.find_one({'_id':ObjectId(config_id)})
    if config:
        config['_id'] = str(config['_id'])
        return jsonify(config)
    return jsonify({"error":"Configuration not found"}), 404

# @app.route('/')
# def admin_form():
#     """Renders the main admin configuration page."""
#     return render_template('index.html')

@app.route('/start_scraping',methods=['POST'])
def start_scraping():
    """Starts collecting process for a specific ERP configuration."""
    data = request.json
    config_id = data.get('config_id')

    if not config_id:
        return jsonify({"error":"No configuration selected !!"}), 400
    
    config = config_collection.find_one({'_id':ObjectId(config_id)})
    if not config:
        return jsonify({"error":"Configuration not found!"}), 404

    username = data.get('username')
    password = data.get('password')

    config['download_dir'] = 'downloads'

    print(f"Starting collecting process for '{config['erp_name']}' in a background thread...")
    scraper_thread = Thread(target=pipeline.scrape_erp_portal,args=(config,username,password))
    scraper_thread.start()

    return jsonify({"message":f"Collecting process started for {config['erp_name']}! Check terminal for process."})

@app.route('/get_documents')
def get_documents():
    """Fetch all documents from the raw_documents collection"""
    documents = list(documents_collection.find({}))

    #DEBUGGING: This will show us exactly what the database is returning
    print(f"DEBUG: Found {len(documents)} documents in the 'raw_documents' collection.")

    for doc in documents:
        doc['_id']=str(doc['_id'])
    return jsonify(documents)

@app.route('/delete_document/<doc_id>',methods=['POST'])
def delete_document(doc_id):
    """Deletes a document from the database and its associated file."""
    try:
        doc = documents_collection.find_one({'_id':ObjectId(doc_id)})

        if doc and 'file_name' in doc:
            # FIX: The download directory is static for now, so we refer to it directly.
            file_path = os.path.join('downloads',doc['file_name'])
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Delete local file: {file_path}")

        # Delete the database record
        documents_collection.delete_one({'_id':ObjectId(doc_id)})
        return jsonify({"message":"Document and associated file deleted."})
    except Exception as e:
        return jsonify({"error":str(e)}),500
if __name__ == "__main__":
    app.run(debug=True,port=5000)