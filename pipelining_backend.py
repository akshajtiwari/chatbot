from flask import Flask,request, render_template, jsonify
from threading import Thread
import pipeline

app=Flask(__name__)

@app.route('/')
def admin_form():
    """Renders the main admin configuration page."""
    return render_template('index.html')

@app.route('/start_scraping',methods=['POST'])
def start_scraping():
    """Receives form data and starts the scraper in a background thread."""

    config = {
        'login_url': request.form.get('login_url'),
        'target_urls':[url for url in request.form.get('target_urls').splitlines() if url.strip()],
        'supported_file_types':[ftype for ftype in request.form.get('supported_file_types').splitlines() if ftype.strip()],
        'username_payload_key': request.form.get('username_payload_key'),
        'password_payload_key': request.form.get('password_payload_key'),
        'download_dir':'downloads'
    }

    username = request.form.get('username')
    password = request.form.get('password')

    print("Starting searching process in a background thread...")
    scraper_thread = Thread(target=pipeline.scrape_erp_portal,args=(config,username,password))
    scraper_thread.start()
    
    return jsonify({"message":"Searching processed started! Check the terminal for the process"})

if __name__ == "__main__":
    print("starting Flask server...")
    print("Open your broswer/Live server with port 5000")
    app.run(debug=True,port=5000)