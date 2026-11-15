from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED
from fastapi import HTTPException
import subprocess

MAX_ARCHIVE_SIZE = 50 * 1024 * 1024
MAX_ENTRIES = 500
MAX_TOTAL_SIZE = 100 * 1024 * 1024
MAX_MEMBER_SIZE = 20 * 1024 * 1024


def inspect_archive(file_path: str) -> dict:
    path = Path(file_path)

    if not path.is_file():
        raise HTTPException(404, "الملف غير موجود")

    if path.stat().st_size > MAX_ARCHIVE_SIZE:
        raise HTTPException(413, "حجم الأرشيف يتجاوز الحد المسموح")

    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()

            if len(entries) > MAX_ENTRIES:
                raise HTTPException(413, "عدد الملفات داخل الأرشيف كبير جداً")

            total_size = 0
            results = []

            for item in entries:
                name = item.filename
                member = PurePosixPath(name)

                if (
                    member.is_absolute()
                    or ".." in member.parts
                    or "\\" in name
                    or "\x00" in name
                ):
                    raise HTTPException(400, "الأرشيف يحتوي على مسار غير آمن")

                if item.flag_bits & 1:
                    raise HTTPException(415, "الأرشيف يحتوي على ملفات مشفرة")

                if item.file_size > MAX_MEMBER_SIZE:
                    raise HTTPException(413, "أحد الملفات داخل الأرشيف كبير جداً")

                total_size += item.file_size
                if total_size > MAX_TOTAL_SIZE:
                    raise HTTPException(413, "الحجم الإجمالي للملفات كبير جداً")

                results.append({
                    "name": name,
                    "size": item.file_size,
                    "compressed_size": item.compress_size,
                    "directory": item.is_dir()
                })

            return {
                "archive": path.name,
                "files_count": len(results),
                "total_size": total_size,
                "files": results
            }

    except BadZipFile as exc:
        raise HTTPException(415, "الملف ليس أرشيف ZIP صالحاً") from exc


def inspect_apk(file_path: str) -> dict:
    path = Path(file_path)

    if path.suffix.lower() != ".apk":
        raise HTTPException(400, "امتداد الملف ليس APK")

    result = inspect_archive(str(path))
    result["type"] = "APK"
    result["package_info"] = None

    try:
        command = subprocess.run(
            ["aapt", "dump", "badging", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False
        )

        if command.returncode == 0:
            result["package_info"] = command.stdout[:20000]
        else:
            result["package_info_error"] = command.stderr[:2000]

    except (FileNotFoundError, subprocess.TimeoutExpired):
        result["package_info_error"] = "تعذر تشغيل aapt"

    try:
        signature = subprocess.run(
            ["apksigner", "verify", "--verbose", "--print-certs", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )
        result["signature"] = {
            "valid": signature.returncode == 0,
            "details": (signature.stdout or signature.stderr)[:10000]
        }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        result["signature"] = {
            "valid": None,
            "details": "تعذر إكمال فحص التوقيع"
        }

    return result
