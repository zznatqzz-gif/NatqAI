from pathlib import Path
from fastapi import HTTPException
from .security import safe_project_path

MAX_FILE_SIZE = 512 * 1024
MAX_FILES = 500


def create_project_dir(user_id: int, project_id: int) -> Path:
    path = safe_project_path(user_id, project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text_file(user_id: int, project_id: int, relative_path: str, content: str) -> dict:
    if not relative_path or relative_path.strip() in (".", ".."):
        raise HTTPException(400, "اسم الملف غير صالح")

    if len(content.encode("utf-8")) > MAX_FILE_SIZE:
        raise HTTPException(413, "حجم الملف يتجاوز الحد المسموح")

    path = safe_project_path(user_id, project_id, relative_path)

    if not path.name or path.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
        raise HTTPException(400, "نوع الملف أو اسمه غير مسموح")

    if path.exists() and not path.is_file():
        raise HTTPException(400, "المسار ليس ملفاً")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return {
        "path": relative_path,
        "size": path.stat().st_size,
        "status": "saved"
    }


def read_text_file(user_id: int, project_id: int, relative_path: str) -> dict:
    path = safe_project_path(user_id, project_id, relative_path)

    if not path.is_file():
        raise HTTPException(404, "الملف غير موجود")

    if path.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(413, "حجم الملف يتجاوز الحد المسموح")

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(415, "هذا ليس ملفاً نصياً") from exc

    return {"path": relative_path, "content": content}


def list_project_files(user_id: int, project_id: int) -> list:
    root = create_project_dir(user_id, project_id)
    results = []

    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_file():
            results.append({
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size
            })
            if len(results) >= MAX_FILES:
                break

    return results
