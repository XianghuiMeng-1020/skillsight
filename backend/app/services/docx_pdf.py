"""Optional DOCX → PDF conversion via LibreOffice/soffice (headless)."""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

_log = logging.getLogger(__name__)


def docx_bytes_to_pdf_bytes(docx_bytes: bytes) -> bytes | None:
    """
    Convert DOCX to PDF using LibreOffice if available on PATH.
    Returns None if soffice/libreoffice is not installed (caller should fall back to DOCX-only).
    """
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        _log.warning("docx_pdf: no soffice/libreoffice on PATH; PDF export skipped")
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="skillsight_pdf_") as tmp:
            tmp_path = Path(tmp)
            docx_path = tmp_path / "input.docx"
            docx_path.write_bytes(docx_bytes)
            # --headless --convert-to pdf --outdir
            cmd = [
                soffice,
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                str(tmp_path),
                str(docx_path),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                _log.warning("docx_pdf: soffice failed: %s %s", proc.stdout, proc.stderr)
                return None
            pdf_path = tmp_path / "input.pdf"
            if not pdf_path.is_file():
                _log.warning("docx_pdf: expected output missing at %s", pdf_path)
                return None
            return pdf_path.read_bytes()
    except Exception as e:
        _log.exception("docx_pdf: conversion error: %s", e)
        return None
