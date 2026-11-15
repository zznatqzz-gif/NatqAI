"""OpenAI-compatible chat provider gateway for NatqAI."""
from __future__ import annotations
import os
import httpx

class AIProviderError(RuntimeError):
    pass

class OpenAICompatibleProvider:
    def __init__(self) -> None:
        self.base_url = (os.getenv("NATQAI_AI_BASE_URL", "").strip().strip('"').strip("'") or "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
        self.api_key = os.getenv("NATQAI_AI_API_KEY", "")
        self.model = os.getenv("NATQAI_AI_MODEL", "gemini-flash-lite-latest").strip() or "gemini-flash-lite-latest"
        self.timeout = float(os.getenv("NATQAI_AI_TIMEOUT", "60"))

    async def chat(self, messages: list[dict[str, str]]) -> dict:
        if not self.api_key:
            raise AIProviderError("مزود الذكاء الاصطناعي غير مضبوط. أضف NATQAI_AI_API_KEY إلى ملف البيئة.")
        payload = {"model": self.model, "messages": messages, "temperature": 0.7}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise AIProviderError("أعاد مزود الذكاء الاصطناعي إجابة فارغة.")
            return {"content": content.strip(), "model": data.get("model", self.model), "usage": data.get("usage", {})}
        except AIProviderError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("تعذر الاتصال بمزود الذكاء الاصطناعي. تحقق من الإعدادات وحاول مجدداً.") from exc
    async def stream_chat(self, messages: list[dict[str, str]]):
        """Yield text deltas from an OpenAI-compatible SSE chat completion."""
        if not self.api_key:
            raise AIProviderError("مزود الذكاء الاصطناعي غير مضبوط. أضف NATQAI_AI_API_KEY إلى ملف البيئة.")
        payload = {"model": self.model, "messages": messages, "temperature": 0.7, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            event = __import__("json").loads(raw)
                            delta = event["choices"][0].get("delta", {}).get("content")
                        except (ValueError, KeyError, IndexError, TypeError):
                            continue
                        if isinstance(delta, str) and delta:
                            yield delta
        except AIProviderError:
            raise
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = exc.response.text[:500]
            print(f"AI PROVIDER HTTP ERROR: status={status}, detail={detail}", flush=True)
            raise AIProviderError(f"خطأ مزود الذكاء الاصطناعي (HTTP {status}).") from exc
        except (httpx.HTTPError, OSError) as exc:
            print(f"AI PROVIDER CONNECTION ERROR: {type(exc).__name__}: {str(exc)[:300]}", flush=True)
            raise AIProviderError("تعذر الاتصال بمزود الذكاء الاصطناعي أثناء البث.") from exc

