# Protocol 5: Chunking (v0.1)

## Purpose
Defines how documents are split into chunks for evidence retrieval and assessment. Ensures consistent, traceable text segmentation across document types.

## Scope
- **In scope:** Chunking strategy, chunk structure, metadata preservation
- **Out of scope:** Embedding generation, vector storage

## Objects and Fields (v0.1)

### Chunk
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `chunk_id` | UUID | Yes | Unique chunk identifier |
| `doc_id` | UUID | Yes | Reference to source document |
| `idx` | integer | Yes | Order index within document (0-indexed) |
| `char_start` | integer | Yes | Character offset start in original document |
| `char_end` | integer | Yes | Character offset end in original document |
| `chunk_text` | string | Yes | Full text content of chunk |
| `snippet` | string | Yes | Preview (first 220 chars + "...") |
| `quote_hash` | string | Yes | SHA-256 of chunk_text for integrity |
| `section_path` | string | No | Heading path (e.g., "2.1 Methods") |
| `page_start` | integer | No | PDF page number (1-indexed) |
| `page_end` | integer | No | PDF page number end |
| `created_at` | timestamp | Yes | Creation timestamp |

## Chunking Strategy (v0.1)

### Text Files (.txt)
- Split on double newlines (`\n\n`)
- Each paragraph becomes a chunk
- Preserve original character offsets

### Word Documents (.docx)
- Split on paragraph boundaries
- Preserve heading hierarchy in `section_path`
- Track paragraph styles for structure

### PDF Files (.pdf)
- Extract text per page
- Split on double newlines within pages
- Preserve page numbers in `page_start`/`page_end`

### Parameters
| Parameter | Value | Description |
|-----------|-------|-------------|
| `max_chunk_length` | 2000 chars | Maximum chunk size |
| `min_chunk_length` | 50 chars | Minimum chunk size (skip smaller) |
| `overlap` | 0 | No overlap between chunks (v0.1) |

## Rules (v0.1)

1. **Ordering:** Chunks are ordered by `idx` to reconstruct document flow.
2. **Integrity:** `quote_hash` is computed at chunk creation time.
3. **Snippet:** First 220 characters + "..." if truncated.
4. **Empty Chunks:** Chunks with only whitespace are skipped.
5. **Structure Preservation:** Headers/section paths are inherited by child paragraphs.

## Implementation

```python
import hashlib
import uuid

def chunk_text_file(text: str) -> list[dict]:
    """Chunk a plain text file by double newlines."""
    chunks = []
    text = text.replace("\r\n", "\n")
    cursor = 0
    idx = 0
    
    for part in text.split("\n\n"):
        part_strip = part.strip()
        if len(part_strip) < 50:  # Skip small chunks
            cursor += len(part) + 2
            continue
        
        # Find actual position in original text
        pos = text.find(part, cursor)
        if pos == -1:
            pos = cursor
        
        char_start = pos
        char_end = pos + len(part)
        
        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "idx": idx,
            "char_start": char_start,
            "char_end": char_end,
            "chunk_text": part_strip,
            "snippet": _make_snippet(part_strip),
            "quote_hash": hashlib.sha256(part_strip.encode()).hexdigest(),
            "section_path": None,
            "page_start": None,
            "page_end": None,
        })
        
        cursor = char_end + 2
        idx += 1
    
    return chunks

def _make_snippet(text: str, max_len: int = 220) -> str:
    """Create snippet from text."""
    text = text.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
```

## Database Schema

```sql
CREATE TABLE chunks (
    chunk_id UUID PRIMARY KEY,
    doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    snippet TEXT NOT NULL,
    quote_hash TEXT NOT NULL,
    section_path TEXT,
    page_start INTEGER,
    page_end INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX idx_chunks_doc_idx ON chunks(doc_id, idx);
```

## Examples

Input document (text):
```
Introduction

This is the first paragraph of the document.

Methods

We used the following approach...
```

Output chunks:
```json
[
  {
    "chunk_id": "...",
    "idx": 0,
    "char_start": 0,
    "char_end": 12,
    "chunk_text": "Introduction",
    "snippet": "Introduction",
    "quote_hash": "..."
  },
  {
    "chunk_id": "...",
    "idx": 1,
    "char_start": 14,
    "char_end": 60,
    "chunk_text": "This is the first paragraph of the document.",
    "snippet": "This is the first paragraph of the document.",
    "quote_hash": "..."
  }
]
```

## Open Questions
- [ ] Should we implement overlapping chunks for better retrieval?
- [ ] How to handle tables and images in documents?
