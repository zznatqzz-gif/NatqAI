from pathlib import Path
import csv
import json
import xml.etree.ElementTree as ET

from fastapi import HTTPException

MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_TEXT_LENGTH = 50000


def read_file(file_path: str) -> dict:
    path = Path(file_path)

    if not path.is_file():
        raise HTTPException(404, "الملف غير موجود")

    if path.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(413, "حجم الملف يتجاوز الحد المسموح")

    ext = path.suffix.lower()

    try:
        if ext in (".txt", ".md", ".py", ".js", ".html", ".css",
                   ".sql", ".sh", ".yaml", ".yml", ".ini", ".log"):
            content = path.read_text(encoding="utf-8-sig")
            return {"type": "text", "content": content[:MAX_TEXT_LENGTH]}

        if ext == ".json":
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return {
                "type": "json",
                "content": json.dumps(data, ensure_ascii=False)[:MAX_TEXT_LENGTH]
            }

        if ext == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))[:500]
            return {"type": "csv", "rows": rows}

        if ext == ".xml":
            root = ET.parse(path).getroot()
            return {
                "type": "xml",
                "root": root.tag,
                "content": ET.tostring(root, encoding="unicode")[:MAX_TEXT_LENGTH]
            }

        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages[:30]:
                pages.append(page.extract_text() or "")
            return {
                "type": "pdf",
                "pages": len(reader.pages),
                "content": "\n".join(pages)[:MAX_TEXT_LENGTH]
            }

        if ext == ".docx":
            from docx import Document
            doc = Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text]
            return {
                "type": "docx",
                "content": "\n".join(paragraphs)[:MAX_TEXT_LENGTH]
            }

        if ext == ".xlsx":
            from openpyxl import load_workbook
            book = load_workbook(str(path), read_only=True, data_only=True)
            sheets = {}
            for sheet in book.worksheets[:20]:
                rows = []
                for row in sheet.iter_rows(max_row=200, max_col=30, values_only=True):
                    rows.append([str(v) if v is not None else "" for v in row])
                sheets[sheet.title] = rows
            book.close()
            return {"type": "xlsx", "sheets": sheets}

        if ext == ".pptx":
            from pptx import Presentation
            presentation = Presentation(str(path))
            slides = []
            for index, slide in enumerate(presentation.slides):
                if index >= 50:
                    break
                texts = [
                    shape.text for shape in slide.shapes
                    if getattr(shape, "has_text_frame", False) and shape.text.strip()
                ]
                slides.append("\n".join(texts))
            return {
                "type": "pptx",
                "slides": len(presentation.slides),
                "content": slides
            }

        if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
            from PIL import Image
            with Image.open(path) as img:
                return {
                    "type": "image",
                    "format": img.format,
                    "width": img.width,
                    "height": img.height,
                    "mode": img.mode
                }

        if ext == ".zip":
            from .archive_reader import inspect_archive
            return {"type": "zip", **inspect_archive(str(path))}

        if ext == ".apk":
            from .archive_reader import inspect_apk
            return inspect_apk(str(path))

        raise HTTPException(415, "صيغة الملف غير مدعومة حالياً")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            422,
            f"تعذر قراءة الملف: {type(exc).__name__}"
        ) from exc
