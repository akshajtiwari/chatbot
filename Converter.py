#!/usr/bin/env python3
"""
Intelligent PDF Parser with Text Chunking and Keyword-Based Filenaming
- Complete implementation with all missing methods restored
- Breaks text into structured chunks for better processing
- Uses keywords to generate descriptive filenames
- Enhanced search capabilities through keyword tagging
"""

import io
import json
import argparse
import re
import requests
import logging
import os
import time
import gc
import traceback
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import pandas as pd
from PIL import Image

import torch
from transformers import DonutProcessor, VisionEncoderDecoderModel, TableTransformerForObjectDetection
from torchvision import transforms
from pdf2image import convert_from_bytes
import pytesseract
from tqdm import tqdm
import pdfplumber

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Config:
    """Configuration settings for the PDF parser"""
    MAX_FILE_SIZE_MB = 50
    MAX_PAGES = 100
    TIMEOUT_SECONDS = 30
    GPU_MEMORY_THRESHOLD = 0.8
    TEXT_THRESHOLD = 100
    DPI = 200
    MAX_RETRIES = 3
    CHUNK_SIZE = 1000  # Approximate words per chunk
    KEYWORDS = ['fees', 'attendance', 'timetable', 'exam', 'result', 'schedule', 'notice', 'circular']

class IntelligentPDFParser:
    def __init__(self, config=None):
        self.config = config or Config()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.use_gpu = torch.cuda.is_available()
        logger.info(f"Using device: {self.device}")
        
        self.donut_model_name = "naver-clova-ix/donut-base-finetuned-cord-v2"
        self.donut_model = None
        self.donut_processor = None
        self.table_model_name = "microsoft/table-transformer-structure-recognition"
        self.table_model = None
        self.table_processor = None
        
        self.SCRIPT_TO_LANG_CODE = {
            'Latin': 'eng', 'Devanagari': 'hin', 'Cyrillic': 'rus', 
            'Arabic': 'ara', 'Japanese': 'jpn', 'Chinese': 'chi_sim',
            'Korean': 'kor', 'Greek': 'ell', 'Hebrew': 'heb'
        }

        # Header keyword sets for filtering
        self.header_keyword_sets = [
            {"pranveer", "singh", "institute", "technology"},
            {"kanpur", "delhi", "national", "highway"},
            {"ph", "tollfree", "email", "info@psit.ac.in"},
        ]
        
        # Validate dependencies
        self.validate_dependencies()

    def validate_dependencies(self):
        """Check if required system dependencies are available"""
        missing = []
        try:
            pytesseract.get_tesseract_version()
        except (pytesseract.TesseractNotFoundError, Exception):
            missing.append("Tesseract OCR")
            logger.warning("Tesseract not found. Some OCR features will be limited.")
        
        try:
            test_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<<>>\nstartxref\n10\n%%EOF"
            convert_from_bytes(test_pdf, first_page=1, last_page=1)
        except Exception as e:
            if "poppler" in str(e).lower() or "convert" in str(e).lower():
                missing.append("Poppler")
                logger.warning("Poppler utilities not found properly.")
        
        if missing:
            logger.warning(f"Missing system dependencies: {', '.join(missing)}")

    def get_gpu_memory_ratio(self):
        """Get current GPU memory usage ratio (allocated/total)"""
        if not self.use_gpu:
            return 0.0
        try:
            total_memory = torch.cuda.get_device_properties(0).total_memory
            allocated_memory = torch.cuda.memory_allocated()
            return allocated_memory / total_memory
        except Exception as e:
            logger.warning(f"Failed to get GPU memory info: {e}")
            return 0.0

    def load_donut_model(self):
        """Load the Donut model (if needed in the future)"""
        if self.donut_model is None:
            logger.info(f"Loading Donut model '{self.donut_model_name}'...")
            try:
                self.donut_processor = DonutProcessor.from_pretrained(self.donut_model_name)
                self.donut_model = VisionEncoderDecoderModel.from_pretrained(
                    self.donut_model_name
                ).to(self.device)
                logger.info("Donut model loaded successfully")
            except Exception as e:
                raise Exception(f"Failed to load Donut model: {str(e)}")

    def unload_donut_model(self):
        """Unload Donut model to free memory"""
        if self.donut_model is not None:
            try:
                del self.donut_model
                del self.donut_processor
                self.donut_model = None
                self.donut_processor = None
                if self.use_gpu:
                    torch.cuda.empty_cache()
                gc.collect()
                logger.info("Donut model unloaded")
            except Exception as e:
                logger.warning(f"Error unloading Donut model: {e}")

    def load_table_detection_model(self):
        """Lazy loading of Table Transformer model with memory management"""
        if self.table_model is None:
            if self.use_gpu and self.get_gpu_memory_ratio() > self.config.GPU_MEMORY_THRESHOLD and self.donut_model is not None:
                logger.info("High GPU memory usage, unloading Donut model")
                self.unload_donut_model()
            
            logger.info(f"Loading Table Transformer model '{self.table_model_name}'...")
            try:
                self.table_processor = transforms.Compose([
                    transforms.Resize(800), 
                    transforms.ToTensor(),
                    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
                ])
                self.table_model = TableTransformerForObjectDetection.from_pretrained(
                    self.table_model_name
                ).to(self.device)
                logger.info("Table Transformer model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load Table Transformer model: {str(e)}")
                raise

    def unload_table_model(self):
        """Unload Table Transformer model to free memory"""
        if self.table_model is not None:
            try:
                del self.table_model
                del self.table_processor
                self.table_model = None
                self.table_processor = None
                if self.use_gpu:
                    torch.cuda.empty_cache()
                gc.collect()
                logger.info("Table Transformer model unloaded")
            except Exception as e:
                logger.warning(f"Error unloading table model: {e}")

    def download_pdf(self, pdf_url: str) -> bytes:
        """Download PDF content from URL"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(pdf_url, headers=headers, timeout=self.config.TIMEOUT_SECONDS)
            response.raise_for_status()
            
            if (not response.headers.get('content-type', '').lower().endswith('pdf') and 
                not response.content[:4] == b'%PDF'):
                raise Exception("URL does not point to a valid PDF file")
            
            file_size_mb = len(response.content) / (1024 * 1024)
            if file_size_mb > self.config.MAX_FILE_SIZE_MB:
                logger.warning(f"Large PDF detected ({file_size_mb:.1f}MB), processing may be slow")
            
            return response.content
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to download PDF: {str(e)}")

    def download_pdf_with_retry(self, pdf_url: str) -> bytes:
        """Download PDF with retry mechanism for timeouts"""
        for attempt in range(self.config.MAX_RETRIES):
            try:
                return self.download_pdf(pdf_url)
            except requests.exceptions.Timeout:
                if attempt == self.config.MAX_RETRIES - 1:
                    raise Exception(f"Download timed out after {self.config.MAX_RETRIES} attempts")
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Timeout occurred, retrying in {wait_time}s...")
                time.sleep(wait_time)
            except requests.exceptions.RequestException as e:
                if attempt == self.config.MAX_RETRIES - 1:
                    raise Exception(f"Failed to download PDF after {self.config.MAX_RETRIES} attempts: {str(e)}")
                wait_time = 2 ** attempt
                logger.warning(f"Download failed, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
            except Exception as e:
                raise Exception(f"Unexpected error during download: {str(e)}")

    def is_text_based_pdf(self, pdf_content: bytes) -> bool:
        """Determine if PDF is text-based or image-based"""
        try:
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                if not pdf.pages:
                    logger.warning("PDF has no pages")
                    return False
                pages_to_check = min(3, len(pdf.pages))
                total_text = "".join(pdf.pages[i].extract_text() or "" for i in range(pages_to_check))
                clean_text = re.sub(r'\s+', ' ', total_text).strip()
                return len(clean_text) > self.config.TEXT_THRESHOLD
        except Exception as e:
            logger.error(f"Error analyzing PDF type: {e}")
            return False

    def chunk_text(self, text: str, chunk_size: int = None) -> List[Dict[str, Any]]:
        """
        Break text into manageable chunks with metadata
        Returns list of chunks with word count and potential keywords
        """
        if chunk_size is None:
            chunk_size = self.config.CHUNK_SIZE
            
        chunks = []
        words = text.split()
        
        # If text is small enough, return as single chunk
        if len(words) <= chunk_size:
            return [{
                "text": text,
                "word_count": len(words),
                "char_count": len(text),
                "keywords": self.extract_keywords(text)
            }]
        
        # Split into chunks
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            
            chunks.append({
                "text": chunk_text,
                "word_count": len(chunk_words),
                "char_count": len(chunk_text),
                "keywords": self.extract_keywords(chunk_text),
                "chunk_id": f"chunk_{len(chunks)+1}"
            })
        
        return chunks

    def extract_keywords(self, text: str, max_keywords: int = 5) -> List[str]:
        """
        Extract relevant keywords from text based on config.KEYWORDS
        """
        text_lower = text.lower()
        found_keywords = []
        
        # Check for predefined keywords
        for keyword in self.config.KEYWORDS:
            if keyword in text_lower:
                found_keywords.append(keyword)
                
                if len(found_keywords) >= max_keywords:
                    break
        
        return found_keywords

    def extract_subject_from_text(self, text: str) -> Tuple[str, List[str]]:
        """
        Extract subject and keywords from text
        Returns (subject, keywords) tuple
        """
        # Extract keywords first
        keywords = self.extract_keywords(text, max_keywords=3)
        
        # Then extract subject
        def is_valid_subject(candidate: str) -> bool:
            if not candidate or not isinstance(candidate, str):
                return False
                
            clean_candidate = candidate.strip()
            if not clean_candidate:
                return False
                
            lower_candidate = clean_candidate.lower()
            
            # Check against header keyword sets
            line_words = set(lower_candidate.split())
            for keyword_set in self.header_keyword_sets:
                if keyword_set.issubset(line_words):
                    return False

            if not (10 <= len(clean_candidate) <= 120):
                return False
                
            if any(word in lower_candidate for word in ['page', 'date', 'copyright', 'confidential', 'http://', 'https://']):
                return False
                
            if not any(c.isalpha() for c in clean_candidate):
                return False
                
            return True

        # 1. Look for explicit keywords first
        explicit_pattern = r"^(?:Subject|Sub|Ref|Reference|Regarding|Re|Topic)[\s:\\-]+\s*(.+)$"
        match = re.search(explicit_pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            candidate = match.group(1).strip()
            if is_valid_subject(candidate):
                return candidate, keywords

        # 2. Look for common document titles
        lines = text.split('\n')[:15]
        for line in lines:
            clean_line = line.strip()
            if not clean_line:
                continue
            
            if clean_line.upper() == "ORDER":
                return clean_line.upper(), keywords
                
            title_keywords = ['notice', 'report', 'minutes', 'agenda', 'proposal', 'circular']
            if any(keyword in clean_line.lower() for keyword in title_keywords):
                if is_valid_subject(clean_line):
                    return clean_line, keywords
        
        # 3. Fallback: find the first meaningful line
        for line in lines:
            clean_line = line.strip()
            if is_valid_subject(clean_line) and not clean_line.isdigit():
                 return clean_line, keywords

        return "Untitled_Document", keywords

    def sanitize_filename(self, name: str) -> str:
        """Cleans a string to be a valid and safe filename"""
        if not name or not isinstance(name, str):
            return "document"
            
        name = re.sub(r'[\\/*?:"<>|]', "", name)
        name = re.sub(r'[\s\-\+]+', "_", name)
        name = re.sub(r'^_+|_+$', "", name)
        name = re.sub(r'_+', "_", name)
        return name[:80] if name else "document"

    def extract_text_and_tables_from_native_pdf(self, pdf_content: bytes) -> Dict[str, Any]:
        """
        Extract text and tables from text-based PDF with chunking
        """
        logger.info("Extracting text and tables from text-based PDF...")
        full_text_parts, all_tables = [], []
        
        try:
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                total_pages = min(len(pdf.pages), self.config.MAX_PAGES)
                
                # Extract text by page for chunking
                page_texts = []
                for i in tqdm(range(total_pages), desc="Processing Native PDF"):
                    try:
                        page = pdf.pages[i]
                        
                        # Extract tables
                        tables = page.extract_tables()
                        if tables:
                            for idx, table_data in enumerate(tables):
                                if table_data and len(table_data) > 1:
                                    try:
                                        df = pd.DataFrame(table_data[1:], columns=table_data[0])
                                        all_tables.append({
                                            "page": i + 1, 
                                            "table_index": idx, 
                                            "data_json": df.to_json(orient='records', force_ascii=False), 
                                            "data_csv": df.to_csv(index=False)
                                        })
                                    except Exception as e:
                                        logger.warning(f"Failed to process table on page {i+1}: {e}")
                        
                        # Extract text
                        def not_within_bboxes(obj):
                            for table in page.find_tables():
                                bbox = table.bbox
                                if (bbox[0] <= obj["x0"] <= bbox[2] and bbox[1] <= obj["top"] <= bbox[3]):
                                    return False
                            return True
                            
                        plain_text = page.filter(not_within_bboxes).extract_text()
                        if plain_text:
                            page_texts.append({
                                "page_number": i + 1,
                                "text": plain_text,
                                "word_count": len(plain_text.split())
                            })
                            full_text_parts.append(plain_text)
                    except Exception as e:
                        logger.warning(f"Error processing page {i+1}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error processing native PDF: {e}")
            raise
            
        full_text = "\n\n".join(full_text_parts).strip()
        
        # Chunk the text for better processing
        text_chunks = self.chunk_text(full_text)
        
        return {
            "full_text": full_text,
            "text_chunks": text_chunks,
            "page_texts": page_texts,  # Keep page-by-page text as well
            "tables": all_tables
        }

    def extract_tables_with_pipeline(self, pdf_content: bytes) -> Dict[str, Any]:
        """
        Two-stage table extraction pipeline for image-based PDFs
        """
        logger.info("Starting two-stage table extraction pipeline...")
        
        try:
            self.load_table_detection_model()
            
            # Get page count safely
            try:
                with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                    total_pages = len(pdf.pages)
            except:
                total_pages = 1  # Fallback
                
            pages_to_process = min(total_pages, self.config.MAX_PAGES)
            images = convert_from_bytes(pdf_content, first_page=1, last_page=pages_to_process, dpi=self.config.DPI)
            
            all_tables, full_text_parts = [], []
            for page_num, image in enumerate(tqdm(images, desc="Processing Image Pages"), 1):
                try:
                    full_text_parts.append(pytesseract.image_to_string(image, lang='eng'))
                except Exception as e:
                    logger.warning(f"OCR failed for page {page_num}: {e}")
                    full_text_parts.append("")
                
                try:
                    pixel_values = self.table_processor(image.convert("RGB")).unsqueeze(0).to(self.device)
                    with torch.no_grad():
                        outputs = self.table_model(pixel_values)
                    
                    target_sizes = torch.tensor([image.size[::-1]]).to(self.device)
                    results = self.table_model.post_process(outputs, target_sizes)[0]
                    table_boxes = results['boxes'][results['labels'] == self.table_model.config.label2id['table']].tolist()
                    
                    for table_idx, table_bbox in enumerate(table_boxes):
                        try:
                            table_image = image.crop(table_bbox)
                            ocr_data = pytesseract.image_to_data(table_image, lang='eng', output_type=pytesseract.Output.DICT, config='--psm 6')
                            df = pd.DataFrame()
                            current_line, row_data = -1, []
                            for i, text in enumerate(ocr_data['text']):
                                if int(ocr_data['conf'][i]) > 50 and text.strip():
                                    if ocr_data['line_num'][i] != current_line:
                                        if row_data:
                                            df = pd.concat([df, pd.DataFrame([row_data])], ignore_index=True)
                                        row_data = []
                                        current_line = ocr_data['line_num'][i]
                                    row_data.append(text.strip())
                            if row_data:
                                df = pd.concat([df, pd.DataFrame([row_data])], ignore_index=True)

                            if not df.empty:
                                if len(df) > 1 and len(df.columns) == len(df.iloc[0]) and not any(
                                    cell.isdigit() for cell in df.iloc[0] if isinstance(cell, str)):
                                    df.columns = df.iloc[0]
                                    df = df[1:].reset_index(drop=True)
                                all_tables.append({
                                    "page": page_num, 
                                    "table_index": table_idx, 
                                    "data_json": df.to_json(orient='records', force_ascii=False), 
                                    "data_csv": df.to_csv(index=False)
                                })
                        except Exception as e:
                            logger.warning(f"Failed to process table {table_idx} on page {page_num}: {e}")
                except Exception as e:
                    logger.warning(f"Table detection failed on page {page_num}: {e}")
                    
            full_text = "\n".join(full_text_parts)
            text_chunks = self.chunk_text(full_text)
            
            return {
                "tables": all_tables, 
                "full_text": full_text,
                "text_chunks": text_chunks,
                "method": "table-pipeline"
            }
        except Exception as e:
            logger.error(f"Table pipeline failed: {e}")
            raise
        finally:
            self.unload_table_model()

    def extract_with_tesseract(self, pdf_content: bytes, lang: str = 'eng') -> Dict[str, Any]:
        """
        Extract text using Tesseract with chunking support
        """
        logger.info(f"Using Tesseract OCR with language: {lang}")
        
        # Get page count safely
        try:
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                total_pages = len(pdf.pages)
        except:
            total_pages = 1
            
        pages_to_process = min(total_pages, self.config.MAX_PAGES)
        
        try:
            images = convert_from_bytes(pdf_content, first_page=1, last_page=pages_to_process, dpi=self.config.DPI)
            full_text_parts = []
            page_texts = []
            
            for page_num, img in enumerate(tqdm(images, desc="OCR Progress"), 1):
                try:
                    page_text = pytesseract.image_to_string(img, lang=lang)
                    full_text_parts.append(page_text)
                    page_texts.append({
                        "page_number": page_num,
                        "text": page_text,
                        "word_count": len(page_text.split())
                    })
                except Exception as e:
                    logger.warning(f"OCR failed for page {page_num}: {e}")
                    page_texts.append({
                        "page_number": page_num,
                        "text": "",
                        "word_count": 0
                    })
                    full_text_parts.append("")
                    
            full_text = "\n".join(full_text_parts)
            text_chunks = self.chunk_text(full_text)
            
            return {
                "full_text": full_text,
                "text_chunks": text_chunks,
                "page_texts": page_texts,
                "method": f"tesseract-{lang}"
            }
        except Exception as e:
            logger.error(f"Tesseract extraction failed: {e}")
            raise

    def detect_document_script(self, pdf_content: bytes) -> str:
        """Detect the primary script used in the document"""
        try:
            images = convert_from_bytes(pdf_content, first_page=1, last_page=1, dpi=150)
            if images:
                osd = pytesseract.image_to_osd(images[0], output_type=pytesseract.Output.DICT)
                return osd.get('script', 'Latin')
        except Exception as e:
            logger.warning(f"Script detection failed: {e}")
        return 'Latin'

    def generate_filename(self, subject: str, keywords: List[str]) -> str:
        """
        Generate a filename based on subject and keywords
        Format: {primary_keyword}_{subject}_{timestamp}
        """
        # Clean the subject
        clean_subject = self.sanitize_filename(subject)
        
        # Use the first keyword if available, otherwise use "document"
        primary_keyword = keywords[0] if keywords else "document"
        
        # Add timestamp for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Limit filename length
        max_subject_length = 50
        if len(clean_subject) > max_subject_length:
            clean_subject = clean_subject[:max_subject_length].rstrip('_')
        
        return f"{primary_keyword}_{clean_subject}_{timestamp}"

    def parse_pdf(self, pdf_url: str) -> Dict[str, Any]:
        """
        Main method to parse PDF from URL with enhanced text chunking
        """
        pdf_content = None
        try:
            # Download PDF
            pdf_content = self.download_pdf_with_retry(pdf_url)
            
            # Get page count
            try:
                with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                    page_count = len(pdf.pages)
            except Exception as e:
                logger.warning(f"Failed to get page count: {e}")
                page_count = 0
            
            # Determine PDF type
            is_text_based = self.is_text_based_pdf(pdf_content)
            extraction_data = {}
            extraction_method = ""
            detected_script = "N/A"
            
            if is_text_based:
                logger.info("PDF detected as text-based")
                extraction_data = self.extract_text_and_tables_from_native_pdf(pdf_content)
                extraction_method = "pdfplumber_native"
            else:
                logger.info("PDF detected as image-based")
                detected_script = self.detect_document_script(pdf_content)
                logger.info(f"Detected script: {detected_script}")
                
                if detected_script == 'Latin':
                    try:
                        # For Latin scripts, try table extraction first
                        extraction_data = self.extract_tables_with_pipeline(pdf_content)
                        extraction_method = extraction_data.get("method", "table-pipeline")
                        
                        # If no tables found or extraction failed, fall back to OCR
                        if not extraction_data.get("tables") or not extraction_data.get("full_text"):
                            logger.info("Pipeline found no tables, using full-page Tesseract")
                            extraction_data = self.extract_with_tesseract(pdf_content, 'eng')
                            extraction_method = "tesseract-eng-fallback"
                    except Exception as e:
                        logger.warning(f"Table pipeline failed, falling back to Tesseract: {e}")
                        extraction_data = self.extract_with_tesseract(pdf_content, 'eng')
                        extraction_method = "tesseract-fallback"
                else:
                    # For non-Latin scripts, use OCR directly
                    lang_code = self.SCRIPT_TO_LANG_CODE.get(detected_script, 'eng')
                    extraction_data = self.extract_with_tesseract(pdf_content, lang_code)
                    extraction_method = extraction_data.get("method", f"tesseract-{lang_code}")
            
            # Extract subject and keywords from the full text
            full_text = extraction_data.get("full_text", "")
            subject, keywords = self.extract_subject_from_text(full_text)
            
            # Generate filename based on subject and keywords
            filename = self.generate_filename(subject, keywords)
            
            # Build final result with chunked text
            final_result = {
                "document_summary": {
                    "subject": subject, 
                    "keywords": keywords,
                    "word_count": len(full_text.split()),
                    "table_count": len(extraction_data.get("tables", [])), 
                    "page_count": page_count,
                    "chunk_count": len(extraction_data.get("text_chunks", [])),
                    "suggested_filename": filename
                },
                "content": {
                    "full_text": full_text,
                    "text_chunks": extraction_data.get("text_chunks", []),
                    "page_texts": extraction_data.get("page_texts", []),
                    "tables": extraction_data.get("tables", [])
                },
                "metadata": {
                    "content_type": "text" if is_text_based else "image", 
                    "extraction_method": extraction_method,
                    "script_detected": detected_script if not is_text_based else "N/A", 
                    "extraction_timestamp": datetime.now().isoformat()
                },
                "source_metadata": {
                    "url": pdf_url, 
                    "processing_timestamp": datetime.now().isoformat(),
                    "processing_device": self.device, 
                    "file_size_mb": len(pdf_content) / (1024 * 1024) if pdf_content else 0
                }
            }
            return final_result
            
        except Exception as e:
            logger.error(f"PDF processing failed: {e}")
            logger.error(traceback.format_exc())
            return {
                "error": str(e), 
                "error_type": type(e).__name__, 
                "timestamp": datetime.now().isoformat(),
                "pdf_url": pdf_url,
                "pdf_size": len(pdf_content) if pdf_content else 0
            }
        finally:
            # Ensure models are always unloaded
            self.unload_table_model()
            self.unload_donut_model()

def main():
    parser = argparse.ArgumentParser(description="Intelligent PDF Parser with Text Chunking and Keyword-Based Filenaming")
    parser.add_argument("pdf_url", help="URL of the PDF to parse")
    parser.add_argument("--output_dir", "-o", help="Directory to save the output JSON file", default=None)
    parser.add_argument("--config", "-c", help="Path to custom config JSON", default=None)
    
    args = parser.parse_args()
    
    config = Config()
    if args.config:
        try:
            with open(args.config, 'r') as f:
                custom_config = json.load(f)
                for key, value in custom_config.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
        except Exception as e:
            logger.warning(f"Failed to load custom config: {e}")
    
    pdf_parser = IntelligentPDFParser(config)
    result = pdf_parser.parse_pdf(args.pdf_url)
    
    if "error" in result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1
    
    if args.output_dir:
        # Use the suggested filename from the parser
        filename = result.get("document_summary", {}).get("suggested_filename", "document")
        full_filename = f"{filename}.json"
        
        os.makedirs(args.output_dir, exist_ok=True)
        output_path = os.path.join(args.output_dir, full_filename)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            subject = result.get("document_summary", {}).get("subject", "Untitled Document")
            keywords = result.get("document_summary", {}).get("keywords", [])
            
            print(f"✓ Successfully parsed: '{subject}'")
            print(f"✓ Keywords detected: {', '.join(keywords) if keywords else 'None'}")
            print(f"✓ Results saved to: {output_path}")
            print(f"✓ Pages: {result['document_summary']['page_count']}, "
                  f"Words: {result['document_summary']['word_count']}, "
                  f"Tables: {result['document_summary']['table_count']}, "
                  f"Chunks: {result['document_summary']['chunk_count']}")
        except Exception as e:
            print(f"Error saving results: {e}")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return 0
    
if __name__ == "__main__":
    exit(main())