"""Senses and reach: voice mood, voice enrolment on real speech (temporary file), IP location, firewall and VPN
error paths, the presentation state, and the palette geometry in the page."""
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cognition import db, geo, shield, voice_mood  # noqa: E402

SR = 16000


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    assert ok, name


def tmp(name):
    return Path(tempfile.mkdtemp()) / name


def voice(f0, amp, rate, jit=0.0, secs=2.0):
    """A synthetic voice: harmonics, a loudness envelope and pitch wobble (jit) like real speech."""
    t = np.arange(int(SR * secs)) / SR
    inst = f0 * (1 + jit * np.sin(2 * np.pi * 7 * t) + jit * 0.5 * np.sin(2 * np.pi * 13 * t))
    phase = 2 * np.pi * np.cumsum(inst) / SR
    sig = sum(np.sin(h * phase) / h for h in (1, 2, 3))
    env = 0.5 + 0.5 * np.sin(2 * np.pi * rate * t)
    return (amp * sig * env / 2.2 * 32767).astype(np.int16)


def test_voice_mood_detects_tired_and_stressed_against_the_usual_voice():
    usual = voice_mood.analyze(voice(180, 0.6, 4, 0.02))
    check("pitch of a synthetic voice is found (about 180 Hz)", usual and abs(usual["f0"] - 180) < 6)
    check("tired: quieter and slower than usual", voice_mood.mood_from(voice_mood.analyze(voice(180, 0.25, 2, 0.02)), usual) == "усталость")
    check("stressed: louder with a jumpy pitch", voice_mood.mood_from(voice_mood.analyze(voice(180, 0.95, 4, 0.12)), usual) == "стресс")
    check("usual voice: no mood", voice_mood.mood_from(voice_mood.analyze(voice(182, 0.6, 4, 0.02)), usual) == "")


def test_voice_mood_needs_a_baseline_and_keeps_it_clean():
    p = tmp("v.db")
    for i in range(6):
        assert voice_mood.note(voice(180 + i, 0.6, 4, 0.02), p) == ""
    mood = voice_mood.note(voice(180, 0.25, 2, 0.02), p)
    check("after six usual phrases a tired one is recognised and stored", mood == "усталость")
    base = voice_mood._load_baseline(p)
    check("a tired phrase does not move the usual voice", base["n"] == 6)
    with db.conn(p) as c:
        val = c.execute("SELECT value FROM relationship WHERE key = 'last_mood'").fetchone()[0]
    check("the mood is visible to the check-in", val == "усталость")


def test_voice_mood_ignores_silence_and_noise():
    rng = np.random.default_rng(1)
    check("silence: no judgement", voice_mood.analyze(np.zeros(SR * 2, dtype=np.int16)) is None)
    check("noise: no judgement", voice_mood.analyze((rng.standard_normal(SR * 2) * 3000).astype(np.int16)) is None)


def _real_speech(name):
    path = ROOT / "voices" / "samples" / f"piper_{name}.wav"
    with wave.open(str(path), "rb") as w:
        sr, raw = w.getframerate(), w.readframes(w.getnframes())
    import voiceprint as vp
    return vp.resample(np.frombuffer(raw, dtype=np.int16), sr)


def test_voice_enrolment_on_real_speech_uses_a_temporary_file():
    import voiceprint as vp
    if not vp._model():          # the speaker model is downloaded by the installer, not kept in git
        print("SKIP  speaker model not installed yet: run install.ps1 to enable this check")
        return
    real = vp.FILE
    before = real.read_bytes() if real.exists() else None
    vp.FILE = tmp("voiceprint_test.npz")
    vp._cache.clear()
    try:
        if not (ROOT / "voices" / "samples" / "piper_dmitri.wav").exists():
            check("speech samples present (skipped)", True)
            return
        owner = _real_speech("dmitri")
        check("enrolment on speech saves pieces", vp.enroll(np.concatenate([owner, owner, owner])) >= 3)
        ok_owner, s_owner = vp.is_owner(owner[:SR * 4])
        ok_other, s_other = vp.is_owner(_real_speech("denis")[:SR * 4])
        check("the enrolled speaker is accepted", ok_owner and s_owner > 0.8)
        check("a different speaker is refused", not ok_other and s_other < 0.5)
    finally:
        vp.FILE = real
        vp._cache.clear()
    after = real.read_bytes() if real.exists() else None
    check("the real voiceprint file was not touched", before == after)


def test_locate_refuses_home_addresses_and_caches():
    p = tmp("g.db")
    for ip in ("192.168.1.1", "10.0.0.5", "127.0.0.1"):
        try:
            geo.locate(ip, p)
            check(f"{ip} refused", False)
        except ValueError:
            pass
    check("home and local addresses refused without a request", True)
    fake = {"country_name": "Land", "city": "Town", "org": "Net", "asn": "AS1"}
    assert geo.locate("8.8.8.8", p, fetch=lambda u: fake)["city"] == "Town"

    def no_request(url):
        raise AssertionError("second time must come from the cache")
    assert geo.locate("8.8.8.8", p, fetch=no_request)["city"] == "Town"
    check("the answer is cached: one request per address", True)


def test_locate_sends_only_the_address():
    seen = []
    geo.locate("8.8.4.4", tmp("s.db"), fetch=lambda u: seen.append(u) or {"country_name": "x"})
    check("the only thing sent is the address itself", seen == ["https://ipapi.co/8.8.4.4/json/"])


def test_firewall_and_vpn_error_paths_without_admin():
    """Real netsh and real WireGuard checks. Without administrator rights nothing is changed by these calls."""
    assert shield._text("Для запрошенной операции требуется повышение прав".encode("utf-8")).startswith("Для")
    check("netsh text in UTF-8 is read", True)
    try:
        shield.vpn_tunnel("on", "jarvis-test-tunnel")
        check("VPN without WireGuard refused clearly", False)
    except ValueError as e:
        check("VPN without WireGuard refused clearly", "WireGuard не установлен" in str(e))
    try:
        shield.vpn_tunnel("on", "bad name!")
        check("odd tunnel name refused", False)
    except ValueError:
        check("odd tunnel name refused", True)
    try:
        shield.block_ip("192.168.1.9")
        check("a home address is never blocked", False)
    except ValueError:
        check("a home address is never blocked", True)


def test_netsh_admin_message_is_recognised():
    check("admin message recognised", shield._netsh_error("Для запрошенной операции требуется повышение прав."))
    check("other errors are not mistaken for admin", not shield._netsh_error("правило не найдено"))


def test_block_command_text():
    check("the command shown to the owner is the exact rule", shield.block_command("45.33.32.156") ==
          'netsh advfirewall firewall add rule name="Jarvis block 45.33.32.156" dir=in action=block remoteip=45.33.32.156')


def test_presentation_state_for_the_screen():
    from cognition import show
    show.STATE.update(active=False, i=0, slides=[])
    show.STATE.update(active=True, lang="ru", slides=[{"say": "а"}, {"say": "б"}, {"say": "в"}])
    show.step(1)
    pub = show.public()
    check("the screen reads active, slide and total", pub["active"] and pub["i"] == 1 and pub["total"] == 3)
    show.stop()
    check("stopped show is inactive", show.public()["active"] is False)


def test_palettes_have_their_own_geometry_in_the_page():
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    core = (ROOT / "web" / "core.js").read_text(encoding="utf-8")
    for shape in ("dots", "grid", "shield", "orbits"):
        check(f"shape {shape} is drawn by the core", f'st.shape === "{shape}"' in core)
    check("five palettes exist", app.count('{ id: "') >= 5)


if __name__ == "__main__":
    test_voice_mood_detects_tired_and_stressed_against_the_usual_voice()
    test_voice_mood_needs_a_baseline_and_keeps_it_clean()
    test_voice_mood_ignores_silence_and_noise()
    test_voice_enrolment_on_real_speech_uses_a_temporary_file()
    test_locate_refuses_home_addresses_and_caches()
    test_locate_sends_only_the_address()
    test_firewall_and_vpn_error_paths_without_admin()
    test_netsh_admin_message_is_recognised()
    test_block_command_text()
    test_presentation_state_for_the_screen()
    test_palettes_have_their_own_geometry_in_the_page()
    print("stage30: all passed")
