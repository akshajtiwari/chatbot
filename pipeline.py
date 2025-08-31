##Codes here are handled by Himansh
import requests
import time 
import os
import hashlib
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pymongo import MongoClient

NOTICE_BOARD_URL="http://127.0.0.1:5501/test_circular.html"

DOWNLOAD_DIR='downloads'

POLL_INTERVAL = 60

client  = MongoClient('mongodb://localhost:27017/')
db = client['campus_chatbot_db']
collection = db['raw_documents']


#__________________Main Functions__________________

def calculate_checksum(file_path):
    """Calculates the SHA-256 hash of a file for deduplication."""
    sha256_hash=hashlib.sha256()
    with open(file_path, 'rb') as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def process_page():
    """Fetches the notice page, finds PDFs, and downloads new ones."""
    print(f"Checking for new notices at {NOTICE_BOARD_URL}...")

    headers={
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chorme/91.0.4472.124 Safari/537.36'
    }
    try:
        # 1- > fetch the webpage
        response = requests.get(NOTICE_BOARD_URL,headers=headers,timeout=15)
        # print("1 Works here")
        response.raise_for_status()

        # 2 -> parsing the HTML to find all links
        soup = BeautifulSoup(response.content,'html.parser')
        # print("2 soup This worked too")
        links=soup.find_all('a') # Finds all hyperlink tags <a>
        # print("3 did i find the links?",links)

        found_pdf_this_run=False
        for link in links:
            href = link.get('href')
            # print("4 did i find a valid href?", href)
            if href and '.pdf' in href.lower():
                found_pdf_this_run=True
                # Construst the full URL for the PDF
                # The handles cases where the link is relative (e.g., '/notice1.pdf')
                pdf_url= urljoin(NOTICE_BOARD_URL,href)
                
                existing_doc_by_url=collection.find_one({'source_url':pdf_url})
                if existing_doc_by_url:
                    print(f"URL already in database:{pdf_url}. Skipping...")
                    continue
                
                # Download the PDF
                print(f"Found a PDF: {pdf_url}, Downloading ...")
                try:
                    pdf_response=requests.get(pdf_url,headers=headers)
                    pdf_response.raise_for_status()
                    # Get the filename from the URL
                    file_name = os.path.basename(pdf_url)
                    file_path = os.path.join(DOWNLOAD_DIR,file_name)

                    # saving the pdf to the downloads folder
                    with open(file_path,'wb+') as f:
                        f.write(pdf_response.content)

                    # Calculate checksum and check for duplicates before saving to DB
                    checksum = calculate_checksum(file_path)

                    # Check if a document with this checksum already exists
                    existing_doc_by_checksum = collection.find_one({'checksum':checksum})

                    if existing_doc_by_checksum:
                        print(f"'{file_name}' already exists in the database. Skipping ...")
                        # Clean up the duplicate file we just downloaded
                        os.remove(file_path)
                    else:
                        print(f"New file found! Storing metadata for '{file_name}' in the database.")
                        document_metadata = {
                            'file_name':file_name,
                            'source_url':pdf_url,
                            'download_timestamp':time.time(),
                            'checksum':checksum,
                            'status':'staged' # This file is now in our staging area [cite: 8]
                        }
                        collection.insert_one(document_metadata)
                except requests.exceptions.RequestException as e:
                    print(f"-> Failed to download {pdf_url}. Reason - {e}")

                if not found_pdf_this_run:
                    print("Could not find any PDFs this run.")
    except requests.exceptions.RequestException as e:
        print(f"Error: Could not fetch the webpage. {e}")

#__________________Main Loop__________________

if __name__ == '__main__':
    # Create the downloads directory if it doesn't exist
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    while True:
        process_page()
        temp = POLL_INTERVAL
        # while temp:
        #     print(f"waitinf for {temp} seconds before the next check...")
        #     time.sleep(1)
        #     temp-=1
        print(f"Waiting for {POLL_INTERVAL} seconds before the next check...")
        time.sleep(POLL_INTERVAL)

