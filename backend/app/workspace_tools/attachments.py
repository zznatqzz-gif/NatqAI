from pathlib import Path
from fastapi import HTTPException, UploadFile
import os
import re
import uuid

MAX_UPLOAD_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

ATTACHMENTS_ROOT = (
    Path.home() / "downloads" / "natqai_workspace" / "attachments"
)


async def save_attachment(user_id: int, chat_id: int, upload: UploadFile) -> dict:
    if user_id < 1 or chat_id < 1:
        raise HTTPException(400, "معرّف غير صالح")

    original_name = (upload.filename or "file").replace("\\", "/").split("/")[-1]
    original_name = "".join(
        c for c in original_name if c.isprintable() and c not in "/\\"
    ).strip()

    if not original_name:
        original_name = "file"

    original_name = original_name[:180]

    suffix = Path(original_name).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
        suffix = ""

    root = ATTACHMENTS_ROOT
    root.mkdir(parents=True, exist_ok=True, mode=0o700)

    if root.is_symlink():
        raise HTTPException(400, "مساحة المرفقات غير آمنة")

    user_dir = root / str(user_id)
    chat_dir = user_dir / str(chat_id)

    for directory in (user_dir, chat_dir):
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink():
            raise HTTPException(400, "مسار المرفقات غير آمن")

    resolved_root = root.resolve()
    resolved_dir = chat_dir.resolve()

    if not resolved_dir.is_relative_to(resolved_root):
        raise HTTPException(400, "مسار التخزين غير صالح")

    stored_name = uuid.uuid4().hex + suffix
    destination = chat_dir / stored_name

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(destination, flags, 0o600)

    size = 0

    try:
        with os.fdopen(fd, "wb") as output:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break

                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    raise HTTPException(413, "حجم الملف يتجاوز 20 ميغابايت")

                output.write(chunk)

        if size == 0:
            raise HTTPException(400, "الملف فارغ")

        return {
            "original_name": original_name,
            "stored_name": stored_name,
            "mime_type": (upload.content_type or "application/octet-stream")[:120],
            "size": size,
        }

    except Exception:
        destination.unlink(missing_ok=True)
        raise
