"""
LLM waterfall: NVIDIA NIM -> Groq (Llama) -> Gemini -> Cohere, first one with a
key wins, and any failure falls through to the next. Mirrors the VaultMind
provider waterfall. Returns (text, provider) or (None, None) when nothing works.
"""
from __future__ import annotations

import json
import os
import urllib.request


def _post(url: str, headers: dict, body: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _nim(prompt, mt, temp):
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        return None
    model = os.environ.get("NIM_MODEL", "meta/llama-3.3-70b-instruct")
    d = _post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {"model": model, "messages": [{"role": "user", "content": prompt}],
         "temperature": temp, "max_tokens": mt},
    )
    return d["choices"][0]["message"]["content"].strip(), f"nim:{model.split('/')[-1]}"


def _groq(prompt, mt, temp):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    d = _post(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {"model": model, "messages": [{"role": "user", "content": prompt}],
         "temperature": temp, "max_tokens": mt},
    )
    return d["choices"][0]["message"]["content"].strip(), f"groq:{model}"


def _gemini(prompt, mt, temp):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    d = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        {"Content-Type": "application/json"},
        {"contents": [{"parts": [{"text": prompt}]}],
         "generationConfig": {"temperature": temp, "maxOutputTokens": mt}},
    )
    return d["candidates"][0]["content"]["parts"][0]["text"].strip(), f"gemini:{model}"


def _cohere(prompt, mt, temp):
    key = os.environ.get("COHERE_API_KEY")
    if not key:
        return None
    model = os.environ.get("COHERE_MODEL", "command-r-08-2024")
    d = _post(
        "https://api.cohere.com/v2/chat",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {"model": model, "messages": [{"role": "user", "content": prompt}],
         "temperature": temp, "max_tokens": mt},
    )
    return d["message"]["content"][0]["text"].strip(), f"cohere:{model}"


def complete(prompt: str, max_tokens: int = 200, temperature: float = 0.4):
    for provider in (_nim, _groq, _gemini, _cohere):
        try:
            out = provider(prompt, max_tokens, temperature)
            if out and out[0]:
                return out
        except Exception:  # noqa: BLE001 - waterfall: try the next provider
            continue
    return None, None
