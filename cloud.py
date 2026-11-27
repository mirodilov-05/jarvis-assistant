"""Cloud brain for Jarvis V3 — 0 GB of video memory.

  Groq   (free key: https://console.groq.com/keys)        speech-to-text (Whisper large-v3 turbo) + language model with tools
  Gemini (free key: https://aistudio.google.com/apikey)   screen vision + backup language model

Both are called through their OpenAI-compatible HTTP endpoints with plain `requests` (no extra packages).
Keys live in Windows Credential Manager (connections.get_secret): "groq:api_key", "gemini:api_key".
Settings: [cloud] in config.toml / data/settings.json.

What is sent where: your recognised commands and Jarvis's context (tasks, notes it needs) go to Groq/Google;
audio of a command goes to Groq; a screenshot goes to Google only when you ask Jarvis to look at the screen.
"""

from __future__ import annotations

import io
import json
import re
import threading
import time
import wave

import numpy as np
import requests

import connections
import core

GROQ = "https://api.groq.com/openai/v1"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai"
SAMPLE_RATE = 16000

_http = requests.Session()          # keep-alive: saves ~100–200 ms per request
_lock = threading.Lock()
_DEAD: set[str] = set()
STATS = {"provider": "", "model": "", "ms": 0, "error": "", "stt_ms": 0, "calls": 0}


def setting(key: str, default=None):
    return core.setting("cloud", key, default)


def key(provider: str) -> str:
    return connections.get_secret(f"{provider}:api_key")


def has(provider: str) -> bool:
    return bool(key(provider))


def enabled() -> bool:
    """Cloud brain on (default) and at least one key saved."""
    return bool(setting("enabled", True)) and (has("groq") or has("gemini"))


def stt_enabled() -> bool:
    return bool(setting("enabled", True)) and bool(setting("stt", True)) and has("groq")


def local_fallback() -> bool:
    return bool(setting("local_fallback", False))


class CloudError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Speech to text (Groq Whisper)
# ---------------------------------------------------------------------------

def wav_bytes(pcm: np.ndarray, rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


_LANG_NAMES = {"russian": "ru", "uzbek": "uz", "english": "en", "ukrainian": "ru", "belarusian": "ru"}


def transcribe(pcm: np.ndarray, lang: str | None = "ru", prompt: str | None = None, timeout: float = 15) -> dict:
    """int16 PCM -> {"text", "lang", "segments": [{avg_logprob, no_speech_prob, compression_ratio, start, text}]}."""
    k = key("groq")
    if not k:
        raise CloudError("нет ключа Groq")
    data = {"model": setting("stt_model", "whisper-large-v3-turbo"), "response_format": "verbose_json",
            "temperature": "0"}
    if lang:
        data["language"] = lang
    if prompt:
        data["prompt"] = prompt[:800]
    t0 = time.time()
    r = _http.post(f"{GROQ}/audio/transcriptions", headers={"Authorization": f"Bearer {k}"}, data=data,
                   files={"file": ("speech.wav", wav_bytes(pcm), "audio/wav")}, timeout=timeout)
    if r.status_code != 200:
        STATS["error"] = f"Groq STT {r.status_code}: {r.text[:160]}"
        raise CloudError(STATS["error"])
    STATS["stt_ms"] = int((time.time() - t0) * 1000)
    js = r.json()
    lg = lang or _LANG_NAMES.get(str(js.get("language", "")).lower(), "ru")
    return {"text": (js.get("text") or "").strip(), "lang": lg, "segments": js.get("segments") or []}


def transcribe_long(pcm: np.ndarray, lang: str | None = "ru", piece_s: int = 600) -> list[tuple[float, str]]:
    """Long recordings: 10-minute pieces (the free plan accepts files up to 25 MB). -> [(start_sec, text)]."""
    out = []
    step = piece_s * SAMPLE_RATE
    for i in range(0, len(pcm), step):
        res = transcribe(pcm[i:i + step], lang, timeout=120)
        base = i / SAMPLE_RATE
        for s in res["segments"]:
            out.append((base + float(s.get("start", 0)), str(s.get("text", "")).strip()))
    return out


# ---------------------------------------------------------------------------
# Language model (Groq first, Gemini as backup) — OpenAI chat format with tools
# ---------------------------------------------------------------------------

def _providers(vision: bool) -> list[tuple[str, str, str]]:
    """[(name, base_url, model)] in the order to try."""
    out = []
    if not vision and has("groq"):
        # each Groq model has its own free per-minute limit: when one is busy (429) the next one answers
        models = [setting("llm_model", "qwen/qwen3.8-27b"), setting("llm_backup_model", "openai/gpt-oss-120b"),
                  "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        for m in dict.fromkeys(x for x in models if x):
            if m not in _DEAD:          # Groq said this model doesn't exist: don't waste time on it again
                out.append(("groq", GROQ, m))
    if has("gemini"):
        for m in gemini_models(vision):
            if m not in _DEAD:
                out.append(("gemini", GEMINI, m))
    return out


def gemini_models(vision: bool = False) -> list[str]:
    """Gemini models to try in order: free models are often busy (503) or out of quota (429) — then the next one answers."""
    first = setting("vision_model" if vision else "gemini_model", "gemini-flash-latest")
    return list(dict.fromkeys([first, "gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-3.5-flash"]))


def _body(model: str, messages: list[dict], tools: list[dict] | None, max_tokens: int, temperature: float) -> dict:
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    # no long "thinking": spoken answers must come back in well under a second
    if model.startswith("qwen/"):
        body["reasoning_effort"] = "none"
    elif "gpt-oss" in model:
        body["reasoning_effort"] = "low"
    elif model.startswith("gemini"):
        body["reasoning_effort"] = "low"      # quick answers; a model that refuses the option is asked again without it
    return body


def chat(messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 400, temperature: float = 0.3,
         vision: bool = False, timeout: float = 12) -> tuple[str, list[tuple[str, dict]]]:
    """-> (text, [(tool_name, args), ...]). Tries the providers in order; raises CloudError if all fail."""
    errors = []
    for name, base, model in _providers(vision):
        t0 = time.time()
        try:
            body = _body(model, messages, tools, max_tokens, temperature)
            r = _http.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key(name)}"},
                           json=body, timeout=timeout)
            if r.status_code == 400 and "reasoning" in r.text.lower() and "reasoning_effort" in body:
                body.pop("reasoning_effort")   # a model that doesn't take this option: ask again without it
                r = _http.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key(name)}"},
                               json=body, timeout=timeout)
        except requests.RequestException as e:
            errors.append(f"{name}: {e.__class__.__name__}")
            continue
        if r.status_code in (404, 400) and ("model_not_found" in r.text or "decommissioned" in r.text
                                            or "does not exist" in r.text):
            _DEAD.add(model)
        if r.status_code != 200:
            errors.append(f"{name}/{model} {r.status_code}: {r.text[:160]}")
            core.log.warning("cloud %s/%s HTTP %s: %s", name, model, r.status_code, r.text[:300])
            continue
        msg = (r.json().get("choices") or [{}])[0].get("message") or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {}
            calls.append((fn.get("name", ""), args if isinstance(args, dict) else {}))
        text = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()
        with _lock:
            STATS.update(provider=name, model=model, ms=int((time.time() - t0) * 1000), error="",
                         calls=STATS["calls"] + 1)
        return text, calls
    STATS["error"] = "; ".join(errors) or "нет ключей"
    raise CloudError(STATS["error"])


def ask(system: str, messages: list[dict], max_tokens: int = 300) -> str:
    text, _ = chat([{"role": "system", "content": system}] + messages, max_tokens=max_tokens)
    return text


def look(system: str, question: str, png_b64: str, max_tokens: int = 400) -> str:
    """Gemini vision: screenshot + question."""
    if not has("gemini"):
        raise CloudError("Для зрения нужен бесплатный ключ Gemini: добавьте его в настройках.")
    text, _ = chat([{"role": "system", "content": system},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_b64}"}},
                        {"type": "text", "text": question}]}],
                   max_tokens=max_tokens, temperature=0.2, vision=True, timeout=40)
    return text


def status() -> dict:
    return {"enabled": enabled(), "stt": stt_enabled(), "groq": has("groq"), "gemini": has("gemini"),
            "local_fallback": local_fallback(), **STATS}


def test(provider: str) -> str:
    """Quick check from the settings drawer."""
    if provider == "groq":
        r = _http.get(f"{GROQ}/models", headers={"Authorization": f"Bearer {key('groq')}"}, timeout=10)
    else:
        r = _http.get(f"{GEMINI}/models", headers={"Authorization": f"Bearer {key('gemini')}"}, timeout=10)
    if r.status_code == 200:
        return "ok"
    raise CloudError(f"{r.status_code}: {r.text[:160]}")
