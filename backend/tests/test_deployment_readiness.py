import tempfile
import unittest
from pathlib import Path
from app.deployment_readiness import deployment_readiness


class DeploymentReadinessTests(unittest.TestCase):
    def test_production_configuration_without_provider_connection_has_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "backend" / "Dockerfile").write_text("FROM python:3.12-slim")
            (root / "backend" / "railway.json").write_text("{}")
            result = deployment_readiness(
                environment="production", secret_key="x" * 40,
                cors_origins=("https://example.com",), database_path="/data/natqai.db",
                ai_base_url="https://api.example.com", ai_api_key="very-private-api-key", ai_model="model",
                project_root=root,
            )
        self.assertEqual(result["status"], "ready_with_warnings")
        self.assertFalse(result["ready_to_publish"])
        self.assertEqual(result["blockers"], 0)
        self.assertEqual(result["warnings"], 1)
        self.assertFalse(result["deployment_performed"])
        self.assertNotIn("very-private-api-key", str(result))
        self.assertNotIn("x" * 40, str(result))

    def test_development_defaults_are_blocked(self):
        result = deployment_readiness(
            environment="development", secret_key="development-only-change-me",
            cors_origins=("*",), database_path="./natqai.db",
            project_root="/missing-project-root",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertGreaterEqual(result["blockers"], 4)

    def test_railway_token_presence_does_not_claim_verified_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "backend" / "Dockerfile").write_text("FROM python:3.12-slim")
            (root / "backend" / "railway.json").write_text("{}")
            result = deployment_readiness(
                environment="production", secret_key="s" * 40,
                cors_origins=("https://example.com",), database_path="/data/natqai.db",
                ai_base_url="https://api.example.com", ai_api_key="private-token", ai_model="model",
                railway_token="configured-but-not-verified", project_root=root,
            )
        self.assertFalse(result["ready_to_publish"])
        self.assertTrue(result["railway_credential_configured"])
        self.assertFalse(result["railway_connection_verified"])
        railway_check = next(item for item in result["checks"] if item["key"] == "railway_connection")
        self.assertEqual(railway_check["status"], "warning")
        self.assertIn("not been validated", railway_check["message"])
        self.assertNotIn("configured-but-not-verified", str(result))
        self.assertNotIn("private-token", str(result))


if __name__ == "__main__":
    unittest.main()
