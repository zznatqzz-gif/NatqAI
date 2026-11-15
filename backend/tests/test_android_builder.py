import io
import os
import zipfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from android_builder import worker
from android_builder.worker import app


def source_zip(extra=None):
    data = io.BytesIO()
    entries = {f"NatqAIAndroid/{name}": content for name, content in worker.TRUSTED_TEMPLATE_FILES.items()}
    entries["NatqAIAndroid/app/src/main/assets/www/index.html"] = "<h1>test</h1>"
    if extra:
        entries.update(extra)
    with zipfile.ZipFile(data, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return data.getvalue()


class AndroidBuilderTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"ANDROID_BUILDER_TOKEN": "test-builder-secret"})
        self.env.start()
        self.token_patch = patch.object(worker, "TOKEN", "test-builder-secret")
        self.token_patch.start()

    def tearDown(self):
        self.token_patch.stop()
        self.env.stop()
        self.client.close()


    def test_railway_healthcheck_uses_public_health_endpoint(self):
        import json
        config_path = Path(__file__).resolve().parents[1] / "android_builder" / "railway.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["deploy"]["healthcheckPath"], "/health")
        self.assertNotEqual(config["deploy"]["healthcheckPath"], "/ready")

    def test_health_is_public_liveness_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_ready_requires_valid_bearer_token(self):
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 401)
        response = self.client.get("/ready", headers={"Authorization": "Bearer wrong-token"})
        self.assertEqual(response.status_code, 401)

    def test_ready_rejects_missing_authentication_secret(self):
        with patch.object(worker, "TOKEN", ""):
            response = self.client.get("/ready", headers={"Authorization": "Bearer test-builder-secret"})
        self.assertEqual(response.status_code, 503)

    def test_ready_reports_missing_toolchain(self):
        with patch("android_builder.worker._toolchain_status", return_value=None):
            response = self.client.get("/ready", headers={"Authorization": "Bearer test-builder-secret"})
        self.assertEqual(response.status_code, 503)

    def test_ready_reports_verified_toolchain(self):
        expected = {"status": "ready", "gradle": "8.7", "java": "17", "android_sdk": "35"}
        with patch("android_builder.worker._toolchain_status", return_value=expected):
            response = self.client.get("/ready", headers={"Authorization": "Bearer test-builder-secret"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_oversized_http_request_is_rejected_before_multipart_parsing(self):
        oversized = b"x" * (worker.MAX_BUILD_REQUEST_BYTES + 1)
        response = self.client.post(
            "/build",
            headers={"Authorization": "Bearer test-builder-secret", "Content-Type": "application/octet-stream"},
            content=oversized,
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("Build request too large", response.text)

    def test_build_middleware_rejects_concurrent_build_before_parsing_upload(self):
        import asyncio
        middleware_type = worker.BuildRequestSizeLimitMiddleware
        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow_app(scope, receive, send):
            entered.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        async def invoke(middleware):
            messages = []
            async def send(message):
                messages.append(message)
            scope = {"type": "http", "path": "/build", "method": "POST", "headers": []}
            await middleware(scope, lambda: None, send)
            return messages

        async def scenario():
            middleware = middleware_type(slow_app, max_bytes=1024, max_concurrent_builds=1)
            first = asyncio.create_task(invoke(middleware))
            await entered.wait()
            second_messages = await invoke(middleware)
            self.assertEqual(second_messages[0]["status"], 429)
            self.assertIn((b"retry-after", b"5"), second_messages[0]["headers"])
            release.set()
            await first
            third_messages = await invoke(middleware)
            self.assertEqual(third_messages[0]["status"], 200)

        asyncio.run(scenario())

    def test_non_build_routes_are_not_affected_by_upload_limit(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_build_refuses_when_toolchain_is_not_ready(self):
        with patch("android_builder.worker._toolchain_status", return_value=None):
            response = self.client.post("/build", headers={"Authorization": "Bearer test-builder-secret"},
                files={"file": ("src.zip", source_zip(), "application/zip")})
        self.assertEqual(response.status_code, 503)

    def test_requires_builder_token(self):
        response = self.client.post("/build", files={"file": ("src.zip", source_zip(), "application/zip")})
        self.assertEqual(response.status_code, 401)

    def test_rejects_path_traversal(self):
        response = self.client.post("/build", headers={"Authorization": "Bearer test-builder-secret"},
            files={"file": ("src.zip", source_zip({"NatqAIAndroid/../../evil": "x"}), "application/zip")})
        self.assertEqual(response.status_code, 422)

    def test_rejects_modified_gradle_script(self):
        response = self.client.post("/build", headers={"Authorization": "Bearer test-builder-secret"},
            files={"file": ("src.zip", source_zip({"NatqAIAndroid/app/build.gradle": "plugins {}; Runtime.getRuntime().exec('id')"}), "application/zip")})
        self.assertEqual(response.status_code, 422)
        self.assertIn("Modified Android build template", response.text)

    def test_rejects_modified_manifest_or_activity(self):
        for path, content in (
            ("NatqAIAndroid/app/src/main/AndroidManifest.xml", "<manifest><uses-permission android:name='android.permission.READ_SMS'/></manifest>"),
            ("NatqAIAndroid/app/src/main/java/com/natqai/generated/MainActivity.java", "class MainActivity { static { evil(); } }"),
        ):
            with self.subTest(path=path):
                response = self.client.post("/build", headers={"Authorization": "Bearer test-builder-secret"},
                    files={"file": ("src.zip", source_zip({path: content}), "application/zip")})
                self.assertEqual(response.status_code, 422)

    def test_builds_and_returns_apk_from_worker(self):
        async def fake_gradle(root, env, log_path, request):
            apk = root / "app/build/outputs/apk/debug/app-debug.apk"
            apk.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(apk, "w") as built:
                built.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00" + b"x" * 64)
                built.writestr("classes.dex", b"dex\n035\0" + b"x" * 2048)
            return type("Result", (), {"returncode": 0})()
        with patch("android_builder.worker._toolchain_status", return_value={"status": "ready"}), \
             patch("android_builder.worker._verify_apk_signature"), \
             patch("android_builder.worker._run_gradle_build", side_effect=fake_gradle):
            response = self.client.post("/build", headers={"Authorization": "Bearer test-builder-secret"},
                files={"file": ("src.zip", source_zip(), "application/zip")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/vnd.android.package-archive")
        self.assertTrue(response.content.startswith(b"PK"))
        self.assertGreater(len(response.content), 1024)
        with zipfile.ZipFile(io.BytesIO(response.content)) as apk:
            self.assertIn("AndroidManifest.xml", apk.namelist())
            self.assertIn("classes.dex", apk.namelist())

    def test_rejects_unexpected_java_source(self):
        response = self.client.post("/build", headers={"Authorization": "Bearer test-builder-secret"},
            files={"file": ("src.zip", source_zip({
                "NatqAIAndroid/app/src/main/java/evil/Injected.java": "class Injected {}"
            }), "application/zip")})
        self.assertEqual(response.status_code, 422)

    def test_cleanup_file_response_removes_temp_directory_on_send_failure(self):
        import asyncio
        import tempfile
        from unittest.mock import AsyncMock
        with tempfile.TemporaryDirectory() as parent:
            cleanup_dir = Path(parent) / "build-temp"
            cleanup_dir.mkdir()
            apk = cleanup_dir / "app.apk"
            apk.write_bytes(b"apk")
            response = worker.CleanupFileResponse(apk, cleanup_dir=str(cleanup_dir))
            with patch("starlette.responses.FileResponse.__call__", new=AsyncMock(side_effect=RuntimeError("client disconnected"))):
                with self.assertRaises(RuntimeError):
                    asyncio.run(response({}, None, None))
            self.assertFalse(cleanup_dir.exists())

    def test_process_group_termination_sends_sigterm(self):
        import asyncio
        from unittest.mock import AsyncMock
        class FakeProcess:
            pid = 12345
            returncode = None
            async def wait(self):
                self.returncode = -15
                return self.returncode
        process = FakeProcess()
        with patch("android_builder.worker.os.killpg") as killpg:
            asyncio.run(worker._stop_process_group(process))
        killpg.assert_called_once_with(process.pid, worker.signal.SIGTERM)
        self.assertEqual(process.returncode, -15)

    def test_apk_validator_rejects_invalid_binary_manifest(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"not-binary-xml")
            archive.writestr("classes.dex", b"dex\n035\0" + b"x" * 32)
        temp = __import__("tempfile").NamedTemporaryFile(suffix=".apk", delete=False)
        try:
            temp.write(data.getvalue()); temp.close()
            with self.assertRaises(Exception):
                worker._validate_apk(Path(temp.name))
        finally:
            os.unlink(temp.name)

    def test_apk_validator_rejects_invalid_dex_magic(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00" + b"x" * 32)
            archive.writestr("classes.dex", b"not-a-dex-file" + b"x" * 32)
        temp = __import__("tempfile").NamedTemporaryFile(suffix=".apk", delete=False)
        try:
            temp.write(data.getvalue()); temp.close()
            with self.assertRaises(Exception):
                worker._validate_apk(Path(temp.name))
        finally:
            os.unlink(temp.name)

    def test_apk_validator_rejects_duplicate_entries(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00" + b"x" * 32)
            archive.writestr("classes.dex", b"dex\n035\0" + b"x" * 32)
            archive.writestr("classes.dex", b"dex\n035\0" + b"y" * 32)
        temp = __import__("tempfile").NamedTemporaryFile(suffix=".apk", delete=False)
        try:
            temp.write(data.getvalue()); temp.close()
            with self.assertRaises(Exception):
                worker._validate_apk(Path(temp.name))
        finally:
            os.unlink(temp.name)

    def test_apk_validator_rejects_zip_without_android_entries(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("readme.txt", "not an apk")
        temp = __import__("tempfile").NamedTemporaryFile(suffix=".apk", delete=False)
        try:
            temp.write(data.getvalue()); temp.close()
            with self.assertRaises(Exception):
                worker._validate_apk(Path(temp.name))
        finally:
            os.unlink(temp.name)
    def test_apk_signature_verification_rejects_missing_apksigner(self):
        with patch.dict(os.environ, {"ANDROID_HOME": "/nonexistent/android-sdk"}):
            with self.assertRaises(Exception) as raised:
                worker._verify_apk_signature(Path("/tmp/example.apk"))
        self.assertIn("signature verifier is unavailable", str(raised.exception))

    def test_apk_signature_verification_rejects_invalid_signature(self):
        import tempfile
        with tempfile.TemporaryDirectory() as sdk_dir:
            signer = Path(sdk_dir) / "build-tools/35.0.0/apksigner"
            signer.parent.mkdir(parents=True)
            signer.touch()
            with patch.dict(os.environ, {"ANDROID_HOME": sdk_dir}), \
                 patch("android_builder.worker.subprocess.run", return_value=type("Result", (), {"returncode": 1, "stdout": "", "stderr": "unsigned"})()):
                with self.assertRaises(Exception) as raised:
                    worker._verify_apk_signature(Path("/tmp/example.apk"))
        self.assertIn("does not have a valid Android signature", str(raised.exception))

    def test_apk_signature_verification_accepts_apksigner_success(self):
        import tempfile
        with tempfile.TemporaryDirectory() as sdk_dir:
            signer = Path(sdk_dir) / "build-tools/35.0.0/apksigner"
            signer.parent.mkdir(parents=True)
            signer.touch()
            with patch.dict(os.environ, {"ANDROID_HOME": sdk_dir}), \
                 patch("android_builder.worker.subprocess.run", return_value=type("Result", (), {"returncode": 0, "stdout": "Verified using v2 scheme", "stderr": ""})()):
                worker._verify_apk_signature(Path("/tmp/example.apk"))

