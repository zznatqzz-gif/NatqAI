from pathlib import Path
from fastapi import HTTPException

WORKSPACE_ROOT = Path.home() / "downloads" / "natqai_workspace"


def safe_project_path(user_id: int, project_id: int, relative_path: str = "") -> Path:
    if user_id < 1 or project_id < 1:
        raise HTTPException(400, "معرّف المشروع غير صالح")

    if WORKSPACE_ROOT.is_symlink():
        raise HTTPException(400, "مساحة العمل غير آمنة")

    root = WORKSPACE_ROOT.resolve()
    user_dir = root / str(user_id)
    base = user_dir / str(project_id)

    for directory in (user_dir, base):
        if directory.is_symlink():
            raise HTTPException(400, "الروابط الرمزية غير مسموحة")

    if "\x00" in relative_path or "\\" in relative_path:
        raise HTTPException(400, "المسار غير مسموح")

    candidate = Path(relative_path or ".")

    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(400, "المسار المطلوب غير مسموح")

    current = base
    for part in candidate.parts:
        if part == ".":
            continue
        current = current / part
        if current.is_symlink():
            raise HTTPException(400, "الروابط الرمزية غير مسموحة")

    resolved_base = base.resolve()
    resolved_path = (base / candidate).resolve()

    if not resolved_base.is_relative_to(root):
        raise HTTPException(400, "مساحة المشروع غير صالحة")

    if not resolved_path.is_relative_to(resolved_base):
        raise HTTPException(400, "لا يمكن الوصول خارج مساحة المشروع")

    return resolved_path
