##Codes here are handled by Himansh
import requests
import time 
import os
import hashlib
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pymongo import MongoClient
import getpass
import re

# --- LoginError -----

class LoginError(Exception):
    pass

# --- Database connection ---
client  = MongoClient('mongodb://localhost:27017/')
db = client['campus_chatbot_db']
document_collection = db['raw_documents']
config_collection = db['configurations']


#__________________Helper Functions__________________

def sanitize_filename(filename):
    """
    Removes characters that are illegal in Windows and other file systems.
    """
    return re.sub(r'[<>:"/\\|?*]','_',filename)


def calculate_checksum(data):
    """Calculates the SHA-256 hash of a file for deduplication."""
    sha256_hash=hashlib.sha256()
    if isinstance(data,str) and os.path.exists(data):
        with open(data, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
    elif isinstance(data,bytes):
        sha256_hash.update(data)
    else:
        return None
    return sha256_hash.hexdigest()

## _____ Main Logic_____

def search_erp_portal(config, username, password, stop_event,condition, poll_interval=300):
    """Continously searches an ERP portal in a loop until the stop_event is set."""
    print(f"[{config['erp_name']}] Searcher starting continous polling every {poll_interval} seconds.")
    
    download_dir = config.get('download_dir','downloads')
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    with requests.Session() as session:
        session.headers.update({
            'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        login_payload = {
            config['username_payload_key']: username,
            config['password_payload_key']:password
        }

        print(f"[{config['erp_name']}] Attempting to log in...")
        login_res = session.post(config['login_url'],data=login_payload,timeout=20)
        login_res.raise_for_status()

        soup = BeautifulSoup(login_res.text,'html.parser')
        username_field = soup.find('input',{'name':config['username_payload_key']})

        if username_field:
            raise LoginError("Login Failed. Please check credentials.")

        print(f"[{config['erp_name']}] Login successful. Starting search...")

        while not stop_event.is_set():
            print(f"[{config['erp_name']}] --- Starting new search cycle ---")
            for target_url in config.get('target_urls',[]):
                if stop_event.is_set(): break
                if not target_url: continue

                print(f"[{config['erp_name']}] --- Reading Page: {target_url}")
                page_res = session.get(target_url,timeout=20)
                page_res.raise_for_status()
                
                content_bytes = page_res.content
                html_checksum = calculate_checksum(content_bytes)
                if html_checksum and not document_collection.find_one({'checksum':html_checksum}):
                    print(f"[{config['erp_name']}] -> New HTML content detected. Archiving ...")
                    document_collection.insert_one({
                        'source_url':target_url, 'download_timestamp': time.time(),
                        'checksum':html_checksum, 'status':'staged',
                        'file_type':'html_content','erp_name':config['erp_name'],
                        'raw_html': content_bytes.decode('utf-8',errors='ignore')
                    })
                
                soup_files = BeautifulSoup(content_bytes,'html.parser')
                for link in soup_files.find_all('a'):
                    href = link.get('href')
                    if not href: continue
                    for ftype in config.get('supported_file_types',[]):
                        if href.lower().endswith(ftype):
                            resource_url = urljoin(target_url,href)
                            if not document_collection.find_one({'source_url':resource_url}):
                                resource_res = session.get(resource_url,timeout=30)
                                original_filename = os.path.basename(resource_url)
                                safe_filename = sanitize_filename(original_filename)
                                file_path = os.path.join(download_dir,safe_filename)
                                with open(file_path,'wb') as f: f.write(resource_res.content)
                                file_checksum = calculate_checksum(file_path)
                                if file_checksum and document_collection.find_one({'checksum':file_checksum}):
                                    os.remove(file_path)
                                else:
                                    document_collection.insert_one({
                                        'file_name':safe_filename,'source_url':resource_url,
                                        'download_timestamp':time.time(),'checksum':file_checksum,
                                        'status':'staged','file_type':ftype,'erp_name':config['erp_name']
                                    })
                            break

            if not stop_event.is_set():
                print(f"[{config['erp_name']}] Search cycle complete. Waiting for {poll_interval} seconds...")
                with condition:
                    condition.wait(poll_interval)

    print(f'[{config["erp_name"]}] Searcher has been stopped.')

