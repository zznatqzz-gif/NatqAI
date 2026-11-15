"""Configurable image/video generation adapters for NatqAI.

The adapter intentionally uses a generic HTTP contract so deployments can
connect providers without hard-coding vendor credentials or SDKs.
"""
from __future__ import annotations

import os
from typing import Any
import httpx


class MediaProviderError(RuntimeError):
    pass


class MediaProvider:
    def __init__(self) -> None:
        self.api_key = os.getenv("NATQAI_MEDIA_API_KEY", "")
        self.image_url = os.getenv("NATQAI_IMAGE_API_URL", "")
        self.video_url = os.getenv("NATQAI_VIDEO_API_URL", "")
        self.timeout = float(os.getenv("NATQAI_MEDIA_TIMEOUT", "180"))

    async def generate(self, media_type: str, prompt: str, reference_url: str | None = None) -> dict[str, Any]:
        endpoint = self.image_url if media_type == "image" else self.video_url
        if not endpoint or not self.api_key:
            raise MediaProviderError(
                f"مزود {media_type} غير مضبوط. أضف NATQAI_{'IMAGE' if media_type == 'image' else 'VIDEO'}_API_URL وNATQAI_MEDIA_API_KEY."
            )
        payload: dict[str, Any] = {"prompt": prompt}
        if reference_url:
            payload["reference_url"] = reference_url
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
            response.raise_for_status()
            data = response.json()
            output_url = data.get("output_url") or data.get("url")
            if not isinstance(output_url, str) or not output_url.startswith(("https://", "http://")):
                raise MediaProviderError("استجابة مزود الوسائط لا تحتوي على output_url صالح.")
            return {"output_url": output_url, "provider_job_id": str(data.get("id", ""))[:200]}
        except MediaProviderError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise MediaProviderError("تعذر الاتصال بمزود إنشاء الوسائط.") from exc
