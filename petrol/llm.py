"""OpenAI uyumlu sohbet API'si uzerinden yapilandirilmis (JSON sema) cagrilar.

Prototipte Groq; uretimde LLM_BASE_URL / model adlari degistirilerek baska saglayiciya gecilir.
"""
import time
from typing import Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_TEMPERATURE

T = TypeVar("T", bound=BaseModel)
UsageHook = Callable[[str, str, dict], None]  # (asama, model, usage)

# Katı sema modunda desteklenmeyebilecek anahtarlar; dogrulamayi zaten pydantic yapiyor
_DROP_KEYS = {"title", "default", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"}


class LLMError(RuntimeError):
    pass


class RateLimited(LLMError):
    """Saglayici hiz/kota siniri: gecici, is kaybedilmemeli; sonraki turda tekrar denenir."""


def _strict_schema(node, is_name_map: bool = False):
    """Sema anahtar kelimelerini temizler; 'properties'/'$defs' altindaki ALAN ADLARINA dokunmaz."""
    if isinstance(node, dict):
        return {
            k: _strict_schema(v, k in ("properties", "$defs") and not is_name_map)
            for k, v in node.items()
            if is_name_map or k not in _DROP_KEYS
        }
    if isinstance(node, list):
        return [_strict_schema(v) for v in node]
    return node


class LLMClient:
    def __init__(self, on_usage: UsageHook | None = None, http: httpx.Client | None = None) -> None:
        if http is None:
            if not LLM_API_KEY:
                raise LLMError("API anahtari yok: .env dosyasina GROQ_API_KEY=... ekleyin")
            http = httpx.Client(
                base_url=LLM_BASE_URL,
                headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                timeout=120,
            )
        self._http = http  # testler sahte bir istemci verebilir
        self._on_usage = on_usage

    def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        out: type[T],
        stage: str,
        reasoning_effort: str = "low",
        max_tokens: int = 4000,
        retries: int = 5,
    ) -> T:
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": out.__name__,
                    "strict": True,
                    "schema": _strict_schema(out.model_json_schema()),
                },
            },
            "reasoning_effort": reasoning_effort,
            "include_reasoning": False,
            "temperature": LLM_TEMPERATURE,
            "max_completion_tokens": max_tokens,
        }
        last_error = ""
        only_rate_limits = True
        for attempt in range(retries):
            try:
                resp = self._http.post("/chat/completions", json=payload)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                only_rate_limits = False
                time.sleep(2**attempt)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                # Hiz siniri: saglayicinin soyledigi kadar bekle
                wait = float(resp.headers.get("retry-after") or 2**attempt)
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                only_rate_limits &= resp.status_code == 429
                time.sleep(min(wait, 90))
                continue
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")

            body = resp.json()
            # Basarisiz denemeler dahil harcanan her token butceye yazilir
            if self._on_usage:
                self._on_usage(stage, model, body.get("usage", {}))
            content = body["choices"][0]["message"].get("content") or ""
            try:
                return out.model_validate_json(content)
            except ValidationError as exc:
                last_error = f"gecersiz cikti: {exc.errors()[:2]}"
                only_rate_limits = False
                continue
        error_cls = RateLimited if only_rate_limits else LLMError
        raise error_cls(f"{retries} denemede basarisiz. Son hata: {last_error}")
