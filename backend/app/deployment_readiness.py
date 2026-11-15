"""Read-only deployment preflight checks. Never returns secret values."""
from pathlib import Path
from typing import Mapping


def deployment_readiness(
    *,
    environment: str,
    secret_key: str,
    cors_origins: tuple[str, ...],
    database_path: str,
    ai_base_url: str = "",
    ai_api_key: str = "",
    ai_model: str = "",
    railway_token: str = "",
    railway_connection_verified: bool = False,
    project_root: str | Path | None = None,
) -> dict:
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    checks = []

    def add(key: str, ok: bool, message: str, severity: str = "blocker"):
        checks.append({"key": key, "status": "passed" if ok else severity, "message": message})

    production = environment.strip().lower() == "production"
    add("environment", production, "Production mode is enabled." if production else "Set NATQAI_ENV=production before public deployment.")
    valid_secret = secret_key != "development-only-change-me" and len(secret_key) >= 32
    add("secret_key", valid_secret, "Application secret is configured." if valid_secret else "Set a unique NATQAI_SECRET_KEY with at least 32 characters.")
    valid_cors = bool(cors_origins) and "*" not in cors_origins
    add("cors", valid_cors, "CORS allowlist is configured." if valid_cors else "Configure explicit trusted origins in NATQAI_CORS_ORIGINS.")
    db = Path(database_path)
    persistent_path = str(db).startswith("/data/") or str(db).startswith("/var/lib/")
    add("database_path", persistent_path, "Database points to a persistent-volume path." if persistent_path else "Use a persistent volume path such as /data/natqai.db.")
    ai_ready = bool(ai_base_url and ai_api_key and ai_model)
    add("ai_provider", ai_ready, "AI provider settings are present." if ai_ready else "AI provider is not fully configured; set base URL, API key, and model.", "warning")
    token_present = bool(railway_token.strip()) or railway_connection_verified
    add(
        "railway_connection",
        railway_connection_verified,
        "Railway account connection was verified." if railway_connection_verified else (
            "A Railway credential is configured, but it has not been validated with Railway." if token_present
            else "Railway is not connected; connect it securely in the application before publishing."
        ),
        "warning",
    )
    dockerfile = root / "backend" / "Dockerfile"
    railway_config = root / "backend" / "railway.json"
    add("container_files", dockerfile.is_file() and railway_config.is_file(), "Container and Railway configuration files are present." if dockerfile.is_file() and railway_config.is_file() else "Dockerfile or Railway configuration is missing.")

    blockers = sum(item["status"] == "blocker" for item in checks)
    warnings = sum(item["status"] == "warning" for item in checks)
    return {
        "status": "blocked" if blockers else ("ready_with_warnings" if warnings else "ready"),
        "ready_to_publish": blockers == 0 and warnings == 0,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "deployment_performed": False,
        "railway_credential_configured": bool(railway_token.strip()),
        "railway_connection_verified": railway_connection_verified,
    }
