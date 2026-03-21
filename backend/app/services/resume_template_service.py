"""
Resume template service: fill a DOCX template with resume content and return bytes.
Uses python-docx to open template and replace placeholders (e.g. {{ RESUME_CONTENT }}).
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

_log = logging.getLogger(__name__)

# Base dir for template files (relative to backend/)
TEMPLATES_BASE = Path(__file__).resolve().parents[2] / "data" / "templates"


def _get_template_path(template_file: Optional[str]) -> Path:
    """Resolve template file path; template_file is relative to data/templates or a filename.
    Rejects path traversal (e.g. ../) to prevent reading files outside templates dir.
    """
    if not template_file or not template_file.strip():
        raise FileNotFoundError("template_not_found")
    name = template_file.strip().lstrip("/")
    base_resolved = TEMPLATES_BASE.resolve()
    path = (TEMPLATES_BASE / name).resolve()
    if not path.exists():
        path = (TEMPLATES_BASE / (name + ".docx" if not name.lower().endswith(".docx") else name)).resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("template_not_found")
    # Prevent path traversal: path must be under TEMPLATES_BASE
    try:
        if not path.is_relative_to(base_resolved):
            raise FileNotFoundError("template_not_found")
    except AttributeError:
        # Python < 3.9: path must equal base or have base as parent
        if path != base_resolved and base_resolved not in path.parents:
            raise FileNotFoundError("template_not_found")
    return path


def _replace_in_paragraph(paragraph, replacements: Dict[str, str]) -> None:
    """Replace placeholders in a paragraph. Placeholders are {{ KEY }}."""
    if not paragraph.text.strip():
        return
    full = paragraph.text
    new_text = full
    for key, value in replacements.items():
        placeholder = "{{ " + key + " }}"
        if placeholder in new_text:
            new_text = new_text.replace(placeholder, value or "")
    if new_text == full:
        return
    # Clear and set new text (preserve first run to keep style if possible)
    for run in paragraph.runs:
        run.text = ""
    if paragraph.runs:
        paragraph.runs[0].text = new_text
    else:
        paragraph.add_run(new_text)


def _replace_in_document(doc, replacements: Dict[str, str]) -> None:
    """Replace placeholders in all paragraphs and table cells."""
    for para in doc.paragraphs:
        _replace_in_paragraph(para, replacements)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _replace_in_paragraph(para, replacements)


def apply_template(
    db: Session,
    review_id: str,
    template_id: str,
    resume_content: str,
    template_file: Optional[str] = None,
) -> bytes:
    """
    Load the DOCX template for the given template_id (or use template_file),
    replace {{ RESUME_CONTENT }} (and optionally other placeholders) with resume_content,
    return the document as bytes.

    If template_file is not provided, looks up resume_templates.template_file by template_id.
    """
    if not template_file:
        if template_id.startswith("__"):
            template_file = template_id.lstrip("_") + ".docx"
        else:
            row = db.execute(
                text("SELECT template_file, name FROM resume_templates WHERE template_id = :tid AND is_active = TRUE LIMIT 1"),
                {"tid": template_id},
            ).mappings().first()
            if row:
                template_file = row.get("template_file") or ""
            else:
                raise FileNotFoundError("template_not_found")

    path = _get_template_path(template_file)
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError("python-docx is required for template export")

    doc = Document(str(path))
    replacements = {
        "RESUME_CONTENT": resume_content or "",
        "CONTENT": resume_content or "",
    }
    _replace_in_document(doc, replacements)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()
