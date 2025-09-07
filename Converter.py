import argparse
import os
import fitz  # PyMuPDF library
import json
import re
import numpy as np
from sentence_transformers import SentenceTransformer, util
from pymongo import MongoClient
from urllib.parse import quote_plus

def is_local_file(filepath):
    """
    Checks if a given filepath is a local file.
    """
    return os.path.exists(filepath) and os.path.isfile(filepath)

def is_pdf(filepath):
    """
    Checks if a file is a PDF based on its extension.
    """
    return filepath.lower().endswith('.pdf')

def extract_text_from_pdf(filepath):
    """
    Extracts text from a single PDF file using PyMuPDF (fitz) and cleans it.
    """
    text = ""
    try:
        with fitz.open(filepath) as doc:
            for page in doc:
                text += page.get_text()
        
        # More powerful text cleaning to fix common OCR errors and formatting issues
        cleaned_text = re.sub(r'\s+', ' ', text).strip()
        cleaned_text = re.sub(r'Kanfiur', 'Kanpur', cleaned_text)
        cleaned_text = re.sub(r'ofthee', 'of the', cleaned_text)
        cleaned_text = re.sub(r'ATCTE', 'AICTE', cleaned_text)
        
        # New, specific fixes for observed OCR errors
        cleaned_text = re.sub(r"19th['‘]", '19th', cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r'August-z0zs', 'August-2025', cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r'B\.Tech-3ra Year', 'B.Tech-3rd Year', cleaned_text)
        cleaned_text = re.sub(r'fwho', 'who', cleaned_text)
        
        return cleaned_text
    except Exception as e:
        print(f"An unexpected error occurred during PDF processing: {e}")
        return None

def extract_metadata_and_schema(text):
    """
    Extracts structured metadata from the text based on predefined patterns
    and provides a JSON schema for it.
    """
    metadata = {
        "title": None,
        "date": None,
        "recipient": None,
        "sender": None,
        "subject": None
    }
    
    # Define a simple JSON schema for the metadata
    metadata_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The title of the notice, e.g., 'NOTICE'."},
            "date": {"type": "string", "description": "The date the notice was issued, e.g., 'August 18, 2025'."},
            "recipient": {"type": "string", "description": "The intended recipients, e.g., 'B.Tech-3rd Year'."},
            "sender": {"type": "string", "description": "The person or department issuing the notice, e.g., 'Prof. Raghvendra Singh'."},
            "subject": {"type": "string", "description": "The subject of the notice, e.g., 'Commencement of GATE Preparation Classes'."}
        }
    }

    # Use more robust regex to find specific patterns in the text
    title_match = re.search(r'\b(NOTICE)\b', text, re.IGNORECASE)
    if title_match:
        metadata["title"] = title_match.group(1).strip()
    
    # Improved date regex to be more flexible
    date_match = re.search(r'(?:[A-Z][a-z]+ \d{1,2}, \d{4})', text)
    if date_match:
        metadata["date"] = date_match.group(0).strip()
        
    recipient_match = re.search(r'Commencement of GATE Preparation Classes for (.*?)All the students', text, re.DOTALL)
    if recipient_match:
        metadata["recipient"] = recipient_match.group(1).strip().replace('.', '')
        
    # Improved sender regex to capture the name more accurately
    sender_match = re.search(r'\[(Prof\.\s+.*?)\]|Signature of (\w+)', text)
    if sender_match:
        if sender_match.group(1):
            metadata["sender"] = sender_match.group(1).strip()
        elif sender_match.group(2):
            metadata["sender"] = sender_match.group(2).strip()
        
    subject_match = re.search(r'NOTICE\s*(.*?)\s*All the students', text, re.DOTALL)
    if subject_match:
        metadata["subject"] = subject_match.group(1).strip()
        
    return metadata, metadata_schema

def semantic_chunk_text(text, model, threshold=0.6):
    """
    Splits a large string of text into semantically meaningful chunks.
    This is a more advanced method that groups sentences based on their
    semantic similarity. The threshold has been slightly increased to 0.6
    to create smaller, more focused chunks.
    """
    # Split text into sentences using a simple regex
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if not sentences:
        return []
        
    # Generate embeddings for each sentence
    sentence_embeddings = model.encode(sentences)

    # Calculate cosine similarity between adjacent sentences
    similarities = [util.cos_sim(sentence_embeddings[i], sentence_embeddings[i+1]).item() for i in range(len(sentences) - 1)]

    # Find the breakpoints where similarity drops below the threshold
    breakpoints = [i for i, sim in enumerate(similarities) if sim < threshold]

    chunks = []
    start_index = 0
    for bp in breakpoints:
        # Create a chunk from the start_index to the breakpoint
        chunk = " ".join(sentences[start_index:bp+1])
        chunks.append(chunk)
        start_index = bp + 1
        
    # Add the last chunk
    final_chunk = " ".join(sentences[start_index:])
    if final_chunk:
        chunks.append(final_chunk)
        
    return chunks

def save_parsed_document_locally(filename, document_data, directory="parsed_documents"):
    """
    Saves the parsed document data (text, chunks, metadata) to a local JSON file.
    """
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, os.path.splitext(filename)[0] + ".json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(document_data, f, indent=4, ensure_ascii=False)
    print(f"Parsed document saved locally to: {filepath}")

def save_embeddings_locally(filename, embeddings_data, directory="embeddings"):
    """
    Saves the embedding data to a local file.
    """
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, os.path.splitext(filename)[0] + "_embeddings.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(embeddings_data, f, indent=4, ensure_ascii=False)
    print(f"Embeddings saved locally to: {filepath}")

def create_and_save_document_to_mongodb(filepath, chunks, metadata, metadata_schema, db_name, collection_name):
    """
    Creates a single document containing all chunks and metadata for a given PDF
    and saves it to a MongoDB collection.
    """
    try:
        print("Step 1: Connecting to MongoDB...")
        client = MongoClient('mongodb://localhost:27017/')
        db = client[db_name]
        collection = db[collection_name]
        
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return

    print("Step 2: Loading Sentence Transformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    print("Step 3: Creating embeddings and preparing a single document for MongoDB...")
    # Prepare the list of chunk objects
    chunk_list = []
    for i, chunk_text in enumerate(chunks):
        embedding = model.encode(chunk_text).tolist()
        chunk_list.append({
            "chunk_id": i,
            "text": chunk_text,
            "embedding": embedding,
        })
    
    # Save the parsed data and embeddings locally first
    document_data = {
        "filepath": filepath,
        "filename": os.path.basename(filepath),
        "metadata": metadata,
        "metadata_schema": metadata_schema,
        "chunks": [
            {"chunk_id": chunk["chunk_id"], "text": chunk["text"]} for chunk in chunk_list
        ]
    }
    save_parsed_document_locally(os.path.basename(filepath), document_data)
    
    embeddings_data = {
        "filename": os.path.basename(filepath),
        "embeddings": [
            {"chunk_id": chunk["chunk_id"], "embedding": chunk["embedding"]} for chunk in chunk_list
        ]
    }
    save_embeddings_locally(os.path.basename(filepath), embeddings_data)


    print("Step 4: Inserting document into MongoDB...")
    # Create the single document to insert
    document_to_insert = {
        "filepath": filepath,
        "filename": os.path.basename(filepath),
        "metadata": metadata,
        "metadata_schema": metadata_schema,
        "chunks": chunk_list
    }

    # We use update_one with upsert=True to either insert a new document
    # or replace an existing one for the same file.
    result = collection.update_one(
        {"filename": document_to_insert["filename"]},
        {"$set": document_to_insert},
        upsert=True
    )

    if result.upserted_id:
        print(f"Successfully inserted new document with ID: {result.upserted_id}.")
    else:
        print(f"Successfully updated existing document for file: {document_to_insert['filename']}.")

    client.close()
    print("MongoDB connection closed.")


def main():
    """
    Main function to parse arguments and run the full pipeline.
    """
    parser = argparse.ArgumentParser(description="A script to process PDF files and store embeddings in MongoDB.")
    parser.add_argument('--file', type=str, required=True, help='Path to the PDF file.')
    parser.add_argument('--source', type=str, choices=['local', 'web'], required=True, help='Source of the file: "local" or "web".')

    args = parser.parse_args()
    filepath = args.file
    source = args.source

    if source == "local":
        if not is_local_file(filepath) or not is_pdf(filepath):
            print("Error: The provided path is not a valid local PDF file.")
            return

        print(f"Processing local PDF file: {filepath}")
        pdf_text = extract_text_from_pdf(filepath)
        if pdf_text:
            # Use semantic chunking for better results
            model = SentenceTransformer('all-MiniLM-L6-v2')
            chunks = semantic_chunk_text(pdf_text, model)
            
            if not chunks:
                print("Failed to create chunks from the extracted text.")
                return

            print(f"Successfully extracted text and created {len(chunks)} chunks using semantic chunking.")
            
            # Extract metadata and schema from the full text
            metadata, metadata_schema = extract_metadata_and_schema(pdf_text)
            print("Extracted Metadata:")
            print(json.dumps(metadata, indent=4))
            print("\nExtracted Metadata Schema:")
            print(json.dumps(metadata_schema, indent=4))
            
            # Now, use these chunks, metadata, and schema to create and save embeddings to MongoDB
            db_name = "rag_pipeline_db"
            collection_name = "document_embeddings"
            create_and_save_document_to_mongodb(filepath, chunks, metadata, metadata_schema, db_name, collection_name)
        else:
            print("Failed to extract text from the PDF.")
    elif source == "web":
        print("Web functionality is not yet implemented.")
    else:
        print(f"Error: Unknown source '{source}'. Please use 'local' or 'web'.")

if __name__ == "__main__":
    main()
