"""Non-executing source checks for user project files."""
import ast
import json
from pathlib import PurePosixPath

MAX_FILES = 100
MAX_TOTAL_BYTES = 2 * 1024 * 1024


def check_project_files(files):
    """Check supported text formats without importing or executing user code."""
    results = []
    total = 0
    selected = files[:MAX_FILES]
    for item in selected:
        path = str(item.get("path", ""))
        content = str(item.get("content", ""))
        size = len(content.encode("utf-8"))
        total += size
        if total > MAX_TOTAL_BYTES:
            results.append({"path": path, "status": "skipped", "message": "تجاوز الفحص حد الحجم الآمن البالغ 2 ميغابايت"})
            break
        suffix = PurePosixPath(path).suffix.lower()
        try:
            if suffix == ".py":
                ast.parse(content, filename=path)
                results.append({"path": path, "status": "passed", "message": "صياغة Python سليمة"})
            elif suffix == ".json":
                json.loads(content)
                results.append({"path": path, "status": "passed", "message": "بنية JSON سليمة"})
            elif suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
                results.append({"path": path, "status": "not_checked", "message": "لم يتم تشغيل أو تحليل JavaScript/TypeScript؛ يلزم مدقق مخصص"})
            elif suffix in {".html", ".htm", ".css", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".sh"}:
                results.append({"path": path, "status": "not_checked", "message": "تم التعرف على الملف؛ لم يُشغّل محتواه"})
            else:
                results.append({"path": path, "status": "not_checked", "message": "نوع الملف غير مدعوم في الفحص الآمن"})
        except (SyntaxError, ValueError, json.JSONDecodeError) as exc:
            line = getattr(exc, "lineno", None)
            detail = f" في السطر {line}" if line else ""
            results.append({"path": path, "status": "failed", "message": f"خطأ في الصياغة{detail}: {str(exc).splitlines()[0][:240]}"})
    if len(files) > MAX_FILES:
        results.append({"path": "", "status": "skipped", "message": f"تم فحص أول {MAX_FILES} ملفاً فقط"})
    counts = {key: sum(1 for r in results if r["status"] == key) for key in ("passed", "failed", "not_checked", "skipped")}
    return {"results": results, "counts": counts, "executed": False,
            "summary": f"نجح {counts['passed']}، أخفق {counts['failed']}، لم يُفحص {counts['not_checked']}، تم تخطي {counts['skipped']}"}
