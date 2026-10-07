"""Thin wrapper around any OpenAI-compatible chat endpoint, returning validated Pydantic objects.

Works with OpenAI, Google Gemini, Groq, Ollama, OpenRouter, ... (see README for base URLs).
Robustness features, because free tiers and local models are quirky:
  * JSON is requested with response_format=json_object; providers that reject it (or reject a
    temperature) are retried without the offending parameter, and that is remembered;
  * output is parsed leniently (code fences, <think> blocks) and validated with Pydantic, with one
    "repair" retry that shows the model its validation error;
  * a shared requests-per-minute limiter (LLM_MAX_RPM) keeps free tiers from returning 429s;
  * every response is cached on disk, so re-running the same CV costs nothing.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .cache import cache, make_key
from .config import Settings, settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class _RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stamps: deque[float] = deque()

    def acquire(self, rpm: int) -> None:
        if rpm <= 0:
            return
        while True:
            with self._lock:
                now = time.time()
                while self._stamps and now - self._stamps[0] > 60:
                    self._stamps.popleft()
                if len(self._stamps) < rpm:
                    self._stamps.append(now)
                    return
                wait = 60 - (now - self._stamps[0]) + 0.05
            time.sleep(max(wait, 0.05))


_limiter = _RateLimiter()
_unsupported: dict[str, set[str]] = {}  # "base_url|model" -> {"response_format", "temperature"}
_unsupported_lock = threading.Lock()


@dataclass
class LLMStats:
    calls: int = 0
    cache_hits: int = 0
    failures: int = 0
    by_task: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"calls": self.calls, "cache_hits": self.cache_hits, "failures": self.failures, "by_task": self.by_task}


def extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("The model did not return a JSON object.")
    chunk = text[start: end + 1]
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", chunk)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Could not parse the model's JSON: {exc}") from exc


class LLMClient:
    def __init__(self, cfg: Settings = settings) -> None:
        self.cfg = cfg
        self.stats = LLMStats()
        self._client = None

    @property
    def enabled(self) -> bool:
        return self.cfg.llm_configured

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI  # imported lazily so offline mode never needs it

            self._client = OpenAI(
                base_url=self.cfg.llm_base_url,
                api_key=self.cfg.llm_api_key or "not-needed",
                timeout=self.cfg.llm_timeout,
                max_retries=3,
            )
        return self._client

    def _create(self, model: str, messages: list[dict], temperature: float) -> str:
        import openai

        key = f"{self.cfg.llm_base_url}|{model}"
        for _ in range(3):
            with _unsupported_lock:
                skip = set(_unsupported.get(key, set()))
            kwargs: dict = {"model": model, "messages": messages}
            if "response_format" not in skip:
                kwargs["response_format"] = {"type": "json_object"}
            if "temperature" not in skip:
                kwargs["temperature"] = temperature
            _limiter.acquire(self.cfg.llm_max_rpm)
            try:
                resp = self._get_client().chat.completions.create(**kwargs)
                return resp.choices[0].message.content or ""
            except openai.BadRequestError as exc:
                msg = str(exc).lower()
                drop = None
                if "temperature" in msg and "temperature" in kwargs:
                    drop = "temperature"
                elif ("response_format" in msg or "json" in msg) and "response_format" in kwargs:
                    drop = "response_format"
                elif "response_format" in kwargs:
                    drop = "response_format"
                elif "temperature" in kwargs:
                    drop = "temperature"
                if not drop:
                    raise LLMError(f"Request rejected by the provider: {exc}") from exc
                with _unsupported_lock:
                    _unsupported.setdefault(key, set()).add(drop)
            except openai.AuthenticationError as exc:
                raise LLMError("The LLM provider rejected the API key (check LLM_API_KEY).") from exc
            except openai.NotFoundError as exc:
                raise LLMError(f"Model or endpoint not found (check LLM_MODEL and LLM_BASE_URL): {exc}") from exc
            except openai.RateLimitError as exc:
                raise LLMError("Rate limit reached at the provider. Set LLM_MAX_RPM in .env, or wait a minute.") from exc
            except openai.APIConnectionError as exc:
                raise LLMError(f"Could not reach the LLM at {self.cfg.llm_base_url}.") from exc
            except openai.APIError as exc:
                raise LLMError(f"LLM provider error: {exc}") from exc
        raise LLMError("The provider kept rejecting the request parameters.")

    def complete_json(
        self,
        task: str,
        system: str,
        user: str,
        schema: type[T],
        strong: bool = False,
        temperature: float = 0.0,
    ) -> T:
        if not self.enabled:
            raise LLMError("No LLM configured.")
        model = self.cfg.llm_model_strong if strong else self.cfg.llm_model
        shape = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        sys_msg = (
            f"{system}\n\nReply with a single JSON object only (no prose, no code fences) that matches this JSON schema:\n{shape}"
        )
        messages = [{"role": "system", "content": sys_msg}, {"role": "user", "content": user}]
        ckey = make_key("llm", model, messages, temperature)
        cached = cache.get("llm", ckey)
        if cached is not None:
            try:
                self.stats.cache_hits += 1
                return schema.model_validate(cached)
            except ValidationError:
                pass
        self.stats.calls += 1
        self.stats.by_task[task] = self.stats.by_task.get(task, 0) + 1
        try:
            content = self._create(model, messages, temperature)
            try:
                data = extract_json(content)
                obj = schema.model_validate(data)
            except (LLMError, ValidationError) as first:
                repair = messages + [
                    {"role": "assistant", "content": content[:4000]},
                    {"role": "user", "content": f"That was invalid: {str(first)[:600]}. Return the corrected JSON object only."},
                ]
                self.stats.calls += 1
                content = self._create(model, repair, temperature)
                data = extract_json(content)
                obj = schema.model_validate(data)
        except (LLMError, ValidationError) as exc:
            self.stats.failures += 1
            raise LLMError(str(exc)) from exc
        cache.set("llm", ckey, obj.model_dump())
        return obj
