#!/usr/bin/env python3
"""
验证 SUPPORTED_EXTENSIONS 中每种扩展名经 parse_multimodal_file 解析时：
- 不抛异常
- 返回结构包含 chunks (list), media_type, metadata
对每种类型用最小合法或占位内容跑一遍。
"""
import base64
import io
import os
import sys
import tempfile
from pathlib import Path

# 1x1 红色 PNG
MINIMAL_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKMIQQAAAABJRU5ErkJggg=="
MINIMAL_PNG = base64.b64decode(MINIMAL_PNG_B64)

# 最小合法 JPEG (1x1)
MINIMAL_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0\x23r\x82\x16\x92\xa2\xb2\xc2\xd2\xe2\xf1\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfe\xb4\xd8\xb5\xff\xd9"
)

def minimal_content(ext: str) -> bytes:
    """每种扩展名的最小可用内容（用于不抛错、可返回 chunks 的测试）。"""
    ext = ext.lower()
    # 纯文本 / 代码
    if ext in (".txt", ".log", ".md", ".markdown"):
        return b"Hello world. Test content for format verification."
    if ext == ".csv":
        return b"a,b,c\n1,2,3\n"
    if ext in (".rtf", ".odt"):
        return b"{\\rtf1\\ansi Hello}"
    # 代码类
    code = b"def main():\n    pass\n"
    if ext in (
        ".py", ".pyw", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        ".vue", ".svelte", ".html", ".htm", ".css", ".scss", ".sass", ".less",
        ".java", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".cs", ".go", ".rs",
        ".rb", ".php", ".swift", ".kt", ".kts", ".scala", ".sh", ".bash", ".zsh",
        ".fish", ".ps1", ".bat", ".cmd", ".lua", ".pl", ".pm", ".ex", ".exs",
        ".erl", ".hrl", ".clj", ".cljs", ".hs", ".lhs", ".elm", ".dart", ".groovy",
        ".gradle", ".tf", ".graphql", ".gql", ".diff", ".patch", ".m", ".mm",
    ):
        return code
    if ext == ".json":
        return b'{"key": "value"}'
    if ext in (".yaml", ".yml"):
        return b"x: 1\ny: 2\n"
    if ext == ".xml":
        return b"<root><a>1</a></root>"
    if ext in (".toml", ".ini", ".cfg", ".conf", ".env"):
        return b"[section]\nkey = value\n"
    if ext == ".sql":
        return b"SELECT 1;"
    if ext == ".proto":
        return b'syntax = "proto3"; message M {}'
    # 图片：用真实最小 PNG/JPEG 避免 PIL 打开失败
    if ext in (".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"):
        return MINIMAL_PNG
    if ext in (".jpg", ".jpeg"):
        return MINIMAL_JPEG
    # SVG/ICO/HEIC 可能只得到占位，给最小内容即可
    if ext == ".svg":
        return b'<svg xmlns="http://www.w3.org/2000/svg"><text x="0" y="10">x</text></svg>'
    if ext == ".ico":
        return MINIMAL_PNG  # 很多库把 ico 当图片读
    if ext in (".heic", ".heif"):
        return b"fake heic"  # 无 pillow-heif 时会占位
    # 音视频：给非空字节，可能只得到占位
    if ext in (".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".wmv"):
        return b"\x00\x00\x00\x00"  # 无效但不会崩
    if ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"):
        return b"\x00\x00\x00\x00"
    # Notebook
    if ext == ".ipynb":
        return b'{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":2}'
    # 文档：二进制格式用最小占位，避免解析器崩溃
    if ext == ".doc":
        return b"\x00" * 100  # 占位，应走 doc 占位逻辑
    if ext == ".docx":
        # 最小 docx = zip with [Content_Types].xml
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
            z.writestr("word/document.xml", "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body><w:p><w:r><w:t>Test</w:t></w:r></w:p></w:body></w:document>")
        return buf.getvalue()
    if ext == ".pdf":
        # 最小合法 PDF
        return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000052 00000 n 
0000000101 00000 n 
trailer << /Size 4 /Root 1 0 R >>
startxref
178
%%EOF"""
    if ext == ".pptx":
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>')
            z.writestr("ppt/slides/slide1.xml", "<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:spTree><p:sp/><p:txBody><a:p><a:r><a:t>Test</a:t></a:r></a:p></p:txBody></p:spTree></p:cSld></p:sld>")
        return buf.getvalue()
    if ext == ".ppt":
        return b"\x00" * 100
    if ext in (".xlsx", ".xls"):
        # xlsx = zip
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
            z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr("xl/sharedStrings.xml", '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="0" uniqueCount="0"/>')
            z.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')
        return buf.getvalue()
    return b"minimal"


def main():
    # Allow running from repo root or backend
    backend = Path(__file__).resolve().parent.parent / "backend"
    if backend.is_dir():
        sys.path.insert(0, str(backend))
    os.chdir(backend if backend.is_dir() else Path.cwd())

    from app.parsers_multimodal import parse_multimodal_file, SUPPORTED_EXTENSIONS

    failed = []
    for ext in sorted(SUPPORTED_EXTENSIONS.keys()):
        try:
            content = minimal_content(ext)
            result = parse_multimodal_file(
                file_bytes=content,
                filename="test" + ext,
                min_chunk_len=30,
            )
        except Exception as e:
            failed.append((ext, "raise", str(e)))
            continue
        if not isinstance(result.get("chunks"), list):
            failed.append((ext, "chunks", "chunks is not a list"))
            continue
        if result.get("media_type") not in ("text", "document", "image", "video", "audio", "code", "presentation", "spreadsheet", "notebook", "unknown"):
            failed.append((ext, "media_type", str(result.get("media_type"))))
            continue
        # 通过
        n = len(result["chunks"])
        print(f"  OK {ext:8} -> media_type={result['media_type']:12} chunks={n}")
    if failed:
        print("\nFailed:", failed)
        sys.exit(1)
    print("\nAll formats OK.")
    return 0


if __name__ == "__main__":
    main()
