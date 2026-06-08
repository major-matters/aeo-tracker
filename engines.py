"""Answer-engine adapters for the AEO citation tracker.

Each engine takes a natural-language query and returns the URLs it cited. The
target domain is "cited" by an engine when one of those URLs is on that domain.

Only engines with a configured key are `available`. Claude (Anthropic web search)
is wired and tested. Perplexity, OpenAI, and Gemini are written to their public
APIs and activate the moment their key is present; they are untested here because
no key is configured. Read-only: we only send queries and read answers.

Keys (first found wins):
  Claude      .anthropic-api-key file (workspace) or ANTHROPIC_API_KEY
  Perplexity  PERPLEXITY_API_KEY
  OpenAI      OPENAI_API_KEY
  Gemini      GEMINI_API_KEY / GOOGLE_AI_API_KEY
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent  # major-labs/


@dataclass
class Result:
    engine: str
    prompt: str
    cited_urls: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _post(url: str, headers: dict, payload: dict, timeout: int = 60):
    """POST JSON, retrying transient failures (429/5xx/timeout) with backoff.
    On a non-retryable HTTP error, return the parsed error body so the caller can
    surface a clean message instead of an opaque exception."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "content-type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - fixed provider https endpoints
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            try:
                return json.loads(e.read().decode("utf-8"))  # provider error JSON, e.g. {"error": ...}
            except Exception:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def _redact(text: str, *secrets: Optional[str]) -> str:
    """Strip any API key out of a string before it is stored or printed. Gemini
    puts its key in the request URL, so an error could otherwise carry it."""
    for s in secrets:
        if s and len(s) > 8:
            text = text.replace(s, "***")
    return text


def _key_from_file_or_env(filename: str, *env: str) -> Optional[str]:
    p = ROOT / filename
    if p.exists():
        v = p.read_text().strip()
        if v:
            return v
    for e in env:
        if os.environ.get(e):
            return os.environ[e]
    return None


class Engine:
    name = "engine"

    def __init__(self):
        self.key: Optional[str] = None

    @property
    def available(self) -> bool:
        return bool(self.key)

    def query(self, prompt: str) -> Result:  # pragma: no cover - overridden
        raise NotImplementedError


class Claude(Engine):
    name = "claude"

    def __init__(self):
        self.key = _key_from_file_or_env(".anthropic-api-key", "ANTHROPIC_API_KEY")

    def query(self, prompt: str) -> Result:
        try:
            d = _post(
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                {
                    "model": os.environ.get("AEO_CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
                    "max_tokens": 700,
                    "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                    "messages": [{"role": "user", "content": prompt + " Cite your sources."}],
                },
            )
            if d.get("type") == "error":
                return Result(self.name, prompt, error=str(d.get("error"))[:200])
            urls = []
            for block in d.get("content", []):
                if block.get("type") == "web_search_tool_result":
                    for r in block.get("content", []) or []:
                        if isinstance(r, dict) and r.get("url"):
                            urls.append(r["url"])
                for c in block.get("citations") or []:
                    if c.get("url"):
                        urls.append(c["url"])
            return Result(self.name, prompt, cited_urls=urls)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            return Result(self.name, prompt, error=_redact(str(e), self.key)[:200])


class Perplexity(Engine):
    name = "perplexity"

    def __init__(self):
        self.key = _key_from_file_or_env(".perplexity-api-key", "PERPLEXITY_API_KEY")

    def query(self, prompt: str) -> Result:
        try:
            d = _post(
                "https://api.perplexity.ai/chat/completions",
                {"Authorization": f"Bearer {self.key}"},
                {"model": "sonar", "messages": [{"role": "user", "content": prompt}]},
            )
            # Perplexity returns citations as a top-level list of URLs.
            urls = list(d.get("citations") or [])
            for c in d.get("search_results") or []:
                if isinstance(c, dict) and c.get("url"):
                    urls.append(c["url"])
            return Result(self.name, prompt, cited_urls=urls)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            return Result(self.name, prompt, error=_redact(str(e), self.key)[:200])


class OpenAI(Engine):
    name = "openai"

    def __init__(self):
        self.key = _key_from_file_or_env(".openai-api-key", "OPENAI_API_KEY")

    def query(self, prompt: str) -> Result:
        try:
            d = _post(
                "https://api.openai.com/v1/responses",
                {"Authorization": f"Bearer {self.key}"},
                {"model": "gpt-4.1", "tools": [{"type": "web_search"}], "input": prompt},
            )
            urls = []
            for item in d.get("output", []) or []:
                for c in item.get("content", []) or []:
                    for a in c.get("annotations", []) or []:
                        if a.get("type") == "url_citation" and a.get("url"):
                            urls.append(a["url"])
            return Result(self.name, prompt, cited_urls=urls)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            return Result(self.name, prompt, error=_redact(str(e), self.key)[:200])


class Gemini(Engine):
    name = "gemini"

    def __init__(self):
        self.key = _key_from_file_or_env(".gemini-api-key", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY")

    def query(self, prompt: str) -> Result:
        try:
            model = "gemini-2.5-flash"
            d = _post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.key}",
                {},
                {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]},
            )
            urls = []
            for cand in d.get("candidates", []) or []:
                gm = cand.get("groundingMetadata") or {}
                for chunk in gm.get("groundingChunks", []) or []:
                    web = chunk.get("web") or {}
                    # Gemini's uri is a vertexaisearch redirect that hides the real
                    # source; web.title carries the actual domain. Prefer it.
                    title = web.get("title")
                    if title and "." in title and " " not in title:
                        urls.append("https://" + title)
                    elif web.get("uri"):
                        urls.append(web["uri"])
            return Result(self.name, prompt, cited_urls=urls)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            return Result(self.name, prompt, error=_redact(str(e), self.key)[:200])


def all_engines() -> List[Engine]:
    return [Claude(), Perplexity(), OpenAI(), Gemini()]
