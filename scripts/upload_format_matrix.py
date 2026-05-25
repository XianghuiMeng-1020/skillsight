"""Comprehensive upload-format matrix.

Generates a *valid minimal* file for every extension we claim to support,
uploads it through /bff/student/documents/upload, and reports:
  - HTTP status
  - chunks_created
  - media_type
  - parse error / refusal hint if any

Reads SUPPORTED_EXTENSIONS from backend/app/parsers_multimodal.py so that the
test stays in sync with what the server claims to support.
"""
from __future__ import annotations

import csv
import io
import json
import os
import struct
import sys
import time
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import requests

PROXIES = {"http": None, "https": None}

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.parsers_multimodal import SUPPORTED_EXTENSIONS  # noqa: E402


# ---------------------------------------------------------------------------
# Tiny synthetic-file factory: returns realistic minimal bytes per extension.
# ---------------------------------------------------------------------------
def _png_1x1() -> bytes:
    # Minimal valid 1x1 PNG (red pixel)
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000"
        "0090775388000000017352474200aece1ce90000000c4944415478da"
        "63f8cfc0c000040001017f8aa9bb0000000049454e44ae426082"
    )


def _gif_1x1() -> bytes:
    return bytes.fromhex(
        "47494638396101000100800100ff0000ffffff21f90401000000002c"
        "00000000010001000002024401003b"
    )


def _bmp_1x1() -> bytes:
    return bytes.fromhex(
        "424d3a0000000000000036000000280000000100000001000000"
        "01001800000000000400000000000000000000000000000000"
        "0000ffffff00"
    )


def _ico_1x1() -> bytes:
    # 1x1 ICO wrapping the same PNG
    png = _png_1x1()
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 1, 1, 0, 0, 1, 32, len(png), 22)
    return header + entry + png


def _jpg_1x1() -> bytes:
    # Tiny JPEG (1x1 white). Crafted minimal JFIF.
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300080606"
        "07060805070707090908090a0c130c0a0b0b0c1916140d131d1a1f1f"
        "1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38"
        "323c2e333432ffdb0043010909090c0b0c180d0d1832211c213232"
        "32323232323232323232323232323232323232323232323232323232"
        "32323232323232323232323232323232323232323232323232ffc000"
        "11080001000103012200021101031101ffc4001f0000010501010101"
        "01010000000000000000010203040506070809000affc400b510000"
        "20103030204030505040400000177010203041105122131410613516"
        "107227114328191a1082309233152f0a3b1c12c2d2e3f0162434e252"
        "f217186272a2a2828292a3536373839393a4344454647484955354556"
        "5758595a636465666768696a737475767778797a838485868788898a"
        "92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2"
        "c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1"
        "f2f3f4f5f6f7f8f9faffc4001f010003010101010101010101010000"
        "00000000010203040506070809000affc400b51100020102040403040"
        "705040400010277000102031104052131061241510761711322328108"
        "144291a1b1c109233352f0156272d10a162434e125f11718191a262728"
        "292a35363738393a434445464748494a535455565758595a6364656667"
        "68696a737475767778797a82838485868788898a92939495969798999a"
        "a2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3"
        "d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c"
        "03010002110311003f00fbd1ffd9"
    )


def _docx_minimal() -> bytes:
    """Minimal valid DOCX (zip + content_types + document.xml)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            (
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
                "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
                "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
                "<Default Extension='xml' ContentType='application/xml'/>"
                "<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>"
                "</Types>"
            ),
        )
        z.writestr(
            "_rels/.rels",
            (
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
                "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/>"
                "</Relationships>"
            ),
        )
        z.writestr(
            "word/document.xml",
            (
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                "<w:body><w:p><w:r><w:t>Hello SkillSight matrix test resume "
                "Python SQL React FastAPI machine learning Java </w:t></w:r></w:p></w:body>"
                "</w:document>"
            ),
        )
    return buf.getvalue()


def _xlsx_minimal() -> bytes:
    """Minimal valid XLSX with one sheet, two cells."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
            "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
            "<Default Extension='xml' ContentType='application/xml'/>"
            "<Override PartName='/xl/workbook.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'/>"
            "<Override PartName='/xl/worksheets/sheet1.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'/>"
            "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='xl/workbook.xml'/>"
            "</Relationships>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet' Target='worksheets/sheet1.xml'/>"
            "</Relationships>",
        )
        z.writestr(
            "xl/workbook.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' "
            "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>"
            "<sheets><sheet name='Sheet1' sheetId='1' r:id='rId1'/></sheets></workbook>",
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
            "<sheetData><row r='1'><c r='A1' t='inlineStr'><is><t>Skill</t></is></c>"
            "<c r='B1' t='inlineStr'><is><t>Level</t></is></c></row>"
            "<row r='2'><c r='A2' t='inlineStr'><is><t>Python</t></is></c>"
            "<c r='B2' t='inlineStr'><is><t>Advanced</t></is></c></row></sheetData></worksheet>",
        )
    return buf.getvalue()


def _pptx_minimal() -> bytes:
    """Minimal PPTX (one slide, one text run)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
            "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
            "<Default Extension='xml' ContentType='application/xml'/>"
            "<Override PartName='/ppt/presentation.xml' ContentType='application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'/>"
            "<Override PartName='/ppt/slides/slide1.xml' ContentType='application/vnd.openxmlformats-officedocument.presentationml.slide+xml'/>"
            "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='ppt/presentation.xml'/>"
            "</Relationships>",
        )
        z.writestr(
            "ppt/_rels/presentation.xml.rels",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide' Target='slides/slide1.xml'/>"
            "</Relationships>",
        )
        z.writestr(
            "ppt/presentation.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<p:presentation xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' "
            "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>"
            "<p:sldIdLst><p:sldId id='256' r:id='rId1'/></p:sldIdLst></p:presentation>",
        )
        z.writestr(
            "ppt/slides/slide1.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<p:sld xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main' "
            "xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'>"
            "<p:cSld><p:spTree><p:sp><p:txBody>"
            "<a:p><a:r><a:t>SkillSight matrix slide test</a:t></a:r></a:p>"
            "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
        )
    return buf.getvalue()


def _epub_minimal() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            "<?xml version='1.0'?><container version='1.0' "
            "xmlns='urn:oasis:names:tc:opendocument:xmlns:container'>"
            "<rootfiles><rootfile full-path='OEBPS/content.opf' "
            "media-type='application/oebps-package+xml'/></rootfiles></container>",
        )
        z.writestr(
            "OEBPS/content.opf",
            "<?xml version='1.0' encoding='UTF-8'?><package version='2.0' "
            "xmlns='http://www.idpf.org/2007/opf' unique-identifier='id'>"
            "<metadata xmlns:dc='http://purl.org/dc/elements/1.1/'>"
            "<dc:title>matrix</dc:title><dc:identifier id='id'>m1</dc:identifier>"
            "<dc:language>en</dc:language></metadata><manifest>"
            "<item id='c1' href='c1.xhtml' media-type='application/xhtml+xml'/></manifest>"
            "<spine><itemref idref='c1'/></spine></package>",
        )
        z.writestr(
            "OEBPS/c1.xhtml",
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
            "<p>SkillSight matrix test ebook content python sql data analysis</p>"
            "</body></html>",
        )
    return buf.getvalue()


def _ipynb_minimal() -> bytes:
    notebook = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# SkillSight test\n", "Python data project\n"]},
            {"cell_type": "code", "execution_count": 1, "metadata": {}, "outputs": [],
             "source": ["import pandas as pd\n", "df = pd.read_csv('a.csv')\n", "print(df.head())\n"]},
        ],
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    return json.dumps(notebook).encode("utf-8")


def _zip_with_resume() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("resume.md", "# Jane Doe\n\n- Python\n- SQL\n- React\n- AWS\n- Communication skills\n")
        z.writestr("project.txt", "Built recommendation engine in Python and Spark.\n")
    return buf.getvalue()


SVG_BYTES = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
    b"<rect width='10' height='10' fill='red'/>"
    b"<text x='0' y='8'>SkillSight</text></svg>"
)

LATEX_BYTES = (
    b"\\documentclass{article}\n"
    b"\\begin{document}\n"
    b"SkillSight matrix test resume. Python, SQL, machine learning, "
    b"React, FastAPI, AWS, communication. Built recommendation system.\n"
    b"\\end{document}\n"
)

RTF_BYTES = (
    b"{\\rtf1\\ansi\\deff0\n"
    b"{\\fonttbl {\\f0 Helvetica;}}\n"
    b"\\f0\\fs24 SkillSight matrix RTF resume. Python, SQL, React, AWS, "
    b"communication, leadership.\\par\n"
    b"}"
)


def _resume_text(label: str) -> bytes:
    text = (
        f"# Jane Doe — SkillSight matrix [{label}]\n\n"
        "- Python (advanced)\n- SQL (advanced)\n- React, TypeScript, FastAPI\n"
        "- Built recommendation engine using PyTorch and AWS Sagemaker\n"
        "- Strong communication & leadership\n"
        "Education: BSc Computer Science, HKU 2024\n"
    )
    return text.encode("utf-8")


def _csv_bytes() -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["skill", "level", "evidence"])
    w.writerow(["Python", "advanced", "5 years"])
    w.writerow(["SQL", "advanced", "ETL pipelines"])
    w.writerow(["React", "intermediate", "Frontend dashboards"])
    return buf.getvalue().encode("utf-8")


def _odt_minimal() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr(
            "META-INF/manifest.xml",
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<manifest:manifest xmlns:manifest='urn:oasis:names:tc:opendocument:xmlns:manifest:1.0'>"
            "<manifest:file-entry manifest:full-path='/' manifest:media-type='application/vnd.oasis.opendocument.text'/>"
            "<manifest:file-entry manifest:full-path='content.xml' manifest:media-type='text/xml'/>"
            "</manifest:manifest>",
        )
        z.writestr(
            "content.xml",
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<office:document-content xmlns:office='urn:oasis:names:tc:opendocument:xmlns:office:1.0' "
            "xmlns:text='urn:oasis:names:tc:opendocument:xmlns:text:1.0'>"
            "<office:body><office:text>"
            "<text:p>SkillSight matrix ODT resume. Python SQL React AWS.</text:p>"
            "</office:text></office:body></office:document-content>",
        )
    return buf.getvalue()


def _pdf_minimal_text() -> bytes:
    """Minimal one-page PDF whose content stream emits real text."""
    text_stream = (
        b"BT\n/F1 12 Tf\n72 720 Td\n"
        b"(SkillSight matrix PDF resume. Python SQL React AWS communication.) Tj\n"
        b"ET\n"
    )
    objs = []
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    stream_obj = b"4 0 obj\n<< /Length %d >>\nstream\n" % len(text_stream) + text_stream + b"endstream\nendobj\n"
    objs.append(stream_obj)
    objs.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    out = b"%PDF-1.4\n"
    offsets = []
    for o in objs:
        offsets.append(len(out))
        out += o
    xref_pos = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
    out += str(xref_pos).encode() + b"\n%%EOF"
    return out


def make_payload(ext: str) -> Tuple[Optional[bytes], str]:
    """Return (bytes, mime) for the given extension or (None, '') to skip.

    None signals "we deliberately skip this extension in the matrix because
    it is media that requires a multi-MB realistic asset (mp4 / mov / mp3 /
    flac etc.). Those are validated separately in the manual demo flow."
    """
    e = ext.lower()
    if e in (".txt", ".md", ".markdown", ".mdx", ".log", ".tex", ".latex", ".diff", ".patch"):
        return _resume_text(e), "text/plain"
    if e == ".rtf":
        return RTF_BYTES, "application/rtf"
    if e == ".pdf":
        return _pdf_minimal_text(), "application/pdf"
    if e == ".docx":
        return _docx_minimal(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if e == ".doc":
        # Legacy .doc requires antiword/textract; we still try the wrapper file
        return _docx_minimal(), "application/msword"
    if e == ".pptx":
        return _pptx_minimal(), "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if e == ".ppt":
        return _pptx_minimal(), "application/vnd.ms-powerpoint"
    if e == ".odt":
        return _odt_minimal(), "application/vnd.oasis.opendocument.text"
    if e == ".epub":
        return _epub_minimal(), "application/epub+zip"
    if e == ".zip":
        return _zip_with_resume(), "application/zip"
    if e == ".xlsx":
        return _xlsx_minimal(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if e == ".xls":
        return _xlsx_minimal(), "application/vnd.ms-excel"
    if e == ".csv":
        return _csv_bytes(), "text/csv"
    if e in (".jpg", ".jpeg"):
        return _jpg_1x1(), "image/jpeg"
    if e == ".png":
        return _png_1x1(), "image/png"
    if e == ".webp":
        # Tiny lossless WEBP
        return bytes.fromhex(
            "524946462e000000574542505650384c220000002f00000010071011d2"
            "0c0e88a0a37ec0e807c1c2c1ffffffffffffffffffffffffffffffffff"
            "ffff7f"
        ), "image/webp"
    if e == ".gif":
        return _gif_1x1(), "image/gif"
    if e == ".bmp":
        return _bmp_1x1(), "image/bmp"
    if e in (".tiff", ".tif"):
        # Tiny grayscale TIFF
        return bytes.fromhex(
            "49492a0008000000080000010300010000000100000001010300010000"
            "0001000000020103000100000008000000030103000100000001000000"
            "06010300010000000100000011010400010000004600000016010300"
            "010000000100000017010400010000000100000000000000ff"
        ), "image/tiff"
    if e == ".svg":
        return SVG_BYTES, "image/svg+xml"
    if e == ".ico":
        return _ico_1x1(), "image/x-icon"
    if e in (".heic", ".heif"):
        return None, ""  # skip — needs a full HEIC asset and libheif
    if e == ".ipynb":
        return _ipynb_minimal(), "application/x-ipynb+json"
    if e in (".py", ".pyw", ".pyi"):
        return b"def hello():\n    print('SkillSight matrix python sample')\n", "text/x-python"
    if e in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        return b"const skills = ['python','sql','react'];\nconsole.log(skills);\n", "application/javascript"
    if e == ".vue":
        return b"<template><div>hello</div></template>", "text/x-vue"
    if e == ".svelte":
        return b"<script>let n=0</script><h1>{n}</h1>", "text/x-svelte"
    if e in (".html", ".htm"):
        return b"<html><body><p>SkillSight matrix html resume python sql</p></body></html>", "text/html"
    if e in (".css", ".scss", ".sass", ".less"):
        return b".x{color:red}", "text/css"
    if e in (".java",):
        return b"public class A{public static void main(String[] a){}}", "text/x-java"
    if e in (".cpp", ".cc", ".cxx", ".c", ".h", ".hpp"):
        return b"#include<stdio.h>\nint main(){return 0;}", "text/x-c"
    if e in (".cs",):
        return b"class A{static void Main(){}}", "text/plain"
    if e in (".go",):
        return b"package main\nfunc main(){}", "text/x-go"
    if e in (".rs",):
        return b"fn main(){}", "text/x-rust"
    if e in (".rb",):
        return b"puts 'hi'", "text/x-ruby"
    if e in (".php",):
        return b"<?php echo 'hi'; ?>", "application/x-php"
    if e in (".swift",):
        return b"print(\"hi\")", "text/x-swift"
    if e in (".kt", ".kts"):
        return b"fun main(){println(\"hi\")}", "text/x-kotlin"
    if e in (".scala",):
        return b"object A{def main(args:Array[String]){}}", "text/x-scala"
    if e in (".r", ".R"):
        return b"x <- 1:5\nprint(x)\n", "text/x-r"
    if e in (".m", ".mm"):
        return b"int main(){return 0;}", "text/plain"
    if e in (".sh", ".bash", ".zsh", ".fish"):
        return b"#!/bin/bash\necho hi\n", "application/x-sh"
    if e in (".ps1", ".bat", ".cmd"):
        return b"echo hi\r\n", "text/plain"
    if e == ".json":
        return b'{"name":"jane","skills":["python","sql","react"]}', "application/json"
    if e in (".yaml", ".yml"):
        return b"name: jane\nskills:\n  - python\n  - sql\n", "application/x-yaml"
    if e == ".xml":
        return b"<?xml version='1.0'?><skills><skill>python</skill></skills>", "application/xml"
    if e == ".toml":
        return b'[skills]\npython = "advanced"\n', "application/toml"
    if e in (".ini", ".cfg", ".conf"):
        return b"[default]\nkey=value\n", "text/plain"
    if e == ".env":
        return b"SKILLSIGHT=ok\n", "text/plain"
    if e == ".sql":
        return b"select * from users where active = true;", "application/sql"
    if e == ".lua":
        return b"print('hi')", "text/x-lua"
    if e in (".pl", ".pm"):
        return b"#!/usr/bin/perl\nprint 'hi';", "text/x-perl"
    if e in (".ex", ".exs"):
        return b"IO.puts \"hi\"", "text/x-elixir"
    if e in (".erl", ".hrl"):
        return b"-module(a).\n-export([go/0]).\ngo()->ok.", "text/x-erlang"
    if e in (".clj", ".cljs"):
        return b"(println \"hi\")", "text/x-clojure"
    if e in (".hs", ".lhs"):
        return b"main = putStrLn \"hi\"", "text/x-haskell"
    if e == ".elm":
        return b"main = text \"hi\"", "text/x-elm"
    if e == ".dart":
        return b"void main(){print('hi');}", "text/x-dart"
    if e in (".groovy", ".gradle"):
        return b"println 'hi'", "text/x-groovy"
    if e == ".tf":
        return b"resource \"aws_s3_bucket\" \"b\" {}", "text/plain"
    if e == ".proto":
        return b"syntax='proto3';message A{}", "text/plain"
    if e in (".graphql", ".gql"):
        return b"type Query{ ping: String }", "application/graphql"
    # Audio / video — skipped; need full real assets.
    if e in (".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".wmv",
             ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"):
        return None, ""
    return None, ""


# ---------------------------------------------------------------------------
def main() -> int:
    base = os.getenv("SKILLSIGHT_API", "http://localhost:8001")
    out_path = ROOT / "reports" / "upload_format_matrix.json"
    out_path.parent.mkdir(exist_ok=True)

    # Login once
    uid = f"format_matrix_{int(time.time())}"
    r = requests.post(
        f"{base}/auth/dev_login",
        json={"subject_id": uid, "role": "student", "ttl_s": 3600},
        timeout=15, proxies=PROXIES,
    )
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['token']}"}

    rows = []
    pass_cnt = fail_cnt = skip_cnt = 0
    print(f"{'EXT':<12} {'CLAIM':<14} STATUS  CHUNKS  MEDIA          NOTE")
    print("-" * 100)
    for ext, claim in sorted(SUPPORTED_EXTENSIONS.items()):
        payload, mime = make_payload(ext)
        if payload is None:
            print(f"{ext:<12} {claim:<14}    -      -    {'(media skip)':<14} requires real asset")
            rows.append({"ext": ext, "claim": claim, "status": None, "skipped": True})
            skip_cnt += 1
            continue
        files = {"file": (f"matrix{ext}", payload, mime)}
        data = {"purpose": "skill_assessment", "scope": "full"}
        try:
            resp = requests.post(
                f"{base}/bff/student/documents/upload",
                headers=h, files=files, data=data,
                timeout=60, proxies=PROXIES,
            )
        except Exception as exc:
            print(f"{ext:<12} {claim:<14} EXC     -    -              {exc}")
            rows.append({"ext": ext, "claim": claim, "status": "exc", "error": str(exc)[:120]})
            fail_cnt += 1
            continue
        ok = resp.status_code == 200
        body = {}
        try:
            body = resp.json()
        except Exception:
            body = {"_text": resp.text[:200]}
        chunks = body.get("chunks_created", "-")
        media = body.get("media_type", "-")
        if ok and chunks not in (0, "-", None):
            pass_cnt += 1
            note = ""
        else:
            fail_cnt += 1
            note = body.get("detail") or body.get("_text") or ""
            note = (note if isinstance(note, str) else json.dumps(note))[:80]
        print(f"{ext:<12} {claim:<14} {resp.status_code:<6}  {str(chunks):<6}  {str(media):<14} {note}")
        rows.append({
            "ext": ext, "claim": claim, "status": resp.status_code,
            "chunks": chunks, "media_type": media,
            "ok": ok and chunks not in (0, "-"),
            "note": note,
        })

    print("\nTotal:", len(rows), "pass:", pass_cnt, "fail:", fail_cnt, "skip:", skip_cnt)
    out_path.write_text(json.dumps({"rows": rows, "pass": pass_cnt, "fail": fail_cnt,
                                    "skip": skip_cnt}, indent=2))
    print(f"Wrote {out_path}")
    return 0 if fail_cnt == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
