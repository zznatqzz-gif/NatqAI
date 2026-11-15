# NatqAI deployment candidate

This archive contains the NatqAI FastAPI backend, web frontend, and automated tests.

## Start command
Run from the `backend` directory:
`python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`

## Required production configuration
- `NATQAI_ENV=production`
- `NATQAI_SECRET_KEY`: unique random secret, at least 32 characters
- `NATQAI_CORS_ORIGINS`: comma-separated trusted public origins (no wildcard)
- `NATQAI_AI_BASE_URL`, `NATQAI_AI_API_KEY`, `NATQAI_AI_MODEL`: provider configuration

## Database persistence
The app uses SQLite. Attach a persistent volume in the hosting platform and set
`NATQAI_DATABASE` to a database path on that volume. Do not rely on an ephemeral
container filesystem for production data. Back up the database before upgrades.

## Media worker
If media jobs are used, run `python worker.py` as a separate worker process
with the same database path and environment variables.

## Validation performed on the source archive
- ZIP integrity test passed.
- Python unittest suite: 20 tests passed.
- Python compile check passed.
- JavaScript syntax checks passed for `app.js` and `i18n.js`.

This is a deployment candidate, not a live deployment. Configure secrets, persistent
storage, and provider settings in the hosting platform before publishing.


## Workspace API update
- Added authenticated project file listing, writing, and reading endpoints.
- Project ownership is checked before file operations.
- File paths are validated to prevent traversal outside the user's project workspace.
- Validation: 23 backend tests passed after this update.
- This update adds backend workspace APIs; automatic AI-driven project generation and frontend workspace UI are still pending.


## Project workspace UI update
- Added project list and project creation controls to the frontend.
- Added a workspace view to list, open, edit, create, and save project text files.
- Workspace requests use the authenticated project file APIs.
- Validation after this frontend update: 23 backend tests passed; Node syntax check passed.
- AI-driven automatic code generation, execution, and repair are not yet implemented.


## AI project file generation update
- Added an authenticated endpoint to generate a bounded set of project text files from an explicit user prompt.
- Added a workspace prompt and Generate Files action in the frontend.
- Generation is create-only: it refuses to overwrite an existing non-empty project.
- Generated paths and file types are validated; path traversal and binary/executable file types are rejected.
- The generator does not execute code, install packages, run tests on generated apps, or build APKs.
- Validation: 26 backend tests passed; Python compileall and JavaScript syntax checks passed.
- The AI generation endpoint was tested with a mocked provider response; live provider operation still requires deployment configuration of NATQAI_AI_API_KEY.


## Project ZIP export update
- Added an authenticated project ZIP download endpoint and a workspace download button.
- Export checks project ownership and caps the uncompressed content at 20 MiB.
- Validation: 28 backend tests passed; Python compileall and JavaScript syntax checks passed.
- Generated projects can now be saved in the workspace and downloaded as ZIP archives.
- Running generated code, automated debugging, APK compilation, and live AI-provider verification remain future work.


## AI project review update
- Added an authenticated project review endpoint and a workspace review button.
- The configured AI provider reviews a bounded selection of project text files and returns structured findings.
- Sensitive-looking files and key/database file extensions are excluded from review context.
- Review is read-only: it does not execute code or modify project files.
- Validation: 28 backend tests passed; Python compileall and JavaScript syntax checks passed.
- The review endpoint was tested with a mocked provider response; live provider review still requires deployment configuration.


## AI-assisted repair proposal and approval
- Added a repair-preview endpoint for an existing project file. It returns a proposed full-file replacement and the SHA-256 hash of the original; it does not save changes.
- Added an explicit apply endpoint. The browser asks the user to approve before sending the proposed content.
- Apply checks the original file hash and rejects stale proposals with HTTP 409, preventing overwriting edits made after preview.
- The workspace review findings now include a "Prepare and review fix" action.
- Repair preview is provider-generated and has not been live-verified with a real AI provider. It does not run tests or execute project code.
- Validation on this updated archive: 30 backend tests passed; Python source compilation and JavaScript syntax checks passed.

## Safe project syntax-check update
- Added an authenticated project check endpoint with project ownership verification.
- The checker performs non-executing Python AST parsing and JSON parsing.
- JavaScript/TypeScript and other text formats are explicitly reported as not checked; no code is executed.
- Limits: first 100 files and 2 MiB of aggregate source text per request.
- Added a workspace button to display per-file check results.
- Validation: 34 backend tests passed; Python compileall and JavaScript syntax checks passed.
- This is a syntax/configuration check, not a full runtime test or isolated code execution environment.


## Container deployment preparation (v9)
- Added `backend/Dockerfile` to package the FastAPI backend and frontend together.
- Added `backend/railway.json` with Dockerfile build configuration, `/health` health check, and restart policy.
- Added a root `.dockerignore` to keep local secrets, databases, uploads, and caches out of the build context.
- Container defaults SQLite to `/data/natqai.db`; production still requires a persistent volume mounted at `/data` and production environment variables.
- This is deployment preparation only. No Railway account was connected, no hosting service was created, and no public deployment was performed.
- In-app one-click publishing, isolated project execution, and Android APK compilation are not included in this update.

## Deployment preflight update (v10)
- Added authenticated `GET /api/v1/deployment/readiness` endpoint.
- The endpoint checks production mode, secret-key policy, CORS allowlist, persistent database path, AI provider configuration, Railway connection presence, and required container configuration files.
- The response never returns configured secret values. It reports blockers and warnings and explicitly states that no deployment was performed.
- Added a workspace action to display deployment readiness checks from inside NatqAI.
- Validation: 36 backend tests passed; Python compileall and JavaScript syntax checks passed.
- This is a read-only preflight only. Railway credential connection, creating a hosting project, deploying user projects, deployment logs/domains, isolated builds, and APK compilation are not implemented yet.


## Deployment credential verification hardening (v11)
- A configured Railway token is no longer treated as proof of a connected/validated Railway account.
- Readiness explicitly reports whether a credential is configured and whether the provider connection has actually been verified; verification remains false until a real Railway API validation is implemented.
- Publishing remains not-ready while Railway validation is unavailable. No deployment is attempted.
- Added regression coverage to ensure configured credentials and AI secrets are never echoed in readiness output.

## Railway account connection (v12)
- Added authenticated in-app Railway connection status, connect, and disconnect endpoints.
- The connect endpoint validates the supplied Railway API token against the Railway GraphQL identity query before saving it.
- Tokens are encrypted per user with Fernet; the encryption key is derived from NATQAI_SECRET_KEY. Changing that application secret requires users to reconnect Railway.
- The frontend accepts the token in a password field inside NatqAI, clears the field after submission, shows only account identity/status, and supports disconnecting.
- Deployment readiness now reports a verified per-user Railway connection only after the remote identity check succeeds.
- Tests mock the Railway HTTP response; no real Railway account was connected and no deployment was performed during this build.
- Validation: 37 backend tests passed; Python compilation and JavaScript syntax checks passed.
- Remaining: implement project upload/build/deploy orchestration, deployment history/logs/domains, safe isolated build execution, and Android APK compilation.

## Railway deployment status visibility (v13)
- Added an authenticated endpoint that fetches the newest deployment for a selected Railway project, service, and environment.
- The response distinguishes `QUEUED`/`BUILDING`/other in-progress states from a confirmed `SUCCESS`; empty history is reported as `NO_DEPLOYMENTS`.
- Added a frontend action to refresh and display the latest deployment state from inside NatqAI.
- Fixed the API test module layout so the full set of previously appended tests is collected by pytest; corrected an invalid AsyncMock assertion.
- Validation: 46 backend tests passed; Python compileall and JavaScript syntax checks passed.
- Important limitation: this still operates on a service whose source is already configured in Railway. NatqAI does not yet upload the current workspace files to Railway, create a build from those files, or provide build/runtime logs and domain management. No live account or deployment was used for these mocked tests.


## v14: private deployment-source intake

- Added authenticated ZIP upload per owned NatqAI project at `POST /api/v1/projects/{project_id}/deployment-source` (multipart field `file`).
- Added metadata readback at `GET /api/v1/projects/{project_id}/deployment-source`.
- Uploads are stored outside the public frontend/static directory; only metadata is returned.
- ZIP validation checks archive integrity, traversal paths, symlinks, duplicate names, entry count, compressed size, expanded size, and extreme compression ratios.
- The server does not extract or execute uploaded project code. This stage stores a validated source archive only; it does not transfer the archive to Railway or create a Railway deployment.
- Defaults: 50 MiB upload limit, 5,000 entries, 250 MiB expanded size. Configure storage with `NATQAI_DEPLOYMENT_SOURCES_DIR`.


## v15: upload and deploy the saved ZIP through Railway CLI

- The backend container installs the official `@railway/cli` package.
- Added `POST /api/v1/projects/{project_id}/deployment-source/deploy`. It requires a previously validated ZIP, a verified per-user Railway connection, and a Railway project/service/environment selection.
- Before queuing the deploy, the API verifies that the selected service and environment belong to the selected Railway project.
- A background task extracts the validated archive into a temporary directory with path-containment checks, then invokes `railway up` with explicit project, environment, and service IDs, passing the encrypted account-scoped credential to the CLI through `RAILWAY_API_TOKEN`. The build runs on Railway; NatqAI does not execute the submitted application code in its API process.
- Added `GET /api/v1/projects/{project_id}/deployment-source/runs/{run_id}` for private per-user job status.
- The UI now has a separate “upload ZIP and deploy” action with an explicit confirmation prompt. The existing action remains for redeploying a service's already configured source.
- The CLI's successful detached response means only that Railway accepted/queued the upload/build. NatqAI labels it `triggered`, not `SUCCESS`; users must inspect Railway deployment status until it reaches terminal `SUCCESS`.
- Added tests for the mocked CLI upload flow and for a missing CLI installation. Validation: 48 backend tests passed; Python compileall and Node syntax checks passed.
- Live Railway deployment was not performed. It still requires deploying this updated NatqAI container with Railway CLI available, a valid Railway token with permissions for the selected target, persistent storage for the SQLite database and ZIP archives, and a user-initiated deploy action. Build/runtime logs, domain setup, stop/redeploy lifecycle controls, isolated code execution/testing, and Android APK compilation remain incomplete.

## v16: authoritative Railway deployment monitoring

- Added additive database fields for Railway's remote status, deployment ID, public URL, and last status-check timestamp; existing databases are migrated without destructive table replacement.
- After `railway up --detach` accepts the uploaded source, NatqAI now polls the newest deployment using the explicitly scoped Railway project, environment, and service IDs.
- The monitor distinguishes confirmed `SUCCESS`, `FAILED`/`CRASHED`, approval-required, sleeping/removed, and in-progress/unknown states. A queued CLI response is never reported as a successful deployment.
- The run-status API returns the remote status, deployment ID, and deployment URL. The frontend continues polling and displays a safe HTTPS link when Railway returns a public URL.
- Polling is bounded to 20 minutes (10-second intervals); if no terminal state is observed, the record is marked `UNKNOWN` and the user is directed to verify Railway's deployment history.
- Validation: 49 backend tests passed; Python compileall and Node syntax checks passed. The test suite includes a mocked successful Railway deployment response and JSON response normalization.
- No live Railway account or real deployment was used. This requires deploying the updated NatqAI container. Build/runtime log retrieval, custom domain management, stop/redeploy lifecycle controls, isolated code execution/testing, and Android APK compilation remain incomplete.


## v17 — Railway build/runtime logs

- Added an authenticated endpoint to retrieve build or runtime logs for a specific NatqAI deployment run.
- The endpoint checks the run against the authenticated user's project ownership before contacting Railway; another user receives 404.
- Uses the documented Railway CLI form `railway logs --service <service> --environment <environment> --lines 150 --json`, adding `--build` for build logs.
- Returns at most 150 log entries and caps parsed stdout at 200 KB; raw logs are not persisted in NatqAI's database.
- Added workspace buttons to display build logs and runtime logs for the latest ZIP deployment request.
- Logs can contain secrets printed by the deployed application. NatqAI restricts retrieval to the project owner; users should avoid printing credentials in application logs.
- This feature has been tested with mocked Railway CLI output. No real Railway account, live deployment, or live log response was tested.


## v18 — Railway service controls

- Added authenticated `POST /api/v1/integrations/railway/service-action` for `redeploy` and `stop` actions.
- The API verifies the selected service and environment belong to the selected Railway project before invoking the CLI.
- Redeploy uses `railway redeploy --service ... --environment ... --yes`; stop uses `railway down --service ... --environment ... --yes`.
- Stop requires `confirm_stop: true`. Railway `down` removes the latest successful deployment but does not delete the service or its configuration; the site may become unavailable.
- CLI output is not returned to the browser to avoid leaking sensitive diagnostics. The response states that the request was accepted, not that the final remote state is verified. Refresh deployment status in the Railway panel to verify.
- Frontend controls require an explicit confirmation dialog, with a separate warning for stop.
- Tests cover successful scoped redeploy, explicit stop confirmation, and rejecting a service outside the selected project.
- No live Railway account or paid infrastructure action was used during tests.


## v19 — custom domain management

- Added authenticated domain management endpoints for Railway: list domains, add a custom domain, inspect a domain's DNS/certificate status, and delete a domain.
- Before every domain operation, NatqAI verifies through Railway GraphQL that the selected service and environment belong to the selected project.
- Uses the documented Railway CLI domain commands (`railway domain list`, `railway domain <hostname>`, `railway domain status <hostname>`, and `railway domain delete <hostname> --yes`) with explicit project, environment, and service scope.
- Custom hostnames are validated; optional service ports must be between 1 and 65535. Delete requires `confirm_delete: true`. CLI output is parsed as JSON and command errors are returned as safe generic messages.
- Added in-app controls to list, add, check DNS/SSL, and delete domains. The UI explains that users must add the DNS records returned by Railway; DNS propagation may take up to 72 hours and a domain may return 404 until ownership verification and certificate setup complete.
- Validation: 55 backend tests passed; Python compileall and frontend JavaScript syntax checks passed.
- Tests use mocked Railway CLI and GraphQL responses. No live custom domain was added, modified, or deleted, and no real DNS or SSL status was checked.


## v20 — Android Studio source package
- Added `GET /api/v1/projects/{project_id}/android-package` to export an Android Studio WebView wrapper ZIP from an owned project.
- Includes a Java WebView activity, Android manifest, Gradle project files, README, and project files under Android assets.
- Excludes hidden files, `.env` files, databases, keys, caches, node_modules, and symlinks; enforces 500 files / 20 MiB. Requires root `index.html`.
- Added a workspace button to download the Android source package.
- This is source scaffolding, not a compiled APK. Compile with Android Studio / Gradle 8.7, JDK 17, and Android SDK 35; configure the HTTPS NatqAI API URL in `natqai-config.js` and allow `https://appassets.androidplatform.net` in `NATQAI_CORS_ORIGINS` first. No Android SDK build is performed on the NatqAI server.

## بناء APK من داخل NatqAI (الإصدار v21)

زر **بناء APK وتنزيله** يرسل مشروع Android المصدر إلى عامل بناء مستقل عبر `ANDROID_BUILDER_URL` و`ANDROID_BUILDER_TOKEN`. يجب نشر صورة `backend/android_builder/Dockerfile` كخدمة خاصة منفصلة، وتعيين السر القوي نفسه في خدمة API والعامل. لا تشغّل عامل البناء داخل عملية API ولا تمنحه Docker socket أو أسرار المستخدم. انظر `backend/android_builder/README_AR.md` لإعداد العامل وحدود موارده.

إذا لم يتم إعداد العامل، يعيد API حالة 503 برسالة صريحة؛ لا يتم إنشاء APK وهمي. عند نجاح العامل، يتحقق API من نوع وحجم الملف قبل تنزيله. البناء الحالي ينتج **debug APK** للتجربة، وليس إصداراً موقعاً للنشر في المتجر. لم يُنفذ بناء حقيقي أثناء إعداد هذه الحزمة لأن بيئة إعداد ZIP لا تحتوي Docker أو Android SDK.

## تحسينات عامل APK (الإصدار v22)

- افحص جاهزية العامل عبر `GET /ready` بعد النشر؛ `/health` وحده لا يثبت توفر Android SDK أو Gradle.
- لا تُرسل APK للمتصفح إلا بعد فحص ZIP ووجود `AndroidManifest.xml` و`classes.dex` وفحص CRC لكل عناصر الأرشيف.
- يُشغّل عامل البناء بصلاحيات أقل مع حدود موارد على مستوى Docker، إضافة إلى حدود CPU/حجم الملفات داخل عملية Gradle.
- لا تزال بيئة بناء ZIP الحالية بلا Docker أو Android SDK؛ يلزم نشر العامل الخاص وتجربة بناء APK حقيقية قبل اعتبار ميزة APK جاهزة للإنتاج.

## فحص جاهزية Android Builder (v23)
يوفر API نقطة `GET /api/v1/projects/{project_id}/android-builder-status` لفحص العامل الخاص قبل البناء. تتطلب النقطة تسجيل الدخول وملكية المشروع، ولا تعرض عنوان العامل أو رمز التوثيق. يعرض زر بناء APK حالة عدم التهيئة أو عدم الجاهزية أو تعذر الاتصال قبل محاولة البناء. يجب أن يعيد العامل `/ready` الحالة 200؛ وهذا الفحص لا يغني عن تجربة بناء فعلية وتنزيل APK والتحقق منه بعد نشر العامل.
