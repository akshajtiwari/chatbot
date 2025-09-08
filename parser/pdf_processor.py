import uvicorn
import pymongo
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import tempfile
import os
import itertools

# --- Stage 1: High-Fidelity Extraction ---
from unstructured.partition.pdf import partition_pdf
from unstructured.documents.elements import Table, Title, NarrativeText, ListItem

# --- Stage 2: AI-Powered Text Correction ---
from ctransformers import AutoModelForCausalLM

# --- Configuration ---
MONGO_CONNECTION_STRING = "mongodb://localhost:27017/"
MONGO_DATABASE_NAME = "pdf_processor_db_advanced"
MONGO_COLLECTION_NAME = "document_chunks_semantic"

# --- LLM Configuration for Cleaning ---
# IMPORTANT: Download the model file and place it in your project directory.
# Model suggestion: TheBloke/Mistral-7B-Instruct-v0.2-GGUF (q4_K_M quantization)
# Link: https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF
LLM_MODEL_PATH = "./mistral-7b-instruct-v0.2.Q4_K_M.gguf"
LLM_MODEL_TYPE = "mistral"

# --- Database Connection ---
try:
    client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
    db = client[MONGO_DATABASE_NAME]
    collection = db[MONGO_COLLECTION_NAME]
    collection.create_index([("content", pymongo.TEXT)])
    print("Successfully connected to MongoDB.")
except pymongo.errors.ConnectionFailure as e:
    print(f"Could not connect to MongoDB: {e}")
    exit()

# --- Load the AI Cleaning Model ---
# This model is loaded once when the server starts for efficiency.
try:
    if os.path.exists(LLM_MODEL_PATH):
        print(f"Loading AI cleaning model from: {LLM_MODEL_PATH}")
        llm = AutoModelForCausalLM.from_pretrained(
            LLM_MODEL_PATH,
            model_type=LLM_MODEL_TYPE,
            context_length=4096 # Increased context for larger chunks
        )
        print("✅ AI cleaning model loaded successfully.")
    else:
        llm = None
        print("⚠️ WARNING: AI cleaning model file not found.")
        print(f"   - The service will run WITHOUT the text correction stage.")
        print(f"   - Please download the model and place it at: {LLM_MODEL_PATH}")

except Exception as e:
    print(f"❌ ERROR: Failed to load the AI cleaning model: {e}")
    llm = None

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Advanced AI PDF Processing Service",
    description="An API that uses a 3-stage AI pipeline for extraction, cleaning, and semantic chunking of PDF content.",
    version="3.1.0" # Version updated for precision chunking
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Model ---
class DocumentChunk(BaseModel):
    document_name: str
    page_number: int
    chunk_type: str
    content: str

# --- Core AI Pipeline Logic ---

def ai_text_corrector(text: str) -> str:
    """
    Stage 2: Uses a local LLM to proofread and correct OCR errors in a block of text.
    """
    if not llm or not text.strip():
        return text # Return original text if model isn't loaded or text is empty

    prompt = f"""[INST] You are a highly intelligent text correction assistant. Your task is to proofread the following text, which was extracted from a document using OCR. Correct any and all spelling mistakes, formatting errors, or character recognition errors (e.g., '2' read as 'Z', '1' as 'l'). Do not summarize, add new information, or change the meaning. Only output the corrected text.

Text to correct:
---
{text}
---
Corrected text: [/INST]"""

    try:
        corrected_text = llm(prompt, max_new_tokens=2048, temperature=0.1)
        return corrected_text.strip()
    except Exception as e:
        print(f"Error during AI text correction: {e}")
        return text # Return original text on failure

def precise_semantic_chunker(elements: List, document_name: str) -> List[DocumentChunk]:
    """
    Stage 3 (Upgraded): Precisely separates tables and text blocks, creating
    contextually coherent chunks before running AI correction.
    """
    final_chunks = []
    
    # Group elements by page number to process page by page
    for page_num, page_elements_iterator in itertools.groupby(elements, key=lambda el: el.metadata.page_number):
        
        # Convert iterator to a list to allow multiple passes
        page_elements = list(page_elements_iterator)
        
        # Isolate all table elements on the page
        tables_on_page = [el for el in page_elements if isinstance(el, Table)]
        
        # Isolate all non-table (text) elements on the page
        text_elements_on_page = [el for el in page_elements if not isinstance(el, Table)]
        
        # Process each table individually
        for table in tables_on_page:
            print(f"Found and processing a table on page {page_num}...")
            table_html = getattr(table.metadata, 'text_as_html', str(table))
            if table_html and table_html.strip():
                cleaned_content = ai_text_corrector(table_html)
                final_chunks.append(DocumentChunk(
                    document_name=document_name,
                    page_number=page_num,
                    chunk_type="table",
                    content=cleaned_content
                ))

        # Combine all text elements on the page into a single coherent block
        if text_elements_on_page:
            print(f"Found and processing a text block on page {page_num}...")
            full_text_block = "\n\n".join([el.text for el in text_elements_on_page if el.text and el.text.strip()])
            
            if full_text_block.strip():
                cleaned_content = ai_text_corrector(full_text_block)
                final_chunks.append(DocumentChunk(
                    document_name=document_name,
                    page_number=page_num,
                    chunk_type="text_block",
                    content=cleaned_content
                ))
            
    print(f"Generated {len(final_chunks)} precise semantic chunks.")
    return final_chunks

# --- API Endpoint ---
@app.post("/process-pdf-advanced/", status_code=201)
async def process_pdf_advanced(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type.")

    filename = file.filename
    print(f"\n--- Starting advanced processing for: {filename} ---")
    pdf_bytes = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        # Stage 1: High-Fidelity Extraction
        elements = partition_pdf(filename=tmp_path, strategy="hi_res", infer_table_structure=True)
        print(f"Stage 1 Complete: Extracted {len(elements)} raw elements.")
        
        # Stage 3: Precise Semantic Chunking (which includes Stage 2 cleaning)
        final_chunks = precise_semantic_chunker(elements, filename)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI model processing failed: {e}")
    finally:
        os.remove(tmp_path)

    if not final_chunks:
        raise HTTPException(status_code=404, detail="Could not create any semantic chunks from the PDF.")
    
    # Store in MongoDB
    try:
        collection.delete_many({"document_name": filename})
        # Note: Pydantic v2 uses model_dump() instead of dict()
        chunks_dict = [chunk.model_dump() for chunk in final_chunks]
        result = collection.insert_many(chunks_dict)
        print(f"Successfully inserted {len(result.inserted_ids)} high-quality chunks for '{filename}'.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database operation failed: {e}")
        
    return {
        "message": "Successfully processed with 3-stage AI pipeline and stored content.",
        "filename": filename,
        "total_chunks_stored": len(final_chunks)
    }

@app.get("/")
def read_root():
    return {"status": "Advanced AI PDF Processing Service is running."}

