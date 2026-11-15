
## v24 — Android Builder readiness verification

The private Android worker's `/ready` endpoint now verifies the actual Gradle 8.7 and Java 17 executables, Android SDK Platform 35 (`android.jar`), and Android Build Tools 35 (`aapt2`, `d8`, `zipalign`). The `/build` endpoint independently refuses a valid source archive with HTTP 503 when the toolchain is unavailable, so bypassing the frontend readiness check cannot start an unusable build. Invalid source archives are still rejected before toolchain readiness is checked.

A real APK build remains pending deployment to a host with the Android toolchain; the current development environment does not provide Docker/Gradle/Android SDK.

The `/ready` endpoint is authenticated with the same `ANDROID_BUILDER_TOKEN` bearer credential as `/build`. NatqAI sends the token during its readiness probe; unauthenticated probes receive HTTP 401. The status API never returns the worker URL or credential.
