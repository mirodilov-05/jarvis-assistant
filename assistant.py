"""Jarvis — background voice assistant + desktop app (Russian + Uzbek).

Wake it by:
  * English wake phrases (instant): "Hey Jarvis", "Alexa", "Hey Mycroft"
  * Saying its name in any language: "Джарвис", "Jarvis" ... — alone, or with the
    command in the same breath: "Джарвис, открой телеграм".
  * The 🎤 button in the app, or Ctrl+Alt+J to open the app window.

Speech is recognised on the GPU (Whisper fine-tuned for Uzbek, also good at Russian).
Abilities live in plugins/*.py. The app is served at http://127.0.0.1:50778 and
opened as a desktop window (Edge app mode).
"""

from __future__ import annotations

import asyncio
import collections
import ctypes
import json
import logging
import os
import queue
import random
import re
import socket
import subprocess
import sys
import threading
import time
import winsound
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
(BASE / "data").mkdir(exist_ok=True)
# pythonw.exe has no console: give libraries that print progress somewhere to write
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(BASE / "data" / "stderr.log", "a", encoding="utf-8")

import importlib  # noqa: E402
importlib.import_module("cuda_setup")  # side effect: must run before faster_whisper is imported
import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402

logging.basicConfig(
    filename=BASE / "data" / "assistant.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
for noisy in ("httpx", "httpcore", "faster_whisper", "telethon", "comtypes", "urllib3", "aiohttp.access"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("jarvis")

import core  # noqa: E402
import cloud  # noqa: E402
import voiceprint as vp  # noqa: E402
from oww_compat import Model  # noqa: E402

SAMPLE_RATE = 16000
FRAME = 1280  # 80 ms, what openWakeWord expects
APP_PORT = 50778
APP_URL = f"http://127.0.0.1:{APP_PORT}"

CONFIG = core.load_config()


def cfg(section: str, key: str, default=None):
    return core.setting(section, key, default)


def langs() -> list[str]:
    return [lg for lg in cfg("voice", "languages", ["ru", "uz"]) if lg in core.LANGS] or ["ru", "uz"]


STATUS = {"state": "starting"}
LEVEL = {"v": 0.0}   # microphone loudness, read by the HUD


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
               [(n, ctypes.c_ulonglong) for n in ("total", "avail", "tpf", "apf", "tv", "av", "aev")]


_cpu_prev: list = []


def _cpu_percent() -> float:
    idle, kern, user = (ctypes.c_ulonglong() for _ in range(3))
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
    cur = (idle.value, kern.value + user.value)
    prev = _cpu_prev[:] or [cur]
    _cpu_prev[:] = [cur]
    d_idle, d_total = cur[0] - prev[0][0], cur[1] - prev[0][1]
    return round(100 * (1 - d_idle / d_total), 1) if d_total else 0.0


def telemetry() -> dict:
    """What the HUD shows: GPU/VRAM, CPU/RAM, which models are loaded where. Called only while the HUD is open."""
    out: dict = {"cpu": _cpu_percent(), "game": GAME["on"], "status": STATUS["state"],
                 "whisper": {k: v[1] for k, v in _models.items()}}
    ms = _MemStatus(dwLength=ctypes.sizeof(_MemStatus))
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
        out["ram"] = {"used_gb": round((ms.total - ms.avail) / 2**30, 1), "total_gb": round(ms.total / 2**30, 1)}
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        name, util, used, total, temp = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
        out["gpu"] = {"name": name, "util": int(util), "vram_used": int(used), "vram_total": int(total), "temp": int(temp)}
    except Exception:  # noqa: BLE001
        out["gpu"] = None
    try:
        import requests
        url = core.CONFIG.get("llm", {}).get("ollama_url", "http://127.0.0.1:11434")
        out["llm"] = [{"name": m["name"], "vram_mb": round(m.get("size_vram", 0) / 2**20)}
                      for m in requests.get(url + "/api/ps", timeout=1).json().get("models", [])]
    except Exception:  # noqa: BLE001
        out["llm"] = None   # Ollama not running
    out["memory_model"] = bool(sys.modules.get("memory") and sys.modules["memory"]._model)
    out["cloud"] = cloud.status()
    out["vram_gb"] = round(out["gpu"]["vram_used"] / 1024, 1) if out.get("gpu") else None
    try:
        import pcx
        out["focus"] = pcx.focus_active()
    except Exception:  # noqa: BLE001
        out["focus"] = False
    return out


def set_status(state: str) -> None:
    if STATUS["state"] != state:
        STATUS["state"] = state
        core.emit({"type": "status", "state": state})


# ---------------------------------------------------------------------------
# Text to speech: Piper (natural offline Russian voices), Microsoft neural voices
# (online, needed for Uzbek), Windows SAPI (last-resort fallback)
# ---------------------------------------------------------------------------

_winmm = ctypes.windll.winmm
VOICES_DIR = BASE / "voices"


def _mci(cmd: str) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _winmm.mciSendStringW(cmd, buf, 255, 0)
    return buf.value


def speakable(text: str) -> str:
    """Make text nicer to hear: drop emoji/markdown, read times naturally."""
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️‍*#_`]", "", text)
    text = re.sub(r"\bhttps?://\S+", "", text)
    text = text.replace("→", ",").replace("«", "").replace("»", "")
    return re.sub(r"\s+", " ", text).strip()


OUT_LEVEL = {"v": 0.0}       # loudness of Jarvis's own voice, for the HUD

_SENT_END = re.compile(r"(?<=[.!?…。！？])\s*")


def _sentences(text: str, max_len: int = 220) -> list[str]:
    """Splits speech into sentences (Japanese 。！？ too) and joins short ones, so each piece is quick to make."""
    out: list[str] = []
    for s in (p.strip() for p in _SENT_END.split(text or "") if p and p.strip()):
        while len(s) > max_len * 2:                       # a very long sentence: cut at a comma or a space
            cut = max(s.rfind("、", 0, max_len), s.rfind(",", 0, max_len), s.rfind(" ", 0, max_len))
            cut = cut if cut > max_len // 3 else max_len
            out.append(s[:cut + 1].strip())
            s = s[cut + 1:].strip()
        if out and len(out[-1]) + len(s) < max_len:
            out[-1] = f"{out[-1]} {s}" if not re.search(r"[。！？、]$", out[-1]) else out[-1] + s
        elif s:
            out.append(s)
    return out


def voice_profile(vid: str, opts: dict | None = None) -> tuple[float, float]:
    """(speed %, tone %) of one voice: piper_<name> or edge_<lang>. A preview passes its own values in opts."""
    o = opts or {}
    sp = o.get("speed", core.setting("voices", f"{vid}_speed", 0))
    tn = o.get("tone", core.setting("voices", f"{vid}_tone", 0))
    try:
        return max(-40.0, min(60.0, float(sp))), max(-25.0, min(25.0, float(tn)))
    except (TypeError, ValueError):
        return 0.0, 0.0


class Speaker:
    def __init__(self) -> None:
        self._q: queue.Queue[tuple[str, str, int]] = queue.Queue()
        self._stop = threading.Event()
        self.speaking = threading.Event()
        self.last_end = 0.0
        self._piper: dict = {}
        self._edge_off_until = 0.0
        self.gain = 1.0              # 0.3 while deciding whether you are interrupting
        self.last_text = ""
        self.current = ""            # what he is saying now (to tell his own echo from your words)
        self.gen = 0                 # stop() makes everything said before it void
        threading.Thread(target=self._run, daemon=True, name="tts").start()

    def say(self, text: str, lang: str = "ru", opts: dict | None = None) -> None:
        """opts (a preview from the voice editor): engine, voice, speed, tone."""
        text = speakable(text or "")
        if text:
            self._q.put((text, lang, self.gen, opts or {}))

    def stop(self) -> None:
        self.gen += 1
        self._stop.set()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def busy(self) -> bool:
        return self.speaking.is_set() or not self._q.empty() or time.time() - self.last_end < 0.5

    def wait(self, timeout: float = 60) -> None:
        end = time.time() + timeout
        time.sleep(0.1)
        while (self.speaking.is_set() or not self._q.empty()) and time.time() < end:
            time.sleep(0.1)

    # -- engines ----------------------------------------------------------
    def _piper_voice(self, name: str):
        if name not in self._piper:
            from piper import PiperVoice

            path = VOICES_DIR / f"ru_RU-{name}-medium.onnx"
            if not path.exists():
                return None
            self._piper[name] = PiperVoice.load(str(path))
        return self._piper[name]

    def _piper_say(self, text: str, opts: dict | None = None) -> bool:
        from piper import SynthesisConfig

        vname = (opts or {}).get("voice") or cfg("voice", "piper_voice_ru", "dmitri")
        voice = self._piper_voice(vname)
        if voice is None:
            return False
        rate = int(cfg("voice", "tts_rate", 1))
        speed, tone = voice_profile(f"piper_{vname}", opts)
        pitch = 1.0 + tone / 100.0
        # a higher tone without a faster voice: made slower by the same factor it is then played faster
        syn = SynthesisConfig(length_scale=max(0.45, (1.0 - rate * 0.04) / (1.0 + speed / 100.0) * pitch),
                              noise_scale=0.6, noise_w_scale=0.7)
        stream = None
        try:
            for chunk in voice.synthesize(text, syn_config=syn):   # one chunk per sentence: starts talking at once
                if self._stop.is_set():
                    break
                if f"tts_{vname}" not in vp._load() and len(chunk.audio_int16_array) > chunk.sample_rate * 1.2:
                    # remember how Jarvis's own voice sounds, so barge-in doesn't react to it
                    threading.Thread(target=vp.set_tts_voice, args=(vname, chunk.audio_int16_array, chunk.sample_rate),
                                     daemon=True).start()
                if stream is None:
                    stream = sd.OutputStream(samplerate=int(chunk.sample_rate * pitch), channels=1, dtype="int16", latency="low")
                    stream.start()
                self._write(stream, chunk.audio_int16_array)
                self._write(stream, np.zeros(int(chunk.sample_rate * 0.12), dtype=np.int16))  # pause between sentences
        finally:
            self._close(stream)
        return True

    def _write(self, stream, data: np.ndarray) -> None:
        """Small pieces, so «стоп» and getting quieter work at once."""
        quiet = 0.45 if core.feature("quiet_voice") else 1.0
        for i in range(0, len(data), 1024):
            if self._stop.is_set():
                return
            OUT_LEVEL["v"] = float(np.abs(data[i:i + 1024]).mean())
            g = quiet * self.gain
            stream.write(data[i:i + 1024] if g == 1.0 else (data[i:i + 1024].astype(np.float32) * g).astype(np.int16))

    def _close(self, stream) -> None:
        OUT_LEVEL["v"] = 0.0
        if stream is not None:
            if self._stop.is_set():
                stream.abort()          # drop what is still in the sound card: silence right now
            else:
                stream.stop()
            stream.close()

    EDGE_VOICES = {"ru": "ru-RU-DmitryNeural", "uz": "uz-UZ-SardorNeural",
                   "en": "en-US-AndrewNeural",      # warm, confident: a presenter's voice
                   "ja": "ja-JP-KeitaNeural"}

    def _edge_synth(self, text: str, voice: str, timeout: float, tries: int, rate: str = "+0%", pitch: str = "+0Hz") -> bytes | None:
        """One sentence as MP3 bytes from Microsoft's voices (a short piece: it arrives in about a second)."""
        import edge_tts

        async def go() -> bytes:
            # The audio of a sentence arrives in ~1.5 s, but closing Microsoft's connection sometimes hangs for long:
            # once audio has come and then 1.5 s pass with nothing new, the sentence is complete.
            buf = bytearray()
            comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            it = comm.stream().__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(it.__anext__(), timeout=1.5 if buf else timeout)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    if buf:
                        break
                    raise
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)
        for attempt in range(1, tries + 1):
            try:
                data = asyncio.run(go())
                if data:
                    return data
            except Exception as e:  # noqa: BLE001
                log.warning("edge-tts attempt %d failed (%s)", attempt, type(e).__name__)
            if attempt < tries:
                time.sleep(0.3)
        return None

    def _edge(self, text: str, lang: str, opts: dict | None = None) -> bool:
        """Speaks sentence by sentence: the next one is prepared while the current one plays.

        Before, the whole text was made at once with a 6-second limit: a long Japanese or English slide never fitted,
        and the Russian Windows voice read it instead (Japanese skipped, English with a Russian accent).
        """
        from concurrent.futures import ThreadPoolExecutor

        if time.time() < self._edge_off_until:
            return False
        voice = cfg("voice", f"edge_voice_{lang}") or self.EDGE_VOICES.get(lang, "en-US-AndrewNeural")
        speed, tone = voice_profile(f"edge_{lang}", opts)
        base = str(cfg("voice", "edge_rate", "+0%")).rstrip("%")
        try:
            speed += float(base)
        except ValueError:
            pass
        rate, pitch = f"{round(speed):+d}%", f"{round(tone * 1.6):+d}Hz"      # tone %: about 1.6 Hz per percent
        parts = _sentences(text, 220 if lang != "ja" else 90)
        if not parts:
            return True
        # Russian has an offline voice (Piper) to fall back on at once, so the first sentence gets one short try
        first_timeout, timeout, tries = (2.5, 8, 1) if lang == "ru" else (12, 12, 2)
        stream = None
        played = False
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="edge")
        try:
            fut = pool.submit(self._edge_synth, parts[0], voice, first_timeout, tries, rate, pitch)
            for i in range(len(parts)):
                data = fut.result()
                if i + 1 < len(parts):
                    fut = pool.submit(self._edge_synth, parts[i + 1], voice, timeout, tries, rate, pitch)
                if not data:
                    if not played:
                        self._edge_off_until = time.time() + 300      # unreliable now: the local voice for 5 minutes
                        return False
                    continue                                          # one lost sentence: go on with the next
                stream = self._play_mp3(data, stream)
                played = True
                if self._stop.is_set():
                    break
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
            self._close(stream)
        return True

    def _play_mp3(self, data: bytes, stream):
        import io

        import av
        with av.open(io.BytesIO(data)) as f:
            rs = av.AudioResampler(format="s16", layout="mono", rate=24000)
            for frame in f.decode(audio=0):
                for fr in rs.resample(frame):
                    if stream is None:
                        stream = sd.OutputStream(samplerate=24000, channels=1, dtype="int16", latency="low")
                        stream.start()
                    self._write(stream, fr.to_ndarray().reshape(-1).astype(np.int16))
                if self._stop.is_set():
                    break
        return stream

    _SAPI_LANG = {"en": ("409", "809"), "ja": ("411",), "ru": ("419",)}

    def _sapi_lang(self, sapi, text: str, lang: str) -> bool:
        """A Windows voice of THAT language. Never the Russian voice for English or Japanese: it mangles them."""
        if lang == "ru":
            self._sapi(sapi, text)
            return True
        codes = self._SAPI_LANG.get(lang, ())
        voices = sapi.GetVoices()
        for i in range(voices.Count):
            item = voices.Item(i)
            try:
                lcids = str(item.GetAttribute("Language")).lower().split(";")
            except Exception:  # noqa: BLE001
                continue
            if any(c in lcids for c in codes):
                keep = sapi.Voice
                sapi.Voice = item
                try:
                    self._sapi(sapi, text)
                finally:
                    sapi.Voice = keep
                return True
        log.warning("No voice for %s: the Microsoft voices need the internet, and Windows has no %s voice installed", lang, lang)
        return False

    def _sapi(self, voice, text: str) -> None:
        voice.Speak(text, 1)
        while not voice.WaitUntilDone(100):
            if self._stop.is_set():
                voice.Speak("", 3)
                break

    def _run(self) -> None:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        sapi = comtypes.client.CreateObject("SAPI.SpVoice")
        voices = sapi.GetVoices()
        for i in range(voices.Count):
            if cfg("voice", "tts_voice", "Irina").lower() in voices.Item(i).GetDescription().lower():
                sapi.Voice = voices.Item(i)
                break
        try:  # load the Russian voice now so the first answer is instant
            self._piper_voice(cfg("voice", "piper_voice_ru", "dmitri"))
        except Exception:  # noqa: BLE001
            log.exception("Piper voice failed to load")
        while True:
            text, lang, gen, opts = self._q.get()
            if gen != self.gen:
                continue
            self._stop.clear()
            if gen != self.gen:          # stopped in this very moment
                continue
            self.current, self.gain = text, 1.0
            self.speaking.set()
            set_status("speaking")
            try:
                sapi.Rate = int(cfg("voice", "tts_rate", 1))
                sapi.Volume = 45 if core.feature("quiet_voice") else 100
                engine = opts.get("engine") or cfg("voice", f"tts_engine_{lang}", "piper" if lang == "ru" else "edge")
                done = False
                if engine == "piper" and lang == "ru":
                    done = self._piper_say(text, opts)
                elif engine == "edge":
                    done = self._edge(text, lang, opts) or (lang == "ru" and self._piper_say(text))
                if not done:
                    self._sapi_lang(sapi, re.sub(r"[ʻʼ’‘`]", "'", text), lang if lang in ("en", "ja") else "ru")
            except Exception:  # noqa: BLE001
                log.exception("TTS failed")
            finally:
                self.speaking.clear()
                self.last_text, self.current = text, ""
                self.last_end = time.time()
                if self._q.empty():
                    set_status(LISTENER.base_status() if LISTENER else "listening")


speaker = Speaker()
core.set_speaker(speaker.say, stop=speaker.stop, busy=lambda: speaker.speaking.is_set() or not speaker._q.empty())


def _stop_show() -> None:
    """«Стоп» also stops a presentation that is reading itself out loud."""
    try:
        from cognition import show
        show.pause()
    except Exception:  # noqa: BLE001
        log.exception("presentation pause failed")


# ---------------------------------------------------------------------------
# Speech to text: a small stock Whisper picks the language (it tells Russian
# from Uzbek almost perfectly), the Uzbek-tuned Whisper writes the words.
# ---------------------------------------------------------------------------

_models: dict = {}
_whisper_lock = threading.Lock()


def _load_model(name: str, device: str):
    from faster_whisper import WhisperModel

    try:
        m = WhisperModel(name, device=device, compute_type="int8_float16" if device == "cuda" else "int8",
                         cpu_threads=2)
        m.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language="ru")  # warm up
        return m
    except Exception:  # noqa: BLE001
        if device == "cpu":
            raise
        log.exception("Whisper %s on GPU failed, using CPU", name)
        return _load_model(name, "cpu")


_CUDA: dict = {}


def has_cuda() -> bool:
    """Is there an NVIDIA card that the speech models can use? (asked once)"""
    if "ok" not in _CUDA:
        try:
            import ctranslate2
            _CUDA["ok"] = ctranslate2.get_cuda_device_count() > 0
        except Exception:  # noqa: BLE001
            _CUDA["ok"] = False
        log.info("Speech on %s", "the NVIDIA card" if _CUDA["ok"] else "the processor (no NVIDIA card)")
    return _CUDA["ok"]


def stt_device() -> str:
    if GAME.get("on") and cfg("performance", "game_mode_cpu_speech", False):
        return "cpu"
    want = cfg("voice", "whisper_device", "cuda")
    return "cuda" if want == "cuda" and has_cuda() else "cpu"


def whisper(kind: str = "main"):
    """kind = "main" (writes text), "lid" (detects language) or "spot" (small CPU model that only listens for the name)."""
    device = "cpu" if kind == "spot" else stt_device()
    with _whisper_lock:
        m = _models.get(kind)
        if m is None or m[1] != device:
            # on the processor the big model takes seconds per phrase: a laptop without NVIDIA gets "small"
            main_name = cfg("voice", "whisper_model", "large-v3-turbo") if device == "cuda" else cfg("voice", "whisper_model_cpu", "small")
            name = main_name if kind == "main" else \
                cfg("voice", "spot_model", "tiny") if kind == "spot" else cfg("voice", "lid_model", "base")
            _models[kind] = (_load_model(name, device), device)
            log.info("Whisper %s model loaded: %s on %s", kind, name, device)
        return _models[kind][0]


PROMPTS = {
    "ru": "Открой Telegram. Включи Яндекс Музыку. Стоп музыка. Закрой вкладку. Выключи ноутбук. YouTube, WhatsApp, Steam, Discord, CS2.",
    "uz": "Jarvis, telegramni och, vazifa qo'sh, nechta vazifam bor, yozib ol, to'xtat.",
}
_HALLUCINATIONS = re.compile(
    r"(продолжение следует|субтитр|редактор субтитров|спасибо за просмотр|подписывайтесь|ставьте лайк|"
    r"thank you for watching|amara\.org|dima torzok|корректор|до новых встреч|^музыка$|"
    r"(динамичн|спокойн|весёл|весел|грустн|напряжённ|напряженн|торжествен)\w* музык|музыкальная заставка|"
    r"^(аплодисменты|смех|тишина|шум)\.?$)", re.I)
_REPEATS = re.compile(r"(.{2,12}?)\1{3,}")


def detect_language(a: np.ndarray, with_prob: bool = False):
    allowed = langs()
    if len(allowed) == 1:
        return (allowed[0], 1.0) if with_prob else allowed[0]
    _, _, probs = whisper("lid").detect_language(a)
    p = dict(probs)
    p_ru = p.get("ru", 0) + 0.5 * p.get("uk", 0) + 0.5 * p.get("be", 0)   # accented Russian can look Ukrainian/Belarusian
    if set(allowed) == {"ru", "uz"}:
        # the stock model doesn't know Uzbek well, but it recognises Russian with ~99% certainty
        lang = "ru" if p_ru >= 0.35 else "uz"
    else:
        lang = max(allowed, key=lambda lg: p.get(lg, 0))
    return (lang, p_ru) if with_prob else lang


_gate = {}
_gate_lock = threading.Lock()


def voiced_seconds(audio: np.ndarray) -> float:
    """How much real human speech is in the clip (neural VAD), in seconds."""
    from openwakeword.vad import VAD

    with _gate_lock:
        vad = _gate.setdefault("vad", VAD())
        vad.reset_states()
        n = sum(1 for i in range(0, len(audio) - 1280 + 1, 1280) if vad.predict(audio[i:i + 1280], frame_size=640) >= 0.5)
    return n * 0.08


def transcribe(audio: np.ndarray, accurate: bool = True, lang_hint: str | None = None) -> tuple[str, str, bool]:
    """Return (text, lang, reliable). reliable=False means mumbling/noise/hallucination."""
    if voiced_seconds(audio) < 0.24:   # no actual speech: don't let Whisper invent words
        return "", lang_hint or langs()[0], False
    spot = cloud.stt_enabled() and not accurate and cfg("cloud", "local_spotting", True)
    if cloud.stt_enabled() and not spot:
        try:
            return _transcribe_cloud(audio, accurate, lang_hint)
        except Exception as e:  # noqa: BLE001 - offline / quota
            log.warning("Cloud speech recognition failed: %s", e)
            if not cloud.local_fallback():
                _cloud_down_notice()
                return "", lang_hint or langs()[0], False
    a = audio.astype(np.float32) / 32768.0

    def decode(lg: str):
        segments, _ = whisper("spot" if spot else "main").transcribe(
            a, language=lg, beam_size=5 if accurate else 2, vad_filter=False, without_timestamps=True,
            condition_on_previous_text=False, temperature=0.0,
            initial_prompt=PROMPTS.get(lg) if accurate else ("Эй, Джарвис." if spot else None))
        out = list(segments)
        score = (sum(x.avg_logprob for x in out) / len(out)) if out else -9.0
        return out, score

    if lang_hint:
        lang = lang_hint
        segs, _ = decode(lang)
    else:
        lang, p_ru = detect_language(a, with_prob=True)
        segs, score = decode(lang)
        # accented Russian / Russian words inside Uzbek: when unsure, try the other language too and keep the clearer one
        if set(langs()) == {"ru", "uz"} and 0.04 <= p_ru <= 0.85 and accurate and stt_device() == "cuda":
            other = "uz" if lang == "ru" else "ru"
            segs2, score2 = decode(other)
            if score2 > score + 0.1:
                lang, segs = other, segs2
            log.info("LID ambiguous p_ru=%.2f: ru/uz scores -> %s", p_ru, lang)
    text = " ".join(s.text.strip() for s in segs).strip()
    if not segs or not text:
        return "", lang, False
    if lang == "uz" and len(re.findall(r"[а-яё]", text.lower())) > len(text) * 0.5:
        lang = "ru"
    avg_logprob = sum(s.avg_logprob for s in segs) / len(segs)
    no_speech = max(s.no_speech_prob for s in segs)
    compression = max(s.compression_ratio for s in segs)
    reliable = not (avg_logprob < -1.0 or (no_speech > 0.6 and avg_logprob < -0.6) or compression > 2.4
                    or _HALLUCINATIONS.search(text) or _REPEATS.search(text.replace(" ", ""))
                    # an echo of the vocabulary hint on silence/noise (real commands are heard confidently)
                        or (text.strip(" .,!?").lower() in PROMPTS.get(lang, "").lower() and no_speech > 0.3 and avg_logprob < -0.45))
    log.info("STT [%s] %.2f/%.2f/%.1f %s: %s", lang, avg_logprob, no_speech, compression,
             "ok" if reliable else "REJECTED", text[:200])
    if accurate:   # show in the app what was heard
        core.emit({"type": "heard", "text": text, "ok": reliable})
    return text, lang, reliable


def _reliable(text: str, lang: str, avg_logprob: float, no_speech: float, compression: float) -> bool:
    return not (avg_logprob < -1.0 or (no_speech > 0.6 and avg_logprob < -0.6) or compression > 2.4
                or _HALLUCINATIONS.search(text) or _REPEATS.search(text.replace(" ", ""))
                or (text.strip(" .,!?").lower() in PROMPTS.get(lang, "").lower() and no_speech > 0.3 and avg_logprob < -0.45))


def _transcribe_cloud(audio: np.ndarray, accurate: bool, lang_hint: str | None, hint: bool = True) -> tuple[str, str, bool]:
    """Groq Whisper large-v3 turbo: ~0.3 s, nothing on the GPU."""
    allowed = langs()
    lang = lang_hint or (allowed[0] if len(allowed) == 1 else None)
    res = cloud.transcribe(audio, lang, PROMPTS.get(lang or "ru") if accurate and hint else None)
    text, lang, segs = res["text"], res["lang"], res["segments"]
    if lang not in core.LANGS:
        lang = allowed[0]
    if not text:
        return "", lang, False
    if segs:
        avg_logprob = sum(float(s.get("avg_logprob", 0)) for s in segs) / len(segs)
        no_speech = max(float(s.get("no_speech_prob", 0)) for s in segs)
        compression = max(float(s.get("compression_ratio", 1)) for s in segs)
    else:
        avg_logprob, no_speech, compression = -0.3, 0.0, 1.0
    reliable = _reliable(text, lang, avg_logprob, no_speech, compression)
    log.info("STT cloud %dms [%s] %.2f/%.2f/%.1f %s: %s", cloud.STATS["stt_ms"], lang, avg_logprob, no_speech,
             compression, "ok" if reliable else "REJECTED", text[:200])
    if accurate:
        core.emit({"type": "heard", "text": text, "ok": reliable})
    return text, lang, reliable


_cloud_notice = {"t": 0.0}


def _cloud_down_notice() -> None:
    """Say once in a while that the cloud can't be reached (no internet, bad key, free limit)."""
    if time.time() - _cloud_notice["t"] > 120:
        _cloud_notice["t"] = time.time()
        core.emit({"type": "cloud", "ok": False, "error": cloud.STATS.get("error", "")})
        speaker.say("Нет связи с облаком, сэр. Проверьте интернет или ключ Groq.", "ru")


# ---------------------------------------------------------------------------
# "Jarvis" spotting that tolerates accents: жарис, жаррис, jarrus, javvis, джарбис…
# ---------------------------------------------------------------------------

_LAT = str.maketrans({"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "o", "ж": "j", "з": "z", "и": "i",
                      "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
                      "у": "u", "ф": "f", "х": "h", "ц": "s", "ч": "j", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "",
                      "э": "e", "ю": "yu", "я": "ya", "ў": "o", "қ": "k", "ғ": "g", "ҳ": "h"})


def _phonetic(word: str) -> str:
    w = re.sub(r"[^a-zа-яёўқғҳ]", "", word.lower()).translate(_LAT)
    w = w.replace("dzh", "j").replace("dj", "j").replace("zh", "j").replace("ch", "j").replace("sh", "s")
    w = w.replace("w", "v").replace("b", "v").replace("ph", "f")
    return re.sub(r"(.)\1+", r"\1", w)


def is_jarvis(word: str) -> bool:
    import difflib

    p = _phonetic(word)
    if not 4 <= len(p) <= 11:
        return False
    if p in {_phonetic(n) for n in cfg("wake", "names", [])}:
        return True
    p = re.sub(r"^(?:hey|hei|ey|ei|e|i)(?=(?:j|h|k|g)a?r)", "", p)        # «эйжарвис», «ихарвис» = «эй/и + харвис»
    if re.fullmatch(r"(?:h|k|g)ar{1,2}v?(?:i|e|y)s", p):                   # how Whisper hears your «жарвис»: харвис, карис
        return True
    if re.fullmatch(r"jayv(?:i|e)s", p):                                     # «джайвис»
        return True
    if not 4 <= len(p) <= 9:
        return False
    if not (p.startswith("j") or p.startswith("dar") or p.startswith("yar")):
        return False
    if len(p) < 5 or not re.search(r"[sz](a|i|u|ga|ni|y|ov|ev|ova|ovu)?$", p):   # the name ends in "-is": жарис, javvis, jarrus, джарисов
        return False
    # "jar…s/z" with up to 3 letters in between: jaris, jarus, jaruz, jaryus, jarvis, jarles…
    if re.fullmatch(r"(j|dj|dar|yar)[aeo]?r\w{0,3}[sz](a|i|u|ga|ni|y|ov|ev|ova|ovu)?", p) and len(p) <= 9:
        return True
    ratio = max(difflib.SequenceMatcher(None, p, t).ratio() for t in ("jarvis", "jarvisa", "jarvisi"))
    return ratio >= float(cfg("wake", "name_similarity", 0.62))


def find_name(text: str, max_pos: int = 2) -> int | None:
    """Index of the word that is "Jarvis" if it opens the phrase (after optional "эй/hey/salom")."""
    words = text.split()
    for i, w in enumerate(words[:max_pos + 1]):
        if is_jarvis(w):
            before = [x for x in words[:i] if not _FILLER_WORD.match(x)]
            return i if not before else None
    return None


_FILLER_WORD = re.compile(r"^(эй|ей|хей|хэй|и|hey|ey|xey|hay|eng|e|э|привет|слушай|salom|assalomu|alaykum|hoy|ok|okay|окей|о|а|ну|aka|ака|бро|bro)[,.!]?$", re.I)


# ---------------------------------------------------------------------------
# Game mode: when a full-screen game runs, free the GPU and stay quiet
# ---------------------------------------------------------------------------

GAME: dict = {"on": False, "name": ""}
_NOT_GAMES = {"explorer.exe", "msedge.exe", "chrome.exe", "browser.exe", "firefox.exe", "opera.exe", "applicationframehost.exe",
              "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe", "lockapp.exe", "vlc.exe",
              "mpc-hc64.exe", "potplayermini64.exe", "telegram.exe", "whatsapp.exe", "code.exe", "claude.exe"}


def _foreground_process() -> tuple[str, bool]:
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", False
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    path = ""
    if h:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            path = buf.value
        kernel32.CloseHandle(h)

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    fullscreen = rect.l <= 0 and rect.t <= 0 and rect.r >= sw and rect.b >= sh
    return path, fullscreen


def _is_game(path: str, fullscreen: bool) -> bool:
    low = path.lower()
    exe = os.path.basename(low)
    if not low or exe in _NOT_GAMES or "\\windows\\" in low:
        return False
    if any(k in low for k in ("\\steamapps\\common\\", "\\epic games\\", "\\riot games\\", "\\games\\", "\\battle.net\\",
                              "\\ubisoft game launcher\\", "\\ea games\\", "\\xboxgames\\", "\\gog galaxy\\games")):
        return True
    extra = [g.lower() for g in cfg("performance", "game_exes", [])]
    return exe in extra or (fullscreen and cfg("performance", "fullscreen_is_game", True))


def game_watcher() -> None:
    import requests

    last_game_seen = 0.0
    last_path = ""
    while True:
        try:
            if cfg("performance", "game_mode", True):
                path, fullscreen = _foreground_process()
                if _is_game(path, fullscreen):
                    last_game_seen, last_path = time.time(), path
                # stay in game mode through quick Alt+Tabs: leave only after 60 s without the game in front
                playing = time.time() - last_game_seen < 60
                path = last_path
            else:
                playing = False
            if playing != GAME["on"]:
                GAME.update(on=playing, name=os.path.basename(path) if playing else "")
                log.info("Game mode %s %s", "ON" if playing else "OFF", GAME["name"])
                core.CONFIG["_game_mode"] = playing
                core.CONFIG["_game_exe"] = GAME["name"] if playing else ""
                if core.profiles().get("auto_game", True):
                    core.set_override("game", "game" if playing else None)
                core.emit({"type": "game", "on": playing, "name": GAME["name"]})
                if playing:
                    try:  # free ~2.5 GB of video memory: unload the language model until the game ends
                        llm = core.CONFIG.get("llm", {})
                        requests.post(llm.get("ollama_url", "http://127.0.0.1:11434") + "/api/generate",
                                      json={"model": llm.get("model", "qwen3.5:2b-q4_K_M"), "keep_alive": 0}, timeout=10)
                    except Exception:  # noqa: BLE001
                        pass
                    if _models:
                        threading.Thread(target=lambda: (whisper("main"), len(langs()) > 1 and whisper("lid")), daemon=True).start()
                else:
                    def _restore():
                        if _models:
                            whisper("main"), len(langs()) > 1 and whisper("lid")
                        llm = sys.modules.get("jarvis_plugin_llm")
                        if llm:
                            llm.warm_up()   # load the language model back so the next answer is fast
                    threading.Thread(target=_restore, daemon=True).start()
        except Exception:  # noqa: BLE001
            log.exception("game watcher")
        time.sleep(4)


# ---------------------------------------------------------------------------
# Microphone, wake phrases, names, voice recorder
# ---------------------------------------------------------------------------

SFX_DIR = BASE / "voices" / "sfx"


def sfx(name: str, wait: bool = True, fallback: tuple[int, int] = (880, 90)) -> None:
    """Short interface sound (voices/sfx/<name>.wav); a plain beep if the file is missing or sounds are off."""
    path = SFX_DIR / f"{name}.wav"
    if not cfg("voice", "ui_sounds", True) or not path.exists():
        if wait:
            winsound.Beep(*fallback)
        return
    winsound.PlaySound(str(path), winsound.SND_FILENAME | (0 if wait else winsound.SND_ASYNC))


def duck_start() -> None:
    if core.feature("ducking"):
        try:
            import pcx
            pcx.duck(float(cfg("voice", "duck_level", 0.15)))
        except Exception:  # noqa: BLE001
            log.exception("ducking failed")


def duck_end_later() -> None:
    """Bring the music back once Jarvis has finished talking."""
    def go():
        try:
            time.sleep(0.3)
            speaker.wait(60)
            import pcx
            pcx.unduck()
        except Exception:  # noqa: BLE001
            log.exception("unducking failed")
    threading.Thread(target=go, daemon=True, name="unduck").start()


# a voice pack replaces only acknowledgements, never answers that carry information («Сейчас 21:08»)
_ACK = re.compile(r"^(открываю|запускаю|включаю|выключаю|закрываю|ставлю|готово|сделано|хорошо|принято|есть|выполн|"
                  r"записал|запомнил|добавил|удалил|отметил|перенёс|перенес|ищу|громче|тише|пауза|звук|"
                  r"напомню|таймер|будильник|понял|окей|ок(?=\W|$))", re.I)
_HUSH = r"(стоп|хватит|замолчи|молчи|тихо|тише|достаточно|понял|поняла|ладно|спасибо|ок|окей|все|ясно|джарвис)"
_DICTATE_START = re.compile(r"(начни|включи|начать) диктовку|diktovka\w* (boshla|yoq)")
_DICTATE_STOP = re.compile(r"(закончи|останови|стоп|хватит)\s*(диктовку)?|diktovka\w* (tugat|toxtat)|tugat|toxtat")
_RECORD_STOP = re.compile(r"^(джарвис |jarvis )?(стоп|stop|хватит|останови|закончи|заверши|сохрани|toxtat|toxta|bas|tamom)\w*"
                          r"( запис\w*| yozuv\w*| yozishni)?$")
_FILLER = re.compile(r"^(эй|ей|хей|hey|привет|слушай|salom|hoy|ok|окей)\s+")
WAKE_REPLIES = {
    "friend": ["Да?", "Слушаю!", "Что сделать?", "Говори.", "Я тут.", "Да, что такое?"],
    "work": ["Слушаю.", "Да.", "Готов."],
    "polite": ["Да, сэр?", "Слушаю Вас.", "Чем могу помочь, сэр?", "К Вашим услугам."],
    "tactical": ["Да, сэр?", "Слушаю, сэр.", "На связи."],
    "coder": ["Слушаю.", "Да?"],
    "business": ["Слушаю.", "Да, по делу?"],
    "quiet": [],
}


class AGC:
    """Automatic gain for detection: lifts whispers/quiet speech up to a normal level (up to 20x)."""

    def __init__(self, target: float = 3000.0, max_gain: float = 20.0) -> None:
        self.gain, self.target, self.max_gain = 1.0, target, max_gain

    def __call__(self, chunk: np.ndarray) -> np.ndarray:
        x = chunk.astype(np.float32)
        rms = float(np.sqrt(np.mean(x ** 2))) + 1e-6
        if rms * self.gain > 150:   # adapt only on sound, not on silence
            want = min(self.max_gain, max(1.0, self.target / rms))
            self.gain += (want - self.gain) * (0.3 if want < self.gain else 0.08)
        return np.clip(x * self.gain, -32768, 32767).astype(np.int16)


def spot(audio: np.ndarray) -> tuple[str, float]:
    """What the small local Whisper hears (for the name and «стоп»): (text, confidence). Never leaves the computer."""
    if voiced_seconds(audio) < 0.2:
        return "", -9.0
    # The name is checked by the tiny model on the processor (fast, private). Only with an NVIDIA card and no cloud
    # does the main local model do it. Before, a new laptop without a Groq key and without NVIDIA ran the big model
    # on the processor for every phrase, after a silent 1.6 GB download: Jarvis seemed deaf to «Джарвис».
    use_tiny = cfg("cloud", "local_spotting", True) and (cloud.stt_enabled() or stt_device() == "cpu")
    if not use_tiny:
        text, _, reliable = transcribe(audio, accurate=False)
        return text, -0.2 if reliable else -2.0
    segs, _ = whisper("spot").transcribe(audio.astype(np.float32) / 32768.0, language="ru", beam_size=2, vad_filter=False,
                                         without_timestamps=True, condition_on_previous_text=False, temperature=0.0,
                                         initial_prompt="Эй, Джарвис.")
    out = list(segs)
    text = " ".join(s.text.strip() for s in out).strip()
    return text, (sum(s.avg_logprob for s in out) / len(out)) if out else -9.0


_HUSH_START = re.compile(r"^(?:джарвис )?(?:стоп|топ|хватит|замолчи|помолчи|молчи|тихо|тише|достаточно|подожди|погоди|отмена|"
                         r"отмени|остановись|перестань|все все|ладно хватит)\b")


def own_words(text: str) -> float:
    """How much of a heard phrase is just Jarvis's own words coming back through the microphone (0…1)."""
    heard = [w for w in core.normalize(text, "ru").split() if len(w) > 2]
    mine = set(core.normalize(speaker.current or (speaker.last_text if time.time() - speaker.last_end < 4 else ""), "ru").split())
    return sum(w in mine for w in heard) / len(heard) if heard else 0.0


# how long Jarvis waits for your answer after a question or «Слушаю», then goes back to sleep
LISTEN_SECONDS = 5


class Listener:
    """The microphone is never switched off: Jarvis hears you while he talks and while he thinks.

    mode  idle     waiting for the name (or, while he talks, for you to interrupt him)
          command  you called him: the next phrase is the command
          answer   he asked something: the next phrase is the answer, no name needed
    """
    SPEECH_ON = 0.55     # VAD probability that counts as speech
    SPEECH_OFF = 0.35
    SURE = -0.40         # the local model is sure it heard the name (real log: your calls ≥ −0.28, room noise ≤ −0.50)

    def __init__(self) -> None:
        from openwakeword.vad import VAD

        self.frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=3000)
        models = [m for m in cfg("wake", "models", ["hey_jarvis"]) if m in ("hey_jarvis", "alexa", "hey_mycroft")]
        from oww_compat import download_models

        download_models(models)
        self.wake = Model(wakeword_models=models or ["hey_jarvis"], inference_framework="onnx")
        self.vad = VAD()
        self.agc = AGC(max_gain=float(cfg("voice", "max_gain", 20)))
        self.manual = threading.Event()
        self.todo: queue.Queue = queue.Queue()       # things that need the microphone for themselves (dictation)
        self.recent = collections.deque(maxlen=25)   # last 2 s of audio for wake-word verification
        self.mode, self.deadline, self.depth, self.retry = "idle", 0.0, 0, True
        self.gen = 0                                 # each new request cancels the previous one
        self.thinking = 0                            # gen of the request being worked on, 0 = none
        self.ducked = False
        self._utter_reset()

    # -- small helpers -----------------------------------------------------
    def _utter_reset(self) -> None:
        self.utter: list[np.ndarray] = []
        self.quiet, self.voiced = 0.0, 0
        self.woken = False            # this phrase contains the wake word
        self.over_speech = False      # it started while Jarvis was talking
        self.checked_at = 0.0         # seconds of the phrase already checked for an interruption

    def _callback(self, indata, frames, t, status) -> None:
        LEVEL["v"] = float(np.abs(indata).mean())   # for the HUD reactor; ~1 µs
        try:
            self.frames.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def flush(self) -> None:
        while not self.frames.empty():
            try:
                self.frames.get_nowait()
            except queue.Empty:
                break

    def speech_prob(self, chunk: np.ndarray) -> float:
        return float(self.vad.predict(chunk, frame_size=640))

    def base_status(self) -> str:
        return "recording" if self.mode != "idle" else "thinking" if self.thinking else "listening"

    def _status(self) -> None:
        if not speaker.speaking.is_set():
            set_status(self.base_status())

    def set_mode(self, mode: str, seconds: float = 0.0) -> None:
        self.mode, self.deadline = mode, time.time() + seconds
        if mode == "idle":
            if self.ducked:
                self.ducked = False
                duck_end_later()
        elif not self.ducked:
            self.ducked = True
            duck_start()              # music and video get quiet while we talk
        self._status()

    def cancel(self) -> None:
        """Drop whatever Jarvis is saying or thinking about."""
        self.gen += 1
        self.thinking = 0
        speaker.stop()

    def record_command(self, start_timeout: float = 7.0, silence: float | None = None, max_len: float = 25.0, prefix=None):
        """Record one utterance using the neural VAD (used by dictation)."""
        if silence is None:
            silence = float(cfg("voice", "end_silence", 0.7))
        chunks: list[np.ndarray] = []
        pre = collections.deque(maxlen=6)          # 0.48 s pre-roll
        started, quiet, voiced, t0 = False, 0.0, 0, time.time()
        self.vad.reset_states()
        if prefix:
            chunks, started = list(prefix), True
        while True:
            chunk = self.agc(self.frames.get())
            p = self.speech_prob(chunk)
            if not started:
                pre.append(chunk)
                voiced = voiced + 1 if p >= self.SPEECH_ON else 0
                if voiced >= 2:                     # 160 ms of real speech
                    started = True
                    chunks.extend(pre)
                elif time.time() - t0 > start_timeout:
                    return None
                continue
            chunks.append(chunk)
            quiet = 0.0 if p >= self.SPEECH_OFF else quiet + 0.08
            if quiet >= silence or len(chunks) * 0.08 > max_len:
                break
        return np.concatenate(chunks)

    # -- main loop ---------------------------------------------------------
    def run(self) -> None:
        """Keep listening forever: reopen the microphone if it disappears (headset unplugged etc.)."""
        while True:
            try:
                with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME, callback=self._callback):
                    log.info("Listening. Wake models: %s", list(self.wake.models))
                    self._status()
                    self.loop()
            except Exception:  # noqa: BLE001
                log.exception("Microphone stream failed; reopening in 3 s")
                set_status("starting")
                time.sleep(3)

    def loop(self, stop: threading.Event | None = None) -> None:
        pre = collections.deque(maxlen=8)          # 0.64 s before the first word: «Стоп» must not become «Топ»
        last_beat = 0.0
        while not (stop and stop.is_set()):
            try:
                chunk = self.agc(self.frames.get(timeout=5))
            except queue.Empty:
                if stop:
                    continue
                raise RuntimeError("no audio from the microphone for 5 s")
            now_t = time.time()
            if now_t - last_beat > 10:      # heartbeat for the supervisor (proves the audio loop is alive)
                last_beat = now_t
                (core.DATA / "heartbeat").write_text(str(int(now_t)))
            if self._exclusive():           # recorder / voice enrolment / dictation had the microphone
                self._utter_reset()
                pre.clear()
                self.recent.clear()
                continue
            talking = speaker.speaking.is_set()
            self.recent.append(chunk)

            # 1) «Эй, Джарвис» — works in any state, also while he talks or thinks
            scores = self.wake.predict(chunk)
            name, score = max(scores.items(), key=lambda kv: kv[1]) if scores else ("", 0.0)
            if score >= float(cfg("wake", "threshold", 0.4)) and self.mode != "command":
                if self.verify_wake(name, score):
                    self.called()
                    if self.utter:
                        self.woken = True   # the phrase goes on: «Эй, Джарвис, включи музыку» in one breath
                    else:
                        self.greet()        # the name is already finished
                self.wake.reset()

            # 2) collect a phrase
            p = self.speech_prob(chunk)
            if not self.utter:
                pre.append(chunk)
                self.voiced = self.voiced + 1 if p >= self.SPEECH_ON else 0
                if self.voiced >= 2:
                    self.utter = list(pre)
                    pre.clear()
                    self.quiet = 0.0
                    self.over_speech = talking
                else:
                    self._timeouts(talking)
                    continue
            else:
                self.utter.append(chunk)
                self.quiet = 0.0 if p >= self.SPEECH_OFF else self.quiet + 0.08

            dur = len(self.utter) * 0.08
            if talking and self.mode == "command" and dur >= 0.96 and self.quiet == 0.0:
                speaker.stop()              # you are already giving the command: no need to finish «Слушаю»
            # 3) interrupting: first get quieter at once, then decide whether it is really you
            if talking and self.mode != "command" and not self.woken and dur - self.checked_at >= 0.9 and self.quiet < 0.2:
                if self.checked_at == 0.0:
                    speaker.gain = 0.3
                self.checked_at = dur
                self.interruption(np.concatenate(self.utter), final=False)

            # 4) the phrase is over
            end_silence = 0.5 if (talking and self.mode == "idle") else min(0.7, float(cfg("voice", "end_silence", 0.7)))
            limit = 20.0 if (self.mode != "idle" or self.woken) else (4.5 if GAME["on"] else 10.0)
            if self.quiet >= end_silence or dur > limit + 0.5:
                audio, woken, over = np.concatenate(self.utter), self.woken, self.over_speech
                too_long = dur > limit
                self._utter_reset()
                self.vad.reset_states()
                self.phrase(audio, woken, over, too_long)
                speaker.gain = 1.0

    def _exclusive(self) -> bool:
        if core.RECORD_REQUEST.is_set():
            core.RECORD_REQUEST.clear()
            self.voice_record(core.RECORD_LANG.get("lang", "ru"))
        elif core.ENROLL_REQUEST.is_set():
            core.ENROLL_REQUEST.clear()
            self.enroll_voice()
        elif self.manual.is_set():
            self.manual.clear()
            self.cancel()
            sfx("wake", wait=False)
            self.set_mode("command", LISTEN_SECONDS)
            return False
        elif not self.todo.empty():
            self.todo.get()()
        else:
            return False
        self.set_mode("idle")
        return True

    def _timeouts(self, talking: bool) -> None:
        """Nobody said anything after «Слушаю» / after his question."""
        if self.mode == "idle":
            return
        if talking:                              # he is still speaking: the time to answer starts when he finishes
            self.deadline = max(self.deadline, time.time() + LISTEN_SECONDS)
        elif time.time() > self.deadline:
            if self.mode == "answer":
                core.PENDING.clear()
            else:
                sfx("cancel", wait=False, fallback=(440, 110))
            self.set_mode("idle")

    # -- deciding what a phrase is -------------------------------------------
    def called(self) -> None:
        """The wake word: instant signal, stop talking, the command follows."""
        self.cancel()
        sfx("wake", wait=False)
        self.depth, self.retry = 0, True
        self.set_mode("command", LISTEN_SECONDS)

    def greet(self) -> None:
        """Only the name was said: answer like a person — without closing the ears."""
        self.set_mode("command", LISTEN_SECONDS)
        if core.feature("wake_reply") and core.mode() != "quiet":
            macros = _plugin("macros")
            if not (macros and macros.play("wake")):
                speaker.say(random.choice(WAKE_REPLIES.get(core.mode(), WAKE_REPLIES["polite"])), "ru")

    def verify_wake(self, name: str, score: float) -> bool:
        audio = np.concatenate(list(self.recent)) if self.recent else None
        if audio is None:
            return False
        text, sure = spot(audio)
        words = re.findall(r"[\w'ʻ’]+", text)
        ok = any(is_jarvis(w) for w in words) or bool(re.search(r"(алекс|alex|mycroft|майкр)", text, re.I)) or score >= 0.8
        if ok and speaker.speaking.is_set() and own_words(text) >= 0.6 and score < 0.6:
            ok = False                      # he said his own name
        log.info("Wake phrase %s (%.2f) heard as %r %.2f -> %s", name, score, text, sure, "accepted" if ok else "ignored")
        return ok and self.owner(audio, "wake phrase")

    def owner(self, audio: np.ndarray, what: str, need: float | None = None) -> bool:
        """Voice lock: is this the owner speaking? (always yes until «Запомни мой голос»; stricter in games)"""
        if not core.feature("voice_lock"):
            return True
        ok, score = vp.is_owner(audio, strict=GAME["on"])
        if score is not None:
            core.CONFIG["_last_voice_score"] = score
            if need is not None:
                ok = score >= need
            log.info("Voice check (%s): %.2f -> %s", what, score, "owner" if ok else "someone else, ignored")
        return ok

    def interruption(self, audio: np.ndarray, final: bool) -> bool:
        """You spoke while he was talking. True if he stopped for you."""
        if not core.feature("barge_in"):
            return False
        text, sure = spot(audio)
        norm = core.normalize(text, "ru")
        if not norm or sure < -1.1 or own_words(text) >= 0.6:
            speaker.gain = 1.0
            return False
        idx = find_name(" ".join(re.findall(r"[\w'ʻ’-]+", text)))
        if _HUSH_START.match(norm) and self.owner(audio, "hush", need=0.12):
            log.info("Interrupted by %r", text)
            self.cancel()
            self.set_mode("idle")
            return True
        if idx is not None and sure >= -0.8 and self.owner(audio, "name over speech"):
            log.info("Interrupted by name: %r", text)
            self.called()
            if final:                       # the whole phrase is already here
                self.run_async(self.hear_command, audio, True)
            else:
                self.woken = True
            return True
        # any other words: only when we know your voice, and it is clearly you
        if vp.enrolled() and len(audio) >= SAMPLE_RATE and self.owner(audio, "over speech", need=0.36):
            log.info("Interrupted: %r", text)
            self.cancel()
            self.set_mode("command", 6)
            if final:
                self.run_async(self.hear_command, audio, False)
            return True
        speaker.gain = 1.0
        return False

    def phrase(self, audio: np.ndarray, woken: bool, over_speech: bool, too_long: bool) -> None:
        dur = len(audio) / SAMPLE_RATE
        if self.mode == "command" or woken:
            if woken and dur < 2.6:                # just «Эй, Джарвис»: answer at once, without the cloud
                text, sure = spot(audio)
                words = re.findall(r"[\w'ʻ’-]+", text)
                idx = find_name(" ".join(words))
                if idx is not None and sure >= self.SURE and len("".join(words[idx + 1:])) < 3:
                    self.greet()
                    return
            self.run_async(self.hear_command, audio, woken, over_speech)
            return
        if self.mode == "answer":
            if not self.owner(audio, "follow-up", need=0.18):     # e.g. TV or a friend answered instead of you
                return
            if speaker.speaking.is_set():                          # answered before he finished the question
                text, _ = spot(audio)
                if not text or own_words(text) >= 0.6:
                    return
                speaker.stop()
            self.run_async(self.hear_command, audio, False)
            return
        if speaker.speaking.is_set():
            self.interruption(audio, final=True)
            return
        if over_speech and dur < 1.0:
            return
        # idle: is it «Джарвис, …»?
        if too_long or dur < 0.4 or not core.feature("name_listening") or not cfg("cloud", "names_in_speech", True) or (
                GAME["on"] and not cfg("performance", "names_in_games", True)):
            return
        text, sure = spot(audio)
        words = re.findall(r"[\w'ʻ’-]+", text)
        idx = find_name(" ".join(words))
        if self.thinking and _HUSH_START.match(core.normalize(text, "ru")) and sure >= -0.8 and self.owner(audio, "hush", need=0.12):
            log.info("Cancelled while thinking by %r", text)
            self.cancel()
            self.set_mode("idle")
            return
        if idx is None:
            return
        log.info("Name heard (%.2f): %s", sure, text)
        if sure < -1.1 or not self.owner(audio, "name"):
            return
        if sure >= self.SURE and len("".join(words[idx + 1:])) < 3:     # just the name, clearly: don't wait for the cloud
            self.called()
            self.greet()
            return
        threading.Thread(target=self.confirm_name, args=(audio,), daemon=True, name="confirm-name").start()

    def confirm_name(self, audio: np.ndarray) -> None:
        """The local model isn't sure: the cloud must hear the name too. Until then nothing is interrupted."""
        try:          # no hint: on unclear sound Whisper repeats its hint as if you had said it
            res = _transcribe_cloud(audio, True, "ru", hint=False) if cloud.stt_enabled() else transcribe(audio, accurate=True)
        except Exception as e:  # noqa: BLE001
            log.warning("Name check failed: %s", e)
            return
        if find_name(" ".join(re.findall(r"[\w'ʻ’-]+", res[0]))) is None:
            log.info("Name not confirmed by the cloud (%r) — ignored", res[0])
            return
        self.depth, self.retry = 0, True
        sfx("wake", wait=False)
        self.run_async(self.hear_command, audio, True, False, res)

    # -- the slow part (cloud) runs beside the microphone ----------------------
    def run_async(self, fn, *args) -> None:
        self.cancel()
        gen = self.gen
        self.thinking = gen
        mode = self.mode
        self.mode = "idle"                     # from here on you can interrupt by name
        self._status()

        def go():
            try:
                fn(gen, mode, *args)
            except Exception:  # noqa: BLE001
                log.exception("voice request failed")
            finally:
                if self.thinking == gen:
                    self.thinking = 0
                if self.gen == gen and self.mode == "idle":
                    self.set_mode("idle")
                self._status()
        threading.Thread(target=go, daemon=True, name="voice-request").start()

    def hear_command(self, gen: int, mode: str, audio: np.ndarray, woken: bool, over_speech: bool = False, res=None) -> None:
        text, lang, reliable = res or transcribe(audio, accurate=True)
        if gen != self.gen:
            return
        try:   # how the voice sounded compared with the owner's usual voice (tired / stressed)
            from cognition import voice_mood
            voice_mood.note(audio)
        except Exception:  # noqa: BLE001 — mood is a nicety, never a reason to ignore a command
            log.exception("voice mood failed")
        if over_speech and not woken and own_words(text) >= 0.6:      # his own «Слушаю, сэр» came back
            self.set_mode("command", 6)
            return
        words = re.findall(r"[^\s]+", text)
        idx = find_name(" ".join(re.sub(r"[^\w'ʻ’-]", "", w) for w in words)) if words else None
        rest = " ".join(words[idx + 1:]).strip(" ,.!?—-") if idx is not None else text
        if idx is not None and len(rest) < 3:          # only the name
            self.greet()
            return
        if not text or not reliable or not re.search(r"\w", text):
            if mode == "answer":
                core.PENDING.clear()
            elif woken and not text:
                self.greet()
            elif self.retry:
                self.retry = False
                self.set_mode("command", LISTEN_SECONDS)
                speaker.say("Не расслышал, повторите.", lang or "ru")
            return
        core.emit({"type": "message", "role": "user", "text": text, "lang": lang, "source": "голос"})
        self.process(rest, lang, gen)

    def process(self, text: str, lang: str, gen: int | None = None) -> None:
        gen = self.gen if gen is None else gen
        if _DICTATE_START.search(core.normalize(text, lang)):
            self.todo.put(lambda: self.dictate(lang))
            return
        set_status("thinking")
        core.FOLLOWUP.clear()
        handle(text, lang, "голос", speak=True, echo=False, alive=lambda: gen == self.gen)
        if gen != self.gen:
            return
        if core.FOLLOWUP.is_set():       # he asked something: the next phrase is the answer (you may answer early)
            core.FOLLOWUP.clear()
            allowed = core.PENDING or core.feature("conversation")
            if allowed and self.depth < int(cfg("assistant", "conversation_turns", 4 if core.mode() == "friend" else 2)):
                self.depth += 1
                self.set_mode("answer", LISTEN_SECONDS)

    # -- learning your voice ---------------------------------------------------
    def enroll_voice(self) -> None:
        """«Запомни мой голос»: ~20 s of the owner's speech -> voiceprint."""
        need, limit = 20.0, 75.0
        speaker.say("Запоминаю ваш голос. Говорите со мной секунд двадцать: прочитайте текст в окне или расскажите, "
                    "как прошёл день. В конце можно сказать пару фраз тише, как вы иногда говорите.", "ru")
        speaker.wait(30)
        self.flush()
        set_status("recording")
        sfx("rec_start", fallback=(988, 120))
        voiced: list[np.ndarray] = []
        got, t0, last_emit = 0.0, time.time(), 0.0
        core.emit({"type": "enroll", "state": "on", "seconds": 0, "need": need})
        while got < need and time.time() - t0 < limit:
            try:
                chunk = self.agc(self.frames.get(timeout=1))
            except queue.Empty:
                continue
            if self.speech_prob(chunk) >= self.SPEECH_OFF:
                voiced.append(chunk)
                got += 0.08
            if time.time() - last_emit > 1:
                last_emit = time.time()
                core.emit({"type": "enroll", "state": "on", "seconds": round(got), "need": need})
        sfx("rec_stop", fallback=(660, 120))
        pieces = vp.enroll(np.concatenate(voiced)) if got >= 9 else 0
        core.emit({"type": "enroll", "state": "off", "ok": bool(pieces)})
        core.emit({"type": "settings"})
        if pieces:
            msg = "Готово, запомнил ваш голос. Теперь я слушаюсь только вас."
        else:
            msg = "Мало речи, не получилось. Скажите «Запомни мой голос» ещё раз и говорите подольше."
        core.emit({"type": "message", "role": "jarvis", "text": msg, "lang": "ru", "source": "голос"})
        speaker.say(msg, "ru")
        set_status("listening")

    # -- voice recorder ------------------------------------------------------
    def voice_record(self, lang: str) -> None:
        """Record everything until the user says "стоп" (or presses Stop in the app)."""
        rec_dir = core.DATA / "recordings"
        rec_dir.mkdir(exist_ok=True)
        stamp = core.now().strftime("%Y-%m-%d_%H-%M-%S")
        raw_path, wav_path = rec_dir / f"{stamp}.pcm", rec_dir / f"{stamp}.wav"
        speaker.say("Записываю. Скажите «стоп», когда закончите." if lang == "ru"
                    else "Yozib olyapman. Tugatish uchun «to'xtat» deng.", lang)
        speaker.wait()
        self.flush()
        winsound.Beep(988, 150)
        core.RECORD_STOP.clear()
        set_status("taping")
        core.emit({"type": "record", "state": "on", "name": wav_path.name})
        samples = 0
        cut_at = None
        utter: list[np.ndarray] = []
        utter_start = 0
        quiet = 0.0
        max_samples = int(float(cfg("recorder", "max_minutes", 180)) * 60 * SAMPLE_RATE)
        self.vad.reset_states()
        with open(raw_path, "wb") as raw:
            while not core.RECORD_STOP.is_set() and samples < max_samples:
                try:
                    chunk = self.frames.get(timeout=0.5)
                except queue.Empty:
                    continue
                raw.write(chunk.tobytes())
                chunk = self.agc(chunk)
                p = self.speech_prob(chunk)
                if p >= self.SPEECH_ON:
                    if not utter:
                        utter_start = max(0, samples - FRAME * 2)
                    utter.append(chunk)
                    quiet = 0.0
                elif utter:
                    utter.append(chunk)
                    quiet += 0.08
                samples += len(chunk)
                if utter and quiet >= 0.7:
                    dur = len(utter) * 0.08
                    audio = np.concatenate(utter)
                    utter = []
                    if dur <= 3.0:   # only short phrases can be the stop command
                        text, lg, reliable = transcribe(audio, accurate=False)
                        if reliable and _RECORD_STOP.search(core.normalize(text, lg)):
                            cut_at = utter_start
                            break
                if samples % (SAMPLE_RATE * 10) < FRAME:
                    core.emit({"type": "record", "state": "on", "seconds": samples // SAMPLE_RATE})
        # keep everything except the "стоп" itself
        keep = (cut_at if cut_at is not None else samples) * 2
        with open(raw_path, "rb") as f:
            pcm = f.read(keep)
        import wave

        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
        raw_path.unlink(missing_ok=True)
        seconds = len(pcm) // 2 // SAMPLE_RATE
        winsound.Beep(660, 150)
        mins, secs = divmod(seconds, 60)
        length = (f"{mins} мин {secs} сек" if mins else f"{secs} сек") if lang == "ru" else (f"{mins} daqiqa {secs} soniya" if mins else f"{secs} soniya")
        core.emit({"type": "record", "state": "off", "name": wav_path.name, "seconds": seconds})
        core.log_exchange("запись", lang, "[голосовая запись]", f"{wav_path.name}, {length}")
        speaker.say(f"Запись сохранена, длительность {length}." if lang == "ru" else f"Yozuv saqlandi, {length}.", lang)
        threading.Thread(target=self._transcribe_file, args=(wav_path, np.frombuffer(pcm, dtype=np.int16)), daemon=True).start()
        self.flush()
        set_status("listening")

    def _transcribe_file(self, wav_path: Path, pcm: np.ndarray) -> None:
        """Save a text transcript next to the recording (data/recordings/<name>.txt)."""
        if len(pcm) < SAMPLE_RATE:
            return
        try:
            if cloud.stt_enabled():
                pieces = cloud.transcribe_long(pcm, langs()[0] if len(langs()) == 1 else None)
            else:
                a = pcm.astype(np.float32) / 32768.0
                segments, info = whisper("main").transcribe(a, beam_size=5, vad_filter=True, condition_on_previous_text=True)
                pieces = [(s.start, s.text.strip()) for s in segments]
            lines = [f"[{int(st // 60):02d}:{int(st % 60):02d}] {tx}" for st, tx in pieces]
            wav_path.with_suffix(".txt").write_text("\n".join(lines), encoding="utf-8")
            core.emit({"type": "data", "file": wav_path.name})
        except Exception:  # noqa: BLE001
            log.exception("Transcript failed")

    def dictate(self, lang: str) -> None:
        path = core.DATA / "dictations" / f"{core.now():%Y-%m-%d_%H-%M}.md"
        speaker.say("Начинаю диктовку. Чтобы закончить, скажите: закончи диктовку." if lang == "ru"
                    else "Diktovka boshlandi. Tugatish uchun ayting: diktovkani tugat.", lang)
        speaker.wait()
        self.flush()
        set_status("recording")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"# Диктовка {core.now():%Y-%m-%d %H:%M}\n\n")
            silent = 0
            while silent < 5:
                audio = self.record_command(start_timeout=60, silence=1.5, max_len=30)
                if audio is None:
                    silent += 1
                    continue
                silent = 0
                text, lg, reliable = transcribe(audio, accurate=True)
                if not text or not reliable:
                    continue
                if len(text) < 40 and _DICTATE_STOP.search(core.normalize(text, lg)):
                    break
                f.write(text + "\n")
                f.flush()
                core.emit({"type": "message", "role": "user", "text": "📝 " + text, "lang": lg, "source": "диктовка"})
        speaker.say(f"Диктовка сохранена: {path.name}." if lang == "ru" else f"Diktovka saqlandi: {path.name}.", lang)


LISTENER: Listener | None = None


# ---------------------------------------------------------------------------
# Command handling (voice and text)
# ---------------------------------------------------------------------------

_STOP_WORDS = {"стоп", "хватит", "замолчи", "тихо", "отмена", "toxta", "toxtat", "jim", "bas", "yetarli"}
HISTORY: collections.deque = collections.deque(maxlen=200)


def _record(event: dict) -> None:
    if event.get("type") == "message":
        HISTORY.append(event)


core.subscribe(_record)


def handle(text: str, lang: str, source: str, speak: bool, echo: bool = True, alive=lambda: True) -> str:
    if echo:
        core.emit({"type": "message", "role": "user", "text": text, "lang": lang, "source": source})
    if core.normalize(text, lang) in _STOP_WORDS:
        speaker.stop()
        _stop_show()
        return "Хорошо." if lang == "ru" else "Xo'p."
    t0 = time.time()
    reply = core.process(text, lang, source)      # history, memory and learning are kept there, for every channel
    log.info("Reply [%s] in %.2fs: %s", lang, time.time() - t0, reply)
    if not alive():          # you interrupted while he was thinking
        log.info("Reply dropped: interrupted")
        speak = False
    if source != "голос":
        core.FOLLOWUP.clear()
    core.emit({"type": "message", "role": "jarvis", "text": reply, "lang": lang, "source": source,
               "secs": core.LAST_ACTION.get("secs")})
    if core.mode() == "quiet" and source != "голос-срочно":
        speak = False     # «Тихий» character: answers only on screen
    macros = _plugin("macros")
    if (speak and reply and core.feature("voice_replies") and macros and macros.active_pack()
            and len(reply) <= 60 and _ACK.match(reply) and macros.play("ok")):
        return reply   # a character voice pack answered with its own short phrase
    if speak and reply and core.feature("voice_replies"):
        speaker.say(reply, lang)
    return reply


# ---------------------------------------------------------------------------
# Desktop app: local web server + Edge app window
# ---------------------------------------------------------------------------

def open_app_window() -> None:
    hwnd = ctypes.windll.user32.FindWindowW(None, "Джарвис")
    if hwnd:                                   # already open (maybe hidden in the tray): just bring it back
        ctypes.windll.user32.ShowWindow(hwnd, 9)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        return
    if cfg("assistant", "native_window", True):
        try:
            import importlib.util
            if importlib.util.find_spec("webview"):
                pyw = Path(sys.executable).with_name("pythonw.exe")
                subprocess.Popen([str(pyw if pyw.exists() else sys.executable), str(BASE / "app_window.py")], cwd=str(BASE),
                                 creationflags=subprocess.CREATE_NO_WINDOW)
                return
        except Exception:  # noqa: BLE001
            log.exception("native window failed, using Edge")
    _open_edge_window()


def _open_edge_window() -> None:
    edge = next((p for p in [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ] if os.path.exists(p)), None)
    if edge:
        subprocess.Popen([edge, f"--app={APP_URL}", "--window-size=1100,760",
                          f"--user-data-dir={BASE / 'data' / 'app-profile'}", "--no-first-run"])
    else:
        os.startfile(APP_URL)


def _plugin(name: str):
    return sys.modules.get(f"jarvis_plugin_{name}")


def app_state() -> dict:
    apps_mod = _plugin("apps")
    return {
        "status": STATUS["state"],
        "tasks": core.load_json(core.DATA / "tasks.json", []),
        "reminders": sorted(core.load_json(core.DATA / "reminders.json", []), key=lambda r: r["at"]),
        "shortcuts": apps_mod.shortcuts() if apps_mod else {},
        "skills": [{"name": s.name, "module": s.module, "title": s.title, "examples": s.examples} for s in core.SKILLS],
        "history": core.read_history(80),          # the saved exchanges (voice, window, Telegram), not just this session
        "settings": {
            "assistant": core.CONFIG.get("assistant", {}),
            "wake": core.CONFIG.get("wake", {}),
            "tasks": core.CONFIG.get("tasks", {}),
            "voice": {k: v for k, v in core.CONFIG.get("voice", {}).items()},
            "weather": core.CONFIG.get("weather", {}),
            "performance": core.CONFIG.get("performance", {}),
            "email": {"address": core.CONFIG.get("email", {}).get("address", ""),
                      "configured": bool(core.CONFIG.get("email", {}).get("app_password"))},
            "telegram": {"configured": (core.DATA / "telegram.session").exists()},
        },
        "dictations": sorted((p.name for p in (core.DATA / "dictations").glob("*.md")), reverse=True)[:30],
        "recordings": [{"name": p.name, "size": p.stat().st_size,
                        "seconds": max(0, (p.stat().st_size - 44) // 2 // SAMPLE_RATE),
                        "has_text": p.with_suffix(".txt").exists()}
                       for p in sorted((core.DATA / "recordings").glob("*.wav"), reverse=True)[:50]]
                      if (core.DATA / "recordings").exists() else [],
        "recording_now": STATUS["state"] == "taping",
        "game": {"on": GAME["on"], "name": GAME["name"]},
        "mode": core.mode(),
        "profile": core.active_profile_id(),
        "voice_enrolled": vp.enrolled(),
        "notes": (sys.modules["jarvis_plugin_notes"].all_notes() if "jarvis_plugin_notes" in sys.modules else []),
    }


def connections_state() -> dict:
    import connections

    data = connections.load()
    wa_mod, tg_mod, cal_mod = _plugin("whatsapp"), _plugin("telegram"), _plugin("calendar_ics")
    api_id, api_hash = connections.telegram_creds()
    return {
        "email": [{**a, "has_password": bool(connections.get_secret(f"email:{a['address']}"))} for a in data["email"]],
        "telegram": {"api_id": api_id, "has_hash": bool(api_hash),
                     "connected": bool(tg_mod and tg_mod.connected())},
        "whatsapp": {"enabled": bool(data["whatsapp"].get("enabled")),
                     **({k: v for k, v in wa_mod.status().items() if k in ("state", "qr", "me")} if wa_mod else {})},
        "youtube": {"channels": data["youtube"].get("channels", []),
                    "has_key": bool(connections.get_secret("youtube:api_key"))},
        "calendar": {"count": len(cal_mod.ics_urls()) if cal_mod else 0},
        "ai": {"provider": data["ai"].get("provider", "local"), "model": data["ai"].get("model", "claude-opus-5-5"),
               "has_key": bool(connections.get_secret("anthropic:api_key"))},
    }


def connections_action(action: str, body: dict) -> dict:
    import connections

    data = connections.load()
    if action == "email_add":
        addr = body["address"].strip()
        host = body.get("imap_host") or _plugin("email_imap").guess_host(addr)
        connections.set_secret(f"email:{addr}", body.get("password", "").replace(" ", ""))
        data["email"] = [a for a in data["email"] if a["address"] != addr] + [
            {"address": addr, "imap_host": host, "name": body.get("name") or addr}]
        connections.save(data)
        res = _plugin("email_imap").check_box(data["email"][-1], limit=1)
        return {"ok": not res["error"], "message": res["error"] or f"Подключено. Непрочитанных: {res['unread']}"}
    if action == "email_delete":
        addr = body["address"]
        connections.set_secret(f"email:{addr}", "")
        data["email"] = [a for a in data["email"] if a["address"] != addr]
        connections.save(data)
        return {"ok": True}
    if action == "telegram_creds":
        data["telegram"]["api_id"] = str(body["api_id"]).strip()
        connections.save(data)
        connections.set_secret("telegram:api_hash", body["api_hash"].strip())
        return {"ok": True}
    if action == "telegram_code":
        r = _plugin("telegram").login_send_code(body["phone"].strip())
        return {"ok": True, "step": r}
    if action == "telegram_signin":
        r = _plugin("telegram").login_sign_in(code=body.get("code", "").strip(), password=body.get("password", ""))
        return {"ok": r.startswith("ok"), "step": r}
    if action == "telegram_logout":
        _plugin("telegram").logout()
        return {"ok": True}
    if action == "whatsapp":
        data["whatsapp"]["enabled"] = bool(body.get("enabled"))
        connections.save(data)
        wa = _plugin("whatsapp")
        wa.start_bridge() if data["whatsapp"]["enabled"] else wa.stop_bridge()
        return {"ok": True}
    if action == "whatsapp_logout":
        try:
            import requests

            requests.post("http://127.0.0.1:50779/logout", timeout=10)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True}
    if action == "youtube":
        data["youtube"]["channels"] = [c.strip() for c in body.get("channels", []) if c.strip()]
        connections.save(data)
        if body.get("api_key"):
            connections.set_secret("youtube:api_key", body["api_key"].strip())
        return {"ok": True, "message": _plugin("youtube").report("ru", detailed=False) or "Сохранено"}
    if action == "calendar_add":
        cal = _plugin("calendar_ics")
        cal.set_urls(cal.ics_urls() + [body["url"]])
        return {"ok": True, "message": cal.summary("ru") or "Сохранено"}
    if action == "calendar_clear":
        _plugin("calendar_ics").set_urls([])
        return {"ok": True}
    if action == "ai":
        data["ai"]["provider"] = body.get("provider", "local")
        if body.get("model"):
            data["ai"]["model"] = body["model"]
        connections.save(data)
        if body.get("api_key"):
            connections.set_secret("anthropic:api_key", body["api_key"].strip())
        if data["ai"]["provider"] == "claude":
            reply = _plugin("llm").ask("Скажи одной фразой, что ты подключён.", "ru", max_tokens=60, use_history=False)
            return {"ok": True, "message": reply}
        return {"ok": True}
    if action == "test":
        mods = {"email": ("email_imap", "summary"), "telegram": ("telegram", "summary"),
                "whatsapp": ("whatsapp", "summary"), "youtube": ("youtube", "report"), "calendar": ("calendar_ics", "summary")}
        mod, fn = mods[body["source"]]
        return {"ok": True, "message": getattr(_plugin(mod), fn)("ru") or "Не подключено"}
    raise ValueError(f"unknown action {action}")


def run_server() -> None:
    from aiohttp import web

    clients: set = set()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def broadcast(event: dict) -> None:
        msg = json.dumps(event, ensure_ascii=False)
        for ws in list(clients):
            asyncio.run_coroutine_threadsafe(ws.send_str(msg), loop)

    core.subscribe(broadcast)

    async def level_pump() -> None:
        """Mic loudness to the HUD ~12×/s — only while a window is open and not in a game."""
        while True:
            await asyncio.sleep(0.08)
            if clients and not GAME["on"]:
                msg = json.dumps({"type": "level", "v": round(LEVEL["v"], 1), "s": STATUS["state"]})
                for ws in list(clients):
                    try:
                        await ws.send_str(msg)
                    except Exception:  # noqa: BLE001
                        clients.discard(ws)

    async def index(_r):   # V3: one HUD screen, everything else lives in its drawers
        return web.FileResponse(BASE / "web" / "index.html", headers={"Cache-Control": "no-store"})

    async def to_index(_r):
        raise web.HTTPFound("/")

    # ---- V3 ---------------------------------------------------------------
    MEDIA = core.DATA / "media"
    SECRET_NAMES = {"groq": "groq:api_key", "gemini": "gemini:api_key", "telegram_bot": "telegram_bot:token",
                    "anthropic": "anthropic:api_key"}

    def _live_on() -> bool:
        try:
            import pcx
            return bool(pcx.LIVE["on"])
        except Exception:  # noqa: BLE001
            return False

    def v3_state() -> dict:
        import connections
        import remote_bot
        macros = _plugin("macros")
        bg = next(iter(sorted(MEDIA.glob("bg.*"))), None) if MEDIA.exists() else None
        try:
            import pcx
            focus = pcx.focus_active()
        except Exception:  # noqa: BLE001
            focus = False
        return {
            "persona": core.setting("assistant", "persona", "tactical"),
            "custom_persona": core.setting("assistant", "custom_persona", ""),
            "greeting_text": core.setting("assistant", "greeting_text", "Привет, сэр. Что будем делать?"),
            "startup_report": bool(core.setting("assistant", "startup_report", False)),
            "keys": {k: bool(connections.get_secret(v)) for k, v in SECRET_NAMES.items()},
            "cloud": cloud.status(),
            "remote": remote_bot.status(),
            "ui": {"accent": core.setting("ui", "accent", "cyan"), "glass": core.setting("ui", "glass", 0.72),
                   "dim": core.setting("ui", "dim", 0.55), "capsule_auto": bool(core.setting("ui", "capsule_auto", True)),
                   "capsule_style": core.setting("ui", "capsule_style", "wave"),
                   "bg": ({"url": f"/media/{bg.name}?v={int(bg.stat().st_mtime)}",
                           "kind": "video" if bg.suffix.lower() in (".mp4", ".webm") else "image"} if bg else None)},
            "packs": macros.packs() if macros else [], "pack": macros.active_pack() if macros else "",
            "focus": focus, "translate_live": _live_on(),
            "voice_enrolled": vp.enrolled(),
            "voice": {"engine": cfg("voice", "tts_engine_ru", "piper"), "piper": cfg("voice", "piper_voice_ru", "dmitri"),
                      "edge": cfg("voice", "edge_voice_ru", "ru-RU-DmitryNeural"), "edge_rate": cfg("voice", "edge_rate", "+0%"),
                      "edge_pitch": cfg("voice", "edge_pitch", "+0Hz"), "ui_sounds": bool(cfg("voice", "ui_sounds", True)),
                      "duck_level": float(cfg("voice", "duck_level", 0.15)),
                      "piper_voices": sorted(p.name.split("-")[1] for p in VOICES_DIR.glob("ru_RU-*-medium.onnx")),
                      "profiles": {k: v for k, v in (core.CONFIG.get("voices") or {}).items()}},
            "onboarded": bool(core.setting("ui", "onboarded", False)),
            "vpn": {"tunnel": core.setting("vpn", "tunnel", "")},
            "performance": {"game_mode": bool(core.setting("performance", "game_mode", True))},
            "weather": {"city": core.setting("weather", "city", "")},
        }

    async def ui_open(r):
        body = await r.json()
        core.emit({"type": "open", "panel": str(body.get("panel", "settings")), "section": str(body.get("section", ""))})
        return web.json_response({"ok": True})

    async def voice_preview(r):
        """The voice editor's «Прослушать»: one phrase in that voice, with the speed and tone on the sliders."""
        body = await r.json()
        lang = body.get("lang") if body.get("lang") in ("ru", "en", "ja") else "ru"
        sample = {"ru": "Здравствуйте. Так звучит мой голос с этими настройками.", "en": "Hello. This is how my voice sounds with these settings.",
                  "ja": "こんにちは。この設定では、私の声はこのように聞こえます。"}[lang]
        opts = {"engine": "piper" if body.get("engine") == "piper" else "edge", "voice": str(body.get("voice", ""))[:20],
                "speed": body.get("speed", 0), "tone": body.get("tone", 0)}
        speaker.stop()
        speaker.say(sample, lang, opts)
        return web.json_response({"ok": True})

    async def say(r):
        body = await r.json()
        lang = body.get("lang") if body.get("lang") in ("ru", "en", "ja") else "ru"
        speaker.say(str(body.get("text", ""))[:300] or "Проверка голоса, сэр.", lang)
        return web.json_response({"ok": True})

    async def v3_get(_r):
        return web.json_response(await asyncio.to_thread(v3_state))

    async def persona_set(r):
        body = await r.json()
        if body.get("persona") in ("tactical", "coder", "business", "quiet", "custom", "friend", "work", "polite"):
            core.save_setting("assistant", "persona", body["persona"])
        if "custom_persona" in body:
            core.save_setting("assistant", "custom_persona", str(body["custom_persona"])[:1500])
        core.emit({"type": "v3"})
        return web.json_response({"ok": True, "persona": core.setting("assistant", "persona", "tactical")})

    async def keys_set(r):
        """Save an API key into Windows Credential Manager (never returned back to the page)."""
        import connections
        body = await r.json()
        name = SECRET_NAMES.get(body.get("name", ""))
        if not name:
            raise web.HTTPBadRequest(text="unknown key")
        value = str(body.get("value", "")).strip()
        await asyncio.to_thread(connections.set_secret, name, value)
        msg = "Ключ удалён." if not value else "Ключ сохранён."
        ok = True
        if value and body["name"] in ("groq", "gemini"):
            try:
                await asyncio.to_thread(cloud.test, body["name"])
                msg = "Ключ работает."
            except Exception as e:  # noqa: BLE001
                ok, msg = False, f"Ключ сохранён, но проверка не прошла: {str(e)[:160]}"
        if body["name"] == "telegram_bot":
            import remote_bot
            await asyncio.to_thread(remote_bot.restart)
        core.emit({"type": "v3"})
        return web.json_response({"ok": ok, "message": msg})

    async def bg_upload(r):
        reader = await r.multipart()
        part = await reader.next()
        ext = os.path.splitext(part.filename or "")[1].lower()
        if ext not in (".mp4", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".gif"):
            raise web.HTTPBadRequest(text="Нужен файл .mp4, .webm, .jpg, .png или .webp")
        MEDIA.mkdir(parents=True, exist_ok=True)
        for old in MEDIA.glob("bg.*"):
            old.unlink(missing_ok=True)
        size, path = 0, MEDIA / f"bg{ext}"
        with open(path, "wb") as f:
            while chunk := await part.read_chunk(1 << 20):
                size += len(chunk)
                if size > 300 * 2**20:
                    f.close()
                    path.unlink(missing_ok=True)
                    raise web.HTTPRequestEntityTooLarge(max_size=300 * 2**20, actual_size=size)
                f.write(chunk)
        core.emit({"type": "v3"})
        return web.json_response({"ok": True})

    async def bg_delete(_r):
        for old in MEDIA.glob("bg.*") if MEDIA.exists() else []:
            old.unlink(missing_ok=True)
        core.emit({"type": "v3"})
        return web.json_response({"ok": True})

    async def media_file(r):
        path = MEDIA / os.path.basename(r.match_info["name"])
        if not path.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    async def goals_get(_r):
        """Goals, repeating reminders and app limits with today's usage — for the panels in the window."""
        today = core.now().strftime("%Y-%m-%d")
        return web.json_response({
            "goals": core.load_json(core.DATA / "goals.json", []), "repeats": core.load_json(core.DATA / "repeats.json", []),
            "limits": core.load_json(core.DATA / "limits.json", []),
            "usage": core.load_json(core.DATA / "limits_usage.json", {}).get(today, {}),
        })

    async def macros_get(_r):
        m = _plugin("macros")
        return web.json_response({"items": m.load(), "types": m.ACTION_TYPES, "packs": m.packs(), "pack": m.active_pack()})

    async def macros_save(r):
        item = await asyncio.to_thread(_plugin("macros").upsert, await r.json())
        return web.json_response(item)

    async def macros_delete(r):
        await asyncio.to_thread(_plugin("macros").delete, r.match_info["id"])
        return web.json_response({"ok": True})

    async def macros_run(r):
        m = _plugin("macros")
        item = next((x for x in m.load() if x["id"] == r.match_info["id"]), None)
        if not item:
            raise web.HTTPNotFound()
        reply = await asyncio.to_thread(m.run, item)
        core.emit({"type": "message", "role": "jarvis", "text": reply, "lang": "ru", "source": "макрос"})
        return web.json_response({"reply": reply})

    async def pack_set(r):
        body = await r.json()
        core.save_setting("voice", "pack", body.get("name", ""))
        core.emit({"type": "v3"})
        return web.json_response({"ok": True})

    async def translate(_r):
        import pcx
        try:
            reply = await asyncio.to_thread(pcx.translate_screen)
        except Exception as e:  # noqa: BLE001
            reply = f"Не получилось перевести: {str(e)[:160]}"
        return web.json_response({"reply": reply})

    async def translate_live(r):
        import pcx
        body = await r.json()
        reply = pcx.translate_live(bool(body.get("on")))
        core.emit({"type": "v3"})
        return web.json_response({"on": pcx.LIVE["on"], "reply": reply})

    async def remote_get(_r):
        import remote_bot
        return web.json_response(remote_bot.status())

    async def remote_set(r):
        import remote_bot
        body = await r.json()
        if "owner_id" in body:
            core.save_setting("remote", "owner_id", int(body["owner_id"] or 0))
        if "enabled" in body:
            core.save_setting("remote", "enabled", bool(body["enabled"]))
        await asyncio.to_thread(remote_bot.restart if core.setting("remote", "enabled", True) else remote_bot.stop)
        core.emit({"type": "v3"})
        return web.json_response(remote_bot.status())

    async def capsule(_r):
        import tray
        tray.toggle_capsule()
        return web.json_response({"ok": True})

    async def window_hide(_r):
        import tray
        return web.json_response({"ok": await asyncio.to_thread(tray.hide_window)})

    async def telemetry_get(_r):
        return web.json_response(await asyncio.to_thread(telemetry))

    async def pc_profile_get(_r):
        import pc_profile
        d = await asyncio.to_thread(pc_profile.load)
        if not d:
            return web.json_response({"scanned": False})
        return web.json_response({"scanned": True, "at": d.get("scanned_at"), "browser": d.get("browser", ""),
                                  "apps": len(d.get("installed") or d.get("apps") or []), "hardware": d.get("hardware", {})})

    async def pc_scan_post(_r):
        import pc_profile
        d = await asyncio.to_thread(pc_profile.scan)
        return web.json_response({"ok": True, "at": d.get("scanned_at"), "apps": len(d.get("installed") or d.get("apps") or [])})

    async def pc_index_get(_r):
        import pc_index
        d = await asyncio.to_thread(pc_index.info)
        d["running"] = pc_index.running()
        return web.json_response(d)

    async def pc_index_post(r):
        import pc_index
        body = await r.json() if r.can_read_body else {}
        if not body.get("confirm"):   # the owner must agree explicitly
            return web.json_response({"ok": False, "message": "Нужно согласие: confirm=true"}, status=400)
        started = pc_index.start_background()
        return web.json_response({"ok": started, "running": True,
                                  "message": "Изучаю имена файлов в фоне" if started else "Уже изучаю файлы"})

    async def activity_get(_r):
        import activity
        return web.json_response({"enabled": activity.enabled(), "running": activity.running(),
                                  "today": await asyncio.to_thread(activity.today_summary)})

    async def setup_get(_r):
        import setup_doctor
        checks = await asyncio.to_thread(setup_doctor.check_all)
        todo = [c for c in setup_doctor.missing_auto(checks) if c.fix.id != "reboot"]
        return web.json_response({
            "checked": setup_doctor.was_checked(),
            "attention": any(c.status in ("missing", "warn") for c in checks),
            "summary": setup_doctor.summary(checks),
            "auto_ids": [c.fix.id for c in todo],
            "auto_names": [c.fix.label for c in todo],
            "manual": [c.fix.label for c in checks if c.fix and c.fix.kind == "manual" and c.status == "missing"],
            "items": [{"id": c.id, "title": c.title, "status": c.status, "detail": c.detail,
                       "fix": (c.fix.label if c.fix else ""), "fix_id": (c.fix.id if c.fix else ""),
                       "size": (c.fix.size if c.fix else "")} for c in checks],
        })

    async def setup_run(r):
        import setup_doctor
        body = await r.json() if r.can_read_body else {}
        if not body.get("confirm"):   # downloads and installs only after the owner's yes
            return web.json_response({"ok": False, "message": "Нужно подтверждение: confirm=true"}, status=400)
        allowed = [i for i in body.get("ids", []) if i in setup_doctor.AUTO_STEPS and i != "reboot"]
        started = setup_doctor.run_all_in_background(allowed)
        return web.json_response({"ok": started, "running": True, "ids": allowed})

    async def setup_last(_r):
        import setup_doctor
        return web.json_response(setup_doctor.last_run())

    async def programs_get(_r):
        import programs
        return web.json_response({"items": await asyncio.to_thread(programs.list_programs, 24)})

    async def hud_get(_r):
        """Everything the 30 home widgets show, in one answer."""
        import hud_data

        def collect() -> dict:
            out = hud_data.snapshot()
            today = core.now().strftime("%Y-%m-%d")
            tasks = core.load_json(core.DATA / "tasks.json", [])
            out.update(status=STATUS["state"], game={"on": GAME["on"], "name": GAME["name"]}, mode=core.mode(),
                       tasks=[t for t in tasks if not t.get("done")] + [t for t in tasks if t.get("done")][-30:],
                       reminders=sorted(core.load_json(core.DATA / "reminders.json", []), key=lambda r: r["at"]),
                       goals=core.load_json(core.DATA / "goals.json", []), limits=core.load_json(core.DATA / "limits.json", []),
                       usage=core.load_json(core.DATA / "limits_usage.json", {}).get(today, {}),
                       history=[h for h in core.read_history(400) if h["user"] != "статус телевизора"][-12:], voice_enrolled=vp.enrolled(),
                       notes=len(sys.modules["jarvis_plugin_notes"].all_notes()) if "jarvis_plugin_notes" in sys.modules else 0)
            try:
                import pcx
                out["focus"] = {"until": pcx.FOCUS["until"] if pcx.focus_active() else 0, "closed": pcx.FOCUS["closed"]}
            except Exception:  # noqa: BLE001
                out["focus"] = {"until": 0, "closed": 0}
            import setup_doctor
            from cognition import emotion, personality, show
            out.update(first_run=not setup_doctor.wizard_done(), lite=bool(core.setting("ui", "hud_lite", False)),
                       show=show.public(), stage=personality.stage(), emotion=emotion.current())
            return out
        return web.json_response(await asyncio.to_thread(collect))

    async def robot_get(_r):
        from cognition import emotion
        return web.json_response(emotion.current())

    async def robot_poke(r):
        """The robot screen's buttons (pet, praise, joke, scold, sorry, sad): he feels it and says so."""
        _own_page(r)
        from cognition import emotion
        body = await r.json()
        st, line = emotion.poke(str(body.get("what", "")))
        if line:
            core.emit({"type": "message", "role": "jarvis", "text": line, "lang": "ru", "source": "робот"})
            if body.get("voice", True):
                speaker.say(line, "ru")
        return web.json_response({"emotion": st, "say": line})

    def _own_page(r) -> None:
        if r.headers.get("X-Jarvis") != "1":       # only this window's own buttons, never another web page
            raise web.HTTPForbidden()

    async def optimize_get(_r):
        import optimizer
        return web.json_response(await asyncio.to_thread(optimizer.analyze))

    async def optimize_post(r):
        import optimizer
        _own_page(r)
        body = await r.json()
        return web.json_response({"items": await asyncio.to_thread(optimizer.apply, [str(i) for i in body.get("ids", [])][:60])})

    async def optimize_undo(r):
        import optimizer
        _own_page(r)
        return web.json_response({"done": await asyncio.to_thread(optimizer.undo)})

    async def find_tv(r):
        import optimizer
        _own_page(r)
        return web.json_response(await asyncio.to_thread(optimizer.find_tv))

    async def wizard_done(r):
        import setup_doctor
        _own_page(r)
        setup_doctor.mark_wizard()
        setup_doctor.mark_checked()
        return web.json_response({"ok": True})

    async def hud_action(r):
        """One widget button. The custom header keeps other web pages from pressing it."""
        import hud_data
        if r.headers.get("X-Jarvis") != "1":
            raise web.HTTPForbidden()
        body = await r.json()
        try:
            out = await asyncio.to_thread(hud_data.action, str(body.get("kind", "")), body)
        except ValueError as e:
            return web.json_response({"ok": False, "reply": str(e)})
        except Exception as e:  # noqa: BLE001 — the widget shows what went wrong
            log.exception("hud action %s", body.get("kind"))
            return web.json_response({"ok": False, "reply": f"не получилось: {type(e).__name__}"})
        return web.json_response({"ok": True, **out})

    async def hud_icon(r):
        import programs
        name = r.match_info["id"]
        f = programs.ICONS / f"{name}.png"
        if not name.isalnum() or not f.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(f, headers={"Cache-Control": "max-age=86400"})

    def _own(r) -> None:
        if r.headers.get("X-Jarvis") != "1":
            raise web.HTTPForbidden()

    async def memory_facts_get(_r):
        from cognition import memory
        return web.json_response({"facts": await asyncio.to_thread(memory.facts),
                                  "habits": await asyncio.to_thread(memory.habits, 8)})

    async def memory_facts_post(r):
        from cognition import memory
        _own(r)
        body = await r.json()
        try:
            await asyncio.to_thread(memory.add_fact, str(body.get("text", "")))
        except ValueError as e:
            return web.json_response({"ok": False, "message": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def memory_facts_delete(r):
        from cognition import memory
        _own(r)
        await asyncio.to_thread(memory.delete_fact, int(r.match_info["id"]))
        return web.json_response({"ok": True})

    async def shield_get(_r):
        from cognition import shield
        p = await asyncio.to_thread(shield.ports)
        return web.json_response({"ports": p, "vpn": await asyncio.to_thread(shield.vpn)})

    async def docs_get(_r):
        from cognition import docs
        return web.json_response({"chunks": await asyncio.to_thread(docs.count), **docs.STATE})

    async def docs_index(r):
        from cognition import docs
        _own(r)
        body = await r.json() if r.can_read_body else {}
        if not body.get("confirm"):
            return web.json_response({"ok": False, "message": "Нужно согласие: confirm=true"}, status=400)
        started = docs.start_background()
        return web.json_response({"ok": started, "message": "Изучаю документы" if started else "Уже изучаю"})

    async def feedback_post(r):
        """👍 / 👎 under the last answer. Only this window can send it (custom header)."""
        from learning import store
        if r.headers.get("X-Jarvis") != "1":
            raise web.HTTPForbidden()
        body = await r.json()
        rating = 1 if str(body.get("rating")) in ("1", "up", "+1") else -1
        last = await asyncio.to_thread(core.read_history, 1)
        if not last:
            return web.json_response({"ok": False, "message": "Пока нечего оценивать."})
        last = last[-1]
        await asyncio.to_thread(store.add_feedback, last.get("user", ""), last.get("reply", ""), rating,
                                last.get("skill", ""), "оценка", 0.5 if rating < 0 else 0.0)
        return web.json_response({"ok": True, "message": "Спасибо, запомнил." if rating > 0 else "Понял, учту."})

    async def learning_metrics(_r):
        from learning import evaluation
        return web.json_response(await asyncio.to_thread(evaluation.metrics))

    async def learning_reflect(r):
        from learning import reflection
        if r.headers.get("X-Jarvis") != "1":
            raise web.HTTPForbidden()
        return web.json_response(await asyncio.to_thread(reflection.reflect))

    async def calendar_get(r):
        import datetime as dt
        cal = _plugin("calendar_ics")
        if not cal:
            return web.json_response({"count": 0, "events": []})
        days = max(1, min(14, int(r.query.get("days", 1))))
        today = dt.date.today()
        evs = await asyncio.to_thread(cal.events, today, days)
        out = [{"title": e["title"], "start": e["start"].isoformat(timespec="minutes") if hasattr(e["start"], "isoformat") else str(e["start"]),
                "all_day": bool(e["all_day"]), "location": e.get("location", "")} for e in evs[:40]]
        return web.json_response({"count": len(cal.ics_urls()), "events": out})

    async def history_clear(r):
        if r.headers.get("X-Jarvis") != "1":
            raise web.HTTPForbidden()
        import datetime as dt
        import shutil
        hf = core.HISTORY_FILE
        if hf.exists() and hf.stat().st_size:
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy(hf, hf.with_name(f"history.backup-{stamp}.jsonl"))
            hf.write_text("", encoding="utf-8")
        core.LAST_ACTION.update(skill="", tools="")
        return web.json_response({"ok": True, "message": "История очищена. Резервная копия сохранена в папке data."})

    async def skills_get(_r):
        return web.json_response({"count": len(core.SKILLS)})

    async def state(_r):
        return web.json_response(await asyncio.to_thread(app_state))

    async def history_get(r):
        """The saved history (data/history.jsonl), newest last. ?limit= up to 5000, ?q= filters by words."""
        try:
            limit = max(1, min(5000, int(r.query.get("limit", 300))))
        except ValueError:
            limit = 300
        q = r.query.get("q", "").strip().lower()

        def read():
            rows = core.read_history(100000 if q else limit)
            if q:
                rows = [h for h in rows if q in (h.get("user", "") + " " + h.get("reply", "")).lower()][-limit:]
            total = 0
            try:
                with core.HISTORY_FILE.open(encoding="utf-8") as f:
                    total = sum(1 for line in f if line.strip())
            except OSError:
                pass
            return {"items": rows, "total": total}
        return web.json_response(await asyncio.to_thread(read))

    async def show_get(_r):
        from cognition import show
        return web.json_response(show.public())

    async def show_audio(r):
        name = r.match_info["name"]
        if not re.fullmatch(r"jarvis_(?:about|report)_(?:ru|en|ja)\.mp3", name):
            raise web.HTTPNotFound()
        path = core.DATA / "media" / name
        if not path.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    async def command(r):
        body = await r.json()
        text = (body.get("text") or "").strip()
        lang = core.detect_lang(text)
        speak = bool(body.get("speak", cfg("voice", "speak_text_replies", False)))
        reply = await asyncio.to_thread(handle, text, lang, "текст", speak)
        return web.json_response({"reply": reply, "secs": core.LAST_ACTION.get("secs")})

    async def listen(_r):
        if LISTENER:
            LISTENER.manual.set()
        return web.json_response({"ok": True})

    async def voice_action(r):
        action = r.match_info["action"]
        if action == "enroll":
            core.ENROLL_REQUEST.set()
        elif action == "forget":
            vp.forget()
            core.emit({"type": "settings"})
        return web.json_response({"enrolled": vp.enrolled()})

    async def stop_speaking(_r):
        LISTENER.cancel() if LISTENER else speaker.stop()
        return web.json_response({"ok": True})

    async def tasks_add(r):
        body = await r.json()
        due = body.get("due")
        import datetime as dt

        task = _plugin("tasks").add_task(body["text"], dt.datetime.fromisoformat(due) if due else None,
                                         body.get("lang", "ru"))
        return web.json_response(task)

    async def tasks_patch(r):
        body = await r.json()
        changes = {k: v for k, v in body.items() if k in ("text", "done", "due")}
        if "due" in changes:
            changes.update(notified=False, pre_notified=False, last_nag=None)
        return web.json_response(_plugin("tasks").update_task(r.match_info["id"], **changes) or {})

    async def tasks_delete(r):
        _plugin("tasks").delete_task(r.match_info["id"])
        return web.json_response({"ok": True})

    async def shortcuts_add(r):
        body = await r.json()
        _plugin("apps").save_shortcut(body["name"], body["target"])
        return web.json_response({"ok": True})

    async def shortcuts_delete(r):
        _plugin("apps").delete_shortcut(r.match_info["name"])
        return web.json_response({"ok": True})

    async def reminders_delete(r):
        idx = int(r.match_info["idx"])
        with core.file_lock:
            items = sorted(core.load_json(core.DATA / "reminders.json", []), key=lambda x: x["at"])
            if 0 <= idx < len(items):
                items.pop(idx)
            core.save_json(core.DATA / "reminders.json", items)
        return web.json_response({"ok": True})

    async def settings(r):
        body = await r.json()
        core.save_setting(body["section"], body["key"], body["value"])
        if body["section"] == "wake" and LISTENER:
            pass
        return web.json_response({"ok": True})

    async def reload(_r):
        errors = await asyncio.to_thread(core.load_plugins)
        core.start_hooks()
        return web.json_response({"errors": errors, "count": len(core.SKILLS)})

    async def dictation(r):
        p = core.DATA / "dictations" / Path(r.match_info["name"]).name
        return web.Response(text=p.read_text(encoding="utf-8") if p.exists() else "", content_type="text/plain")

    async def record_start(_r):
        core.RECORD_LANG["lang"] = "ru"
        core.RECORD_STOP.clear()
        core.RECORD_REQUEST.set()
        return web.json_response({"ok": True})

    async def record_stop(_r):
        core.RECORD_STOP.set()
        return web.json_response({"ok": True})

    def _rec_path(name: str) -> Path:
        return core.DATA / "recordings" / Path(name).name

    async def recording_file(r):
        p = _rec_path(r.match_info["name"])
        return web.FileResponse(p) if p.exists() else web.Response(status=404)

    async def recording_delete(r):
        p = _rec_path(r.match_info["name"])
        p.unlink(missing_ok=True)
        p.with_suffix(".txt").unlink(missing_ok=True)
        core.emit({"type": "data", "file": p.name})
        return web.json_response({"ok": True})

    def _profiles_payload() -> dict:
        data = core.profiles()
        return {"profiles": data["profiles"], "active": data["active"], "effective": core.active_profile_id(),
                "auto": {k: v for k, v in core._overrides.items()}, "schedule": data.get("schedule", []),
                "auto_game": data.get("auto_game", True),
                "features": {k: {"title": v[0], "hint": v[1]} for k, v in core.FEATURES.items()},
                "builtin": list(core.DEFAULT_PROFILES)}

    async def profiles_get(_r):
        return web.json_response(_profiles_payload())

    async def profiles_action(r):
        import uuid

        body = await r.json() if r.can_read_body else {}
        action = r.match_info["action"]
        data = core.profiles()
        msg = ""
        if action == "activate":
            msg = await asyncio.to_thread(core.set_profile, body["id"])
            if msg:
                speaker.say(msg, "ru")
        elif action == "update":
            p = data["profiles"][body["id"]]
            for k in ("title", "icon", "personality", "say", "actions"):
                if k in body:
                    p[k] = body[k]
            if "feature" in body:
                p["features"][body["feature"]] = bool(body["value"])
            core.save_profiles(data)
        elif action == "new":
            pid = "custom_" + uuid.uuid4().hex[:6]
            base = data["profiles"].get(body.get("base", "normal"), data["profiles"]["normal"])
            data["profiles"][pid] = {**json.loads(json.dumps(base)), "title": body.get("title") or "Мой режим", "icon": "⭐"}
            core.save_profiles(data)
            msg = pid
        elif action == "delete":
            if body["id"] not in core.DEFAULT_PROFILES:
                data["profiles"].pop(body["id"], None)
                if data["active"] == body["id"]:
                    data["active"] = "normal"
                core.save_profiles(data)
        elif action == "reset":
            if body["id"] in core.DEFAULT_PROFILES:
                data["profiles"][body["id"]] = json.loads(json.dumps(core.DEFAULT_PROFILES[body["id"]]))
                core.save_profiles(data)
        elif action == "schedule":
            data["schedule"] = body["schedule"]
            core.save_profiles(data)
        elif action == "auto_game":
            data["auto_game"] = bool(body["value"])
            core.save_profiles(data)
        return web.json_response({"ok": True, "message": msg, **_profiles_payload()})

    async def notes_add(r):
        body = await r.json()
        sys.modules["jarvis_plugin_notes"].add_note(body["text"].strip())
        return web.json_response({"ok": True})

    async def notes_delete(r):
        mod = sys.modules["jarvis_plugin_notes"]
        notes = mod.all_notes()
        idx = int(r.match_info["idx"])
        if 0 <= idx < len(notes):
            notes.pop(idx)
            mod.save_all(notes)
        return web.json_response({"ok": True})

    async def open_folder(_r):
        os.startfile(str(BASE))
        return web.json_response({"ok": True})

    async def conn_state(_r):
        return web.json_response(await asyncio.to_thread(connections_state))

    async def conn_action(r):
        body = await r.json() if r.can_read_body else {}
        try:
            result = await asyncio.to_thread(connections_action, r.match_info["action"], body)
        except RuntimeError as e:          # a plain sentence for the owner (e.g. a Telegram login refusal)
            log.warning("connection action %s: %s", r.match_info["action"], e)
            result = {"ok": False, "message": str(e)[:400]}
        except Exception as e:  # noqa: BLE001
            log.exception("connection action failed")
            result = {"ok": False, "message": str(e)[:300]}
        core.emit({"type": "connections"})
        return web.json_response(result)

    async def ws_handler(r):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(r)
        clients.add(ws)
        try:
            async for _ in ws:
                pass
        finally:
            clients.discard(ws)
        return ws

    app = web.Application()
    app.add_routes([
        web.get("/", index), web.get("/classic", to_index), web.get("/hud", to_index), web.get("/api/telemetry", telemetry_get),
        web.get("/api/v3", v3_get), web.post("/api/persona", persona_set), web.post("/api/keys", keys_set),
        web.post("/api/bg", bg_upload), web.delete("/api/bg", bg_delete), web.get("/media/{name}", media_file),
        web.get("/api/goals", goals_get), web.get("/api/macros", macros_get), web.post("/api/macros", macros_save),
        web.delete("/api/macros/{id}", macros_delete), web.post("/api/macros/{id}/run", macros_run),
        web.post("/api/pack", pack_set), web.post("/api/translate", translate), web.post("/api/translate/live", translate_live),
        web.get("/api/remote", remote_get), web.post("/api/remote", remote_set),
        web.post("/api/capsule", capsule), web.post("/api/window/hide", window_hide), web.post("/api/say", say), web.post("/api/voice/preview", voice_preview), web.post("/api/ui/open", ui_open),
        web.get("/api/state", state), web.post("/api/command", command),
        web.get("/api/history", history_get), web.get("/api/show", show_get), web.get("/api/show/audio/{name}", show_audio),
        web.get("/api/robot", robot_get), web.post("/api/robot/poke", robot_poke),
        web.get("/api/pc-profile", pc_profile_get), web.post("/api/pc-scan", pc_scan_post),
        web.get("/api/pc-index", pc_index_get), web.post("/api/pc-index", pc_index_post),
        web.get("/api/activity", activity_get), web.get("/api/programs", programs_get),
        web.get("/api/skills", skills_get),
        web.get("/api/calendar", calendar_get), web.post("/api/history/clear", history_clear),
        web.post("/api/feedback", feedback_post), web.get("/api/learning/metrics", learning_metrics),
        web.get("/api/memory/facts", memory_facts_get), web.post("/api/memory/facts", memory_facts_post),
        web.delete("/api/memory/facts/{id}", memory_facts_delete),
        web.get("/api/shield", shield_get), web.get("/api/docs", docs_get), web.post("/api/docs/index", docs_index),
        web.post("/api/learning/reflect", learning_reflect),
        web.get("/api/hud", hud_get), web.get("/api/optimize", optimize_get), web.post("/api/optimize", optimize_post),
        web.post("/api/optimize/undo", optimize_undo), web.post("/api/find-tv", find_tv), web.post("/api/setup/done", wizard_done),
        web.post("/api/hud/action", hud_action), web.get("/api/hud/icon/{id}", hud_icon),
        web.get("/api/setup", setup_get), web.post("/api/setup/run", setup_run), web.get("/api/setup/last", setup_last),
        web.post("/api/listen", listen), web.post("/api/stop", stop_speaking),
        web.post("/api/voice/{action}", voice_action),
        web.post("/api/tasks", tasks_add), web.patch("/api/tasks/{id}", tasks_patch),
        web.delete("/api/tasks/{id}", tasks_delete), web.post("/api/shortcuts", shortcuts_add),
        web.delete("/api/shortcuts/{name}", shortcuts_delete), web.delete("/api/reminders/{idx}", reminders_delete),
        web.post("/api/settings", settings), web.post("/api/reload", reload),
        web.get("/api/dictation/{name}", dictation), web.post("/api/open-folder", open_folder),
        web.get("/api/connections", conn_state), web.post("/api/connections/{action}", conn_action),
        web.get("/api/profiles", profiles_get), web.post("/api/profiles/{action}", profiles_action),
        web.post("/api/notes", notes_add), web.delete("/api/notes/{idx}", notes_delete),
        web.post("/api/record/start", record_start), web.post("/api/record/stop", record_stop),
        web.get("/api/recording/{name}", recording_file), web.delete("/api/recording/{name}", recording_delete),
        web.get("/ws", ws_handler), web.static("/static", BASE / "web"),
    ])
    runner = web.AppRunner(app, access_log=None)
    loop.run_until_complete(runner.setup())
    loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", APP_PORT).start())
    log.info("App server on %s", APP_URL)
    loop.create_task(level_pump())
    loop.run_forever()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global LISTENER
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", 50777))
    except OSError:
        # already running: just open the window
        if "--app" in sys.argv:
            open_app_window()
        sys.exit(0)
    log.info("Starting Jarvis")
    # stay out of the way of games and other apps: below-normal CPU priority
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    errors = core.load_plugins()
    if errors:
        log.error("Plugin errors: %s", errors)
    import memory
    memory.warm_up()   # semantic memory: load the small CPU model and index notes in the background
    threading.Thread(target=run_server, daemon=True, name="server").start()
    try:  # if a game is already running, load speech models straight onto the CPU
        _path, _fs = _foreground_process()
        if cfg("performance", "game_mode", True) and _is_game(_path, _fs):
            GAME.update(on=True, name=os.path.basename(_path))
            core.CONFIG["_game_mode"] = True
    except Exception:  # noqa: BLE001
        pass
    if not cloud.stt_enabled() or cloud.local_fallback():
        whisper("main")  # local speech models only when the cloud is off (or as a fallback)
        if len(langs()) > 1:
            whisper("lid")
    else:
        log.info("Cloud mode: speech recognition on Groq, nothing loaded on the GPU")
        if cfg("cloud", "local_spotting", True):
            threading.Thread(target=whisper, args=("spot",), daemon=True, name="spot-load").start()
    LISTENER = Listener()
    threading.Thread(target=LISTENER.run, daemon=True, name="listener").start()
    threading.Thread(target=game_watcher, daemon=True, name="game-watcher").start()
    core.start_hooks()  # greeting, task watcher, reminders, LLM warm-up

    import keyboard

    keyboard.add_hotkey(cfg("hotkey", "text_box", "ctrl+alt+j"), open_app_window)
    if "--app" in sys.argv:
        open_app_window()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Jarvis crashed")
        raise
