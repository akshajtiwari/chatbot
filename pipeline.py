##Codes here are handled by Himansh
import requests
import time 
import os
import hashlib
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pymongo import MongoClient
import getpass


# NOTICE_BOARD_URL="http://127.0.0.1:5501/test_circular.html"

# DOWNLOAD_DIR='downloads'

# POLL_INTERVAL = 60

## --- Database setup ---

client  = MongoClient('mongodb://localhost:27017/')
db = client['campus_chatbot_db']
document_collection = db['raw_documents']
config_collection = db['configurations']


#__________________Helper Functions__________________

def calculate_checksum(file_path):
    """Calculates the SHA-256 hash of a file for deduplication."""
    sha256_hash=hashlib.sha256()
    if isinstance(file_path,str) and os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
    elif isinstance(file_path,bytes):
        sha256_hash.update(file_path)
    else:
        return None
    return sha256_hash.hexdigest()

## --- Configuration Management --- 

def get_erp_config():
    """Retrieves ERP configuration from the database."""
    print("Loading ERP configuration from database...")
    config = config_collection.find_one({'config_id':'default_erp'})
    if not config:
        print("Configuration not found!")
        return None
    print("Configuration loaded successfully.")
    return config

def setup_erp_config():
    """A one-time setup for the administarator to save their ERP details"""
    print("---Initial ERP Configuration Setup---")
    print("Please provide the following details for your college's ERP portal.")

    login_url = input("Enter the ERP Login URL (the form's 'action' URL, eg. https://erp.college.edu/afterloginAction): ")
    username_key = input("Enter the payload key for the username field (the 'name' attribute of the input: ")
    password_key = input("Enter the payload key for the username field (the 'name' attribute of the input: ")

    target_urls = []
    print('\nEnter the target URLs you want to scrape (e.g., for notices,timetables).')
    print("Press Enter with an empty line when you are finished.")
    while True:
        url_input = input(f"Target URL #{len(target_urls)+1}: ").strip()
        if not url_input:
            break
        target_urls.append(url_input)

    supported_file_types = []
    print("\nEnter the file extension to download (eg. .pdf, .docx, .jpg).")
    print("Print Enter with an empty line when you are finished.")
    while True:
        ext = input(f"File type #{len(supported_file_types) + 1}: ").strip()
        if not ext:
            break
        supported_file_types.append(ext if ext.startswith('.') else '.'+ext)

    config_data = {
        'config_id': 'default_erp',
        'login_url':login_url,
        'target_urls':target_urls,
        'supported_file_types': supported_file_types,
        'username_payload_key':username_key,
        'password_payload_key':password_key,
        'download_dir':'downloads'
    }

    config_collection.update_one(
        {'config_id':'default_erp'},
        {'$set':config_data},
        upsert=True
    )
    print("\nConfiguration saved successfully to the database!")
    return config_data

## _____ Main Logic_____

def scrape_erp_portal(config, username, password):
    """Logs into ERP using config from DB, and scrapes for specified """
    print("\nAttempting to log into the ERP portal...")

    with requests.Session() as session:
        session.headers.update({
            'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        login_payload = {
            config['username_payload_key']: username,
            config['password_payload_key']:password
        }

        try:
            print(f"Sending login credentials to: {config['login_url']}")
            login_res = session.post(config['login_url'],data=login_payload, timeout=15)
            login_res.raise_for_status()

            soup = BeautifulSoup(login_res.text, 'html.parser')
            username_field = soup.find('input',{'name':config['username_payload_key']})

            if username_field:
                print("Login failed! The login form was still detected on the response page.")
                print("Please check your credentials and configuration.")
                return 

            print("Login Successful!Scraping data through URLs...")

            for target_url in config['target_urls']:
                if not target_url:
                    print("Skipping an empty URL found in configuration...")
                    continue

                print(f"\n---Reading Page:{target_url}")
                protected_page_res = session.get(target_url)
                protected_page_res.raise_for_status()


                page_content_bytes = protected_page_res.content
                html_checksum = calculate_checksum(page_content_bytes)
                
                if html_checksum and not document_collection.find_one({'checksum':html_checksum}):
                    print(" -> New HTML content  detected on page. Archiving...")
                    document_collection.insert_one({
                        'source_url':target_url,
                        'download_timestamp':time.time(),
                        'checksum':html_checksum,
                        'status':'staged',
                        'file_type':'html_content',
                        'raw_html':page_content_bytes.decode('utf-8',errors='ignore')
                    })
                else:
                    print(" -> HTML content is unchanged since last checked.")

                print(f"Searching for file types: {', '.join(config['supported_file_types'])}")
                soup = BeautifulSoup(protected_page_res.content,'html.parser')
                links = soup.find_all('a')

                found_new_file_on_page = False
                for link in links:
                    href = link.get('href')
                    if not href:
                        continue
                    
                    for file_type in config['supported_file_types']:
                        if href.lower().endswith(file_type):
                            resource_url = urljoin(target_url,href)

                            if document_collection.find_one({'source_url':resource_url}):
                                continue
                            found_new_file_on_page = True
                            print(f"Downloading new file: {resource_url}")
                            pdf_response = session.get(resource_url)

                            file_name = os.path.basename(resource_url)
                            file_path = os.path.join(config['download_dir'],file_name)

                            with open(file_path,'wb') as f:
                                f.write(pdf_response.content)

                            checksum = calculate_checksum(file_path)
                            if document_collection.find_one({'checksum':checksum}):
                                print("Duplicate content found. Removing temp file.")
                                os.remove(file_path)
                            else:
                                print(f"New file stored with status 'staged'.")
                                document_collection.insert_one({
                                    'file_name':file_name,
                                    'source_url':resource_url,
                                    'download_timestamp':time.time(),
                                    'status':'staged',
                                    'file_type':file_type
                                })
                            break
                    
                if not found_new_file_on_page:
                    print(f"No new files found on this page during this check.")
        except requests.exceptions.RequestException as e:
            print(f"An error occurred during the request: {e}")


# def process_page():
#     """Fetches the notice page, finds PDFs, and downloads new ones."""
#     print(f"Checking for new notices at {NOTICE_BOARD_URL}...")

#     headers={
#         'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chorme/91.0.4472.124 Safari/537.36'
#     }
#     try:
#         # 1- > fetch the webpage
#         response = requests.get(NOTICE_BOARD_URL,headers=headers,timeout=15)
#         # print("1 Works here")
#         response.raise_for_status()

#         # 2 -> parsing the HTML to find all links
#         soup = BeautifulSoup(response.content,'html.parser')
#         # print("2 soup This worked too")
#         links=soup.find_all('a') # Finds all hyperlink tags <a>
#         # print("3 did i find the links?",links)

#         found_pdf_this_run=False
#         for link in links:
#             href = link.get('href')
#             # print("4 did i find a valid href?", href)
#             if href and '.pdf' in href.lower():
#                 found_pdf_this_run=True
#                 # Construst the full URL for the PDF
#                 # The handles cases where the link is relative (e.g., '/notice1.pdf')
#                 resource_url= urljoin(NOTICE_BOARD_URL,href)
                
#                 existing_doc_by_url=collection.find_one({'source_url':resource_url})
#                 if existing_doc_by_url:
#                     print(f"URL already in database:{resource_url}. Skipping...")
#                     continue
                
#                 # Download the PDF
#                 print(f"Found a PDF: {resource_url}, Downloading ...")
#                 try:
#                     pdf_response=requests.get(resource_url,headers=headers)
#                     pdf_response.raise_for_status()
#                     # Get the filename from the URL
#                     file_name = os.path.basename(resource_url)
#                     file_path = os.path.join(DOWNLOAD_DIR,file_name)

#                     # saving the pdf to the downloads folder
#                     with open(file_path,'wb+') as f:
#                         f.write(pdf_response.content)

#                     # Calculate checksum and check for duplicates before saving to DB
#                     checksum = calculate_checksum(file_path)

#                     # Check if a document with this checksum already exists
#                     existing_doc_by_checksum = collection.find_one({'checksum':checksum})

#                     if existing_doc_by_checksum:
#                         print(f"'{file_name}' already exists in the database. Skipping ...")
#                         # Clean up the duplicate file we just downloaded
#                         os.remove(file_path)
#                     else:
#                         print(f"New file found! Storing metadata for '{file_name}' in the database.")
#                         document_metadata = {
#                             'file_name':file_name,
#                             'source_url':resource_url,
#                             'download_timestamp':time.time(),
#                             'checksum':checksum,
#                             'status':'staged' # This file is now in our staging area [cite: 8]
#                         }
#                         collection.insert_one(document_metadata)
#                 except requests.exceptions.RequestException as e:
#                     print(f"-> Failed to download {resource_url}. Reason - {e}")

#                 if not found_pdf_this_run:
#                     print("Could not find any PDFs this run.")
#     except requests.exceptions.RequestException as e:
#         print(f"Error: Could not fetch the webpage. {e}")

#__________________Main Loop__________________

if __name__ == '__main__':
        erp_config = get_erp_config()
        if not erp_config or 'supported_file_types' not in erp_config:
            # Re-run setup if config is missing or doesn't have the new fields
            print("Configuration is incomplete or missing. Running setup...")
            erp_config = setup_erp_config()

        if not os.path.exists(erp_config['download_dir']):
            os.makedirs(erp_config['download_dir'])
        ERP_USERNAME = input("Enter ERP username: ")
        ERP_PASSWORD = getpass.getpass("Enter ERP Password: ")
        POLL_INTERVAL = 300

        while True:
            scrape_erp_portal(erp_config,ERP_USERNAME,ERP_PASSWORD)
            print(f"\nCheck complete for all target URLs. Waiting for {POLL_INTERVAL} seconds for the next cycle...")
            time.sleep(POLL_INTERVAL)



# if __name__ == '__main__':
#     # Create the downloads directory if it doesn't exist
#     if not os.path.exists(DOWNLOAD_DIR):
#         os.makedirs(DOWNLOAD_DIR)

#     while True:
#         process_page()
#         temp = POLL_INTERVAL
#         # while temp:
#         #     print(f"waitinf for {temp} seconds before the next check...")
#         #     time.sleep(1)
#         #     temp-=1
#         print(f"Waiting for {POLL_INTERVAL} seconds before the next check...")
#         time.sleep(POLL_INTERVAL)

