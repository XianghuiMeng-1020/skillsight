"""
Document Parsers for SkillSight
- TXT, DOCX, PDF parsing with chunking
"""
import hashlib
import io
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _make_snippet(text: str, max_len: int = 220) -> str:
    """Create a snippet from text."""
    t = (text or "").strip().replace("\n", " ")
    t = re.sub(r"\s+", " ", t)
    if len(t) <= max_len:
        return t
    return t[:max_len] + "..."


def _compute_hash(text: str) -> str:
    """Compute SHA-256 hash of text."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ====================
# TXT Parser
# ====================
def parse_txt_to_chunks(
    content: str,
    min_chunk_len: int = 50,
) -> List[Dict[str, Any]]:
    """
    Parse plain text into chunks by double newlines.
    Returns list of chunk dicts with char_start, char_end, chunk_text, snippet, quote_hash.
    """
    if not content:
        return []
    
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    chunks = []
    cursor = 0
    idx = 0
    
    for part in text.split("\n\n"):
        part_strip = part.strip()
        if len(part_strip) < min_chunk_len:
            cursor += len(part) + 2
            continue
        
        # Find position in original text
        pos = text.find(part, cursor)
        if pos == -1:
            pos = cursor
        
        char_start = pos
        char_end = pos + len(part)
        
        chunks.append({
            "idx": idx,
            "char_start": char_start,
            "char_end": char_end,
            "chunk_text": part_strip,
            "snippet": _make_snippet(part_strip),
            "quote_hash": _compute_hash(part_strip),
            "section_path": None,
            "page_start": None,
            "page_end": None,
        })
        
        cursor = char_end + 2
        idx += 1
    
    return chunks


# ====================
# DOCX Parser
# ====================
def parse_docx_to_chunks(
    file_path: str,
    min_chunk_len: int = 50,
) -> List[Dict[str, Any]]:
    """
    Parse DOCX file into chunks by paragraphs.
    Preserves heading hierarchy in section_path.
    """
    try:
        from docx import Document
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
    except ImportError:
        raise ImportError("python-docx is required for DOCX parsing. Install with: pip install python-docx")
    
    doc = Document(file_path)
    chunks = []
    idx = 0
    char_cursor = 0
    current_section = []
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        
        # Detect headings
        style_name = para.style.name if para.style else ""
        is_heading = style_name.lower().startswith("heading")
        
        if is_heading:
            # Extract heading level (Heading 1, Heading 2, etc.)
            level_match = re.search(r"(\d+)", style_name)
            level = int(level_match.group(1)) if level_match else 1
            
            # Update section path
            while len(current_section) >= level:
                current_section.pop()
            current_section.append(text)
        
        # Skip very short paragraphs
        if len(text) < min_chunk_len and not is_heading:
            char_cursor += len(text) + 1
            continue
        
        section_path = " > ".join(current_section) if current_section else None
        
        chunks.append({
            "idx": idx,
            "char_start": char_cursor,
            "char_end": char_cursor + len(text),
            "chunk_text": text,
            "snippet": _make_snippet(text),
            "quote_hash": _compute_hash(text),
            "section_path": section_path,
            "page_start": None,  # DOCX doesn't have page info
            "page_end": None,
        })
        
        char_cursor += len(text) + 1
        idx += 1
    
    return chunks


def parse_docx_bytes_to_chunks(
    file_bytes: bytes,
    min_chunk_len: int = 50,
) -> List[Dict[str, Any]]:
    """
    Parse DOCX from bytes into chunks.
    """
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx is required for DOCX parsing. Install with: pip install python-docx")
    
    doc = Document(io.BytesIO(file_bytes))
    chunks = []
    idx = 0
    char_cursor = 0
    current_section = []
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        
        style_name = para.style.name if para.style else ""
        is_heading = style_name.lower().startswith("heading")
        
        if is_heading:
            level_match = re.search(r"(\d+)", style_name)
            level = int(level_match.group(1)) if level_match else 1
            while len(current_section) >= level:
                current_section.pop()
            current_section.append(text)
        
        if len(text) < min_chunk_len and not is_heading:
            char_cursor += len(text) + 1
            continue
        
        section_path = " > ".join(current_section) if current_section else None
        
        chunks.append({
            "idx": idx,
            "char_start": char_cursor,
            "char_end": char_cursor + len(text),
            "chunk_text": text,
            "snippet": _make_snippet(text),
            "quote_hash": _compute_hash(text),
            "section_path": section_path,
            "page_start": None,
            "page_end": None,
        })
        
        char_cursor += len(text) + 1
        idx += 1
    
    return chunks


# ====================
# PDF Parser
# ====================
def parse_pdf_to_chunks(
    file_path: str,
    min_chunk_len: int = 50,
) -> List[Dict[str, Any]]:
    """
    Parse PDF file into chunks by pages/paragraphs.
    Preserves page numbers.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF is required for PDF parsing. Install with: pip install pymupdf")
    
    doc = fitz.open(file_path)
    chunks = []
    idx = 0
    char_cursor = 0
    
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if not text.strip():
            continue
        
        # Split by double newlines within page
        paragraphs = text.split("\n\n")
        
        for para in paragraphs:
            para_text = para.strip()
            para_text = re.sub(r"\s+", " ", para_text)  # Normalize whitespace
            
            if len(para_text) < min_chunk_len:
                char_cursor += len(para_text) + 2
                continue
            
            chunks.append({
                "idx": idx,
                "char_start": char_cursor,
                "char_end": char_cursor + len(para_text),
                "chunk_text": para_text,
                "snippet": _make_snippet(para_text),
                "quote_hash": _compute_hash(para_text),
                "section_path": None,
                "page_start": page_num,
                "page_end": page_num,
            })
            
            char_cursor += len(para_text) + 2
            idx += 1
    
    doc.close()
    return chunks


def parse_pdf_bytes_to_chunks(
    file_bytes: bytes,
    min_chunk_len: int = 50,
) -> List[Dict[str, Any]]:
    """
    Parse PDF from bytes into chunks.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF is required for PDF parsing. Install with: pip install pymupdf")
    
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    chunks = []
    idx = 0
    char_cursor = 0
    
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if not text.strip():
            continue
        
        paragraphs = text.split("\n\n")
        
        for para in paragraphs:
            para_text = para.strip()
            para_text = re.sub(r"\s+", " ", para_text)
            
            if len(para_text) < min_chunk_len:
                char_cursor += len(para_text) + 2
                continue
            
            chunks.append({
                "idx": idx,
                "char_start": char_cursor,
                "char_end": char_cursor + len(para_text),
                "chunk_text": para_text,
                "snippet": _make_snippet(para_text),
                "quote_hash": _compute_hash(para_text),
                "section_path": None,
                "page_start": page_num,
                "page_end": page_num,
            })
            
            char_cursor += len(para_text) + 2
            idx += 1
    
    doc.close()
    return chunks


# ====================
# Unified Parser
# ====================
def parse_file_to_chunks(
    file_path: str = None,
    file_bytes: bytes = None,
    filename: str = None,
    min_chunk_len: int = 50,
) -> List[Dict[str, Any]]:
    """
    Unified parser that detects file type and parses accordingly.
    
    Args:
        file_path: Path to file (for file-based parsing)
        file_bytes: File content as bytes (for in-memory parsing)
        filename: Filename to detect extension (required if using file_bytes)
        min_chunk_len: Minimum chunk length
    
    Returns:
        List of chunk dictionaries
    """
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == ".txt" or ext == ".md" or ext == ".markdown":
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            return parse_txt_to_chunks(content, min_chunk_len)
        elif ext == ".csv":
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            return parse_txt_to_chunks(content, min_chunk_len)
        elif ext == ".docx":
            return parse_docx_to_chunks(file_path, min_chunk_len)
        elif ext == ".pdf":
            return parse_pdf_to_chunks(file_path, min_chunk_len)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    
    elif file_bytes and filename:
        ext = os.path.splitext(filename)[1].lower()
        
        if ext == ".txt" or ext == ".md" or ext == ".markdown":
            try:
                content = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = file_bytes.decode("utf-8", errors="ignore")
            return parse_txt_to_chunks(content, min_chunk_len)
        elif ext == ".csv":
            try:
                content = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = file_bytes.decode("utf-8", errors="ignore")
            return parse_txt_to_chunks(content, min_chunk_len)
        elif ext == ".docx":
            return parse_docx_bytes_to_chunks(file_bytes, min_chunk_len)
        elif ext == ".pdf":
            return parse_pdf_bytes_to_chunks(file_bytes, min_chunk_len)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    
    else:
        raise ValueError("Either file_path or (file_bytes + filename) must be provided")
