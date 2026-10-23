"""Model connector. The repo is the memory; the model is swappable.

Providers:
  anthropic          Claude models
  openai             OpenAI models
  openai_compatible  anything with an OpenAI-style API (Gemini, Ollama, LM Studio, OpenRouter...)
Each one takes images, so the model can look at charts.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from pathlib import Path


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a model reply, even if it is wrapped in text."""
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    cand = m.group(1) if m else None
    if cand is None:
        i, j = text.find("{"), text.rfind("}")
        cand = text[i:j + 1] if i != -1 and j > i else None
    if cand:
        try:
            data = json.loads(cand)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _b64(path):
    p = Path(path)
    mt = mimetypes.guess_type(p.name)[0] or "image/png"
    return mt, base64.b64encode(p.read_bytes()).decode()


class Model:
    def complete(self, system: str, messages: list[dict], images=()) -> str:
        raise NotImplementedError


class AnthropicModel(Model):
    def __init__(self, model: str, api_key_env: str = "ANTHROPIC_API_KEY", max_tokens: int = 4096, **_):
        import anthropic
        self.client = anthropic.Anthropic(api_key=os.environ[api_key_env])
        self.model, self.max_tokens = model, max_tokens

    def complete(self, system, messages, images=()):
        msgs = [dict(m) for m in messages]
        if images and msgs:
            blocks = []
            for p in images:
                mt, d = _b64(p)
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": d}})
            blocks.append({"type": "text", "text": msgs[-1]["content"]})
            msgs[-1]["content"] = blocks
        r = self.client.messages.create(model=self.model, max_tokens=self.max_tokens, system=system, messages=msgs)
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


class OpenAIModel(Model):
    def __init__(self, model: str, api_key_env: str = "OPENAI_API_KEY", base_url: str | None = None,
                 max_tokens: int = 4096, **_):
        from openai import OpenAI
        key = os.environ.get(api_key_env, "not-needed")
        self.client = OpenAI(api_key=key, base_url=base_url) if base_url else OpenAI(api_key=key)
        self.model, self.max_tokens = model, max_tokens

    def complete(self, system, messages, images=()):
        msgs = [{"role": "system", "content": system}] + [dict(m) for m in messages]
        if images and len(msgs) > 1:
            blocks = []
            for p in images:
                mt, d = _b64(p)
                blocks.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{d}"}})
            blocks.append({"type": "text", "text": msgs[-1]["content"]})
            msgs[-1]["content"] = blocks
        r = self.client.chat.completions.create(model=self.model, messages=msgs, max_tokens=self.max_tokens)
        return r.choices[0].message.content or ""


class FakeModel(Model):
    """Scripted replies, for tests and dry runs."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, messages, images=()):
        self.calls.append({"system": system, "messages": messages, "images": list(images)})
        return self.replies.pop(0) if self.replies else "{}"


def get_model(cfg: dict) -> Model:
    mc = dict(cfg.get("model", {}))
    provider = mc.pop("provider", "anthropic")
    try:
        if provider == "anthropic":
            return AnthropicModel(**mc)
        if provider in ("openai", "openai_compatible"):
            return OpenAIModel(**mc)
    except ImportError:
        extra = "anthropic" if provider == "anthropic" else "openai"
        raise SystemExit(f"The '{extra}' package is not installed. Run:  pip install -e \".[{extra}]\"")
    except KeyError as e:
        raise SystemExit(f"Missing environment variable {e}. Set your API key (see config.yaml, api_key_env).")
    raise ValueError(f"Unknown model provider: {provider}")
