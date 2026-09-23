"""dictator STT: local, private speech-to-text via whisper.cpp.

Nothing about your code leaves the machine. Recording uses sox (`rec`)
with silence auto-stop, so you press to talk, speak, and it ends itself.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import core

def _resolve_model_dir() -> Path:
    """Where the whisper models live.

    Models are large (the turbo model alone is 1.6GB) and are not specific to
    this product, so a machine that already downloaded them for something else
    should not download them again. The order is: an explicit override, our own
    directory if it already has models, then a voicebridge install's directory,
    then our own for a fresh download.

    Set DICTATOR_MODELS to force a location."""
    env = os.environ.get("DICTATOR_MODELS")
    if env:
        return Path(env).expanduser()
    own = core.STATE_DIR / "models"
    if any(own.glob("ggml-*.bin")):
        return own
    shared = Path.home() / ".voicebridge" / "models"
    if any(shared.glob("ggml-*.bin")):
        return shared
    return own


MODEL_DIR = _resolve_model_dir()

# Which engine answered the last transcription. Recorded rather than
# inferred, because the routing has changed more than once and a
# history full of guesses about it would be worse than no history.
LAST_ENGINE = ""
# English-only models are more accurate for English; the multilingual model
# handles Hindi/Hinglish and everything else.
_EN_MODELS = ["ggml-small.en.bin", "ggml-base.en.bin"]
# Hindi mixed with English needs a MULTILINGUAL model. The .en models are not
# merely worse at it, they cannot represent it: asked for English they render
# Hindi speech as an English translation, so you say one sentence and a
# different one appears.
# turbo FIRST, and this reverses an earlier decision that was measured on the
# wrong thing. small won on synthesised speech; on Krish's actual voice, same
# sentence, the gap is not close:
#
#   said  "ab ek asli Hinglish line bol ke dekho, mila jula, English words
#          ke saath"
#   small  ab aslee english laeen bolke deko mila jula english vrts ke saath
#   turbo  ab asali english line bol ke dekho mila jula english words ke saath
#
# small mangles both halves ("vrts" for "words", "laeen" for "line"); turbo
# gets the Hindi AND keeps the English words as English. It costs about 2s
# more per utterance, which is worth it for a transcript you do not have to
# repair by hand.
#
# The lesson worth keeping: TTS audio is not a proxy for a real voice, and
# every conclusion drawn from it here needed re-testing on a real recording.
_ML_MODELS = ["ggml-large-v3-turbo.bin", "ggml-small.bin", "ggml-base.bin"]

# Whisper has no token for Hindi written in English letters, so no language
# flag can ask for it. What it does have is a prompt, which conditions the
# style of what follows, and a prompt written in the script you want is enough
# to pull the output into that script. Measured 3 times out of 3 on this
# machine, with a prompt sharing no words with the test sentences.
#
# Deliberately written in the register it is steering: casual work Hinglish,
# Latin letters, English technical words left as English. That last part is
# what stops "deployment" coming back as a transliterated Devanagari spelling.
# Density, not length, is what makes this work. The previous prompt put this
# after a paragraph of English coding vocabulary, so only a quarter of it was
# Hinglish and the steer lost to the acoustic prior. Pure romanized Hinglish,
# with the coding words woven in rather than bolted on in English.
_HINGLISH_STEER = (
    "haan bhai main abhi us feature pe kaam kar raha hoon. thoda sa refactor "
    "karna padega phir main PR bhej deta hoon. kal meeting mein discuss kar "
    "lenge tab tak tum review kar lena. arey yaar ye wala test fail ho raha "
    "hai, mujhe samajh nahi aa raha kyun. tum zara dekh lo aur batao kya "
    "karna chahiye. maine kal raat ko hi wo change push kar diya tha, branch "
    "pe rebase bhi kar diya hai."
)
_MULTI_MODELS = ["ggml-small.bin", "ggml-base.bin"]
MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/"
    "resolve/main/ggml-base.en.bin"
)


def _best_model(names=None):
    for name in (names or _EN_MODELS):
        p = MODEL_DIR / name
        if p.exists():
            return p
    return MODEL_DIR / (names or _EN_MODELS)[-1]


MODEL = _best_model()

# Vocabulary biasing (whisper `initial_prompt`): conditions the decoder toward
# the words this tool actually hears, so coding jargon, tool names, and git
# terms transcribe correctly instead of as near-homophones. whisper uses it
# for conditioning only, it is never echoed into the transcript. A natural
# sentence in the expected register works better than a bare word list. A
# user vocabulary file (~/.dictator/vocab) is appended when present.
_BASE_PROMPT = (
    "A spoken instruction to a coding assistant in the terminal. It may "
    "mention code, files, functions, variables, git, commit, rebase, pull "
    "request, branch, terminal, session, prompt, and tools like Claude, "
    "Claude Code, GitHub, npm, Python, JavaScript, whisper, Kokoro, and "
    "voicebridge."
)


def whisper_prompt() -> str:
    """The initial_prompt: the base coding vocabulary plus any user terms in
    ~/.dictator/vocab (one phrase per line), capped to whisper's window."""
    extra = ""
    try:
        extra = (core.STATE_DIR / "vocab").read_text().strip()
        extra = " ".join(extra.split())
    except Exception:
        pass
    p = (_BASE_PROMPT + " " + extra).strip() if extra else _BASE_PROMPT
    # The Hinglish steer is deliberately NOT applied, and this is a retraction.
    #
    # The idea was sound and it worked on synthetic speech: a prompt written in
    # romanized Hinglish pulls the output into Latin script, measured 3 times
    # out of 3. On the user's own voice it does the opposite of help. Same
    # audio, same model, one word spoken:
    #
    #     -l auto, no steer  ->  "English"
    #     -l auto, + steer   ->  "hing lish."
    #
    # It splits words and mangles them, because it biases the decoder toward
    # Hindi phonetics for audio that is not Hindi. Script control is worth
    # nothing if the words underneath are wrong, and a change that helps on
    # generated speech while hurting on real speech is a change that was
    # measured on the wrong thing.
    #
    # Script belongs to the MODEL, not to a prompt. See the plan: a natively
    # romanizing checkpoint is the real fix.
    # No Hinglish steer, and this is the second retraction of it.
    #
    # A steer weak enough to leave English alone let Devanagari through. A
    # steer strong enough to stop the leaking turned spoken English into
    # Hindi: he said "are you able to understand everything now and rebase
    # this branch" and got "iss branj ko rebase kar do aur fit test chala
    # dena". There is no setting of one static prompt that serves both, because
    # the prompt applies to an utterance before anyone knows what language it
    # was.
    #
    # So the script is imposed afterwards instead of asked for. See roman.py.
    return p[:800]   # whisper caps ~224 tokens; stay well under


def language() -> str:
    """What the user asked for: "english" or "hinglish"."""
    try:
        want = (core.STATE_DIR / "lang").read_text().strip().lower()
    except Exception:
        return "english"
    return "hinglish" if want.startswith("hing") else "english"


# Set for the duration of one fallback, when the English path has already
# proved the audio is not English. A module flag rather than an argument
# because stt_lang_mode is read from several places inside a single
# transcription, and only one hold is ever in flight at a time.
_force_multilingual = False


def stt_lang_mode() -> "tuple":
    """(model_path, whisper -l arg).

    English stays the default and stays on the .en model, which is the most
    accurate for English and cannot mis-detect English as something else.

    Hinglish needs the opposite of both. It needs the multilingual model,
    because the .en models translate Hindi into English rather than writing it
    down. And it needs `auto` rather than `hi`, because `hi` produces
    Devanagari, which is unusable in a terminal or an editor. Neither flag can
    ask for Hindi-in-English-letters, because Whisper has no such language;
    the prompt does that part."""
    if _force_multilingual or language() == "hinglish":
        return _best_model(_ML_MODELS), "auto"
    return _best_model(_EN_MODELS), "en"


# Hotkey daemons (skhd) run with a minimal PATH that often lacks Homebrew,
# so we look in the usual brew locations too, not just PATH.
_BREW_BINS = ("/opt/homebrew/bin", "/usr/local/bin")


def _find(name: str) -> str:
    p = shutil.which(name)
    if p:
        return p
    for d in _BREW_BINS:
        cand = os.path.join(d, name)
        if os.path.exists(cand):
            return cand
    return ""


def whisper_bin() -> str:
    for name in ("whisper-cli", "whisper-cpp", "main"):
        p = _find(name)
        if p:
            return p
    return ""


# --- warm resident model (issue #2) ------------------------------------------
# Spawning whisper-cli per utterance reloads the ~half-GB model and dlopen's
# the BLAS/Metal/CPU backends every time: measured ~2.1s cold vs ~0.3s against
# a warm whisper-server. So we keep one server resident (mirrors the Kokoro
# TTS server) and fall back to the CLI whenever the server isn't available,
# so nothing breaks on installs without whisper-server.
# Per-uid default so two accounts on one Mac don't collide on the whisper port
# (any HTTP reply there reads as "up"). VB_STT_PORT wins; the server is launched
# with --port WHISPER_PORT, so server and client always agree.
WHISPER_PORT = int(os.environ.get("VB_STT_PORT") or (7000 + os.getuid() % 1000))


def whisper_server_bin() -> str:
    return _find("whisper-server")


def whisper_up() -> bool:
    try:
        r = subprocess.run(
            ["curl", "-s", "-m", "2", "-o", "/dev/null", "-w", "%{http_code}",
             f"http://127.0.0.1:{WHISPER_PORT}/"],
            capture_output=True, timeout=5)
        # Any HTTP reply means the server is listening (root may 404/501).
        return r.stdout.strip() not in (b"", b"000")
    except Exception:
        return False


def _server_matches() -> bool:
    """Is the server that is listening the one we actually want?

    The model and the -l flag are baked in when whisper-server launches, and
    nothing in the per-request payload can override them. So a server started
    weeks ago keeps answering with whatever it was started with.

    This check exists because it did exactly that: a server launched on 21 Aug
    with ggml-small.en and -l en was still serving a month later, while the
    language had since been switched to Hinglish. `vb lang` had become a no-op
    on the warm path, every utterance went to an English-only 244M model, and
    nothing anywhere said so. The Hinglish it produced was that model
    phonetically approximating a language it cannot represent."""
    want_model, want_lang = stt_lang_mode()
    try:
        pid = int((core.STATE_DIR / "stt.pid").read_text().strip())
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return False
    return want_model.name in cmd and f"-l {want_lang}" in cmd


def _stop_whisper_server() -> None:
    """Stop the one we started, and anything else holding the port."""
    try:
        pid = int((core.STATE_DIR / "stt.pid").read_text().strip())
        os.kill(pid, 15)
    except Exception:
        pass
    try:
        subprocess.run(["pkill", "-f", f"whisper-server.*--port {WHISPER_PORT}"],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    for _ in range(20):
        if not whisper_up():
            return
        time.sleep(0.15)


def ensure_whisper_server(wait_s: float = 20.0) -> bool:
    """Start a resident whisper-server if the RIGHT one isn't already up.

    Returns False (and callers fall back to the CLI) if the binary or model
    is missing, so this is always safe to call."""
    if whisper_up():
        if _server_matches():
            return True
        # Wrong model or wrong language. Replacing it costs one reload; not
        # replacing it costs every transcription until someone reboots.
        core.log("whisper server is running the wrong model, restarting it")
        _stop_whisper_server()
    srv = whisper_server_bin()
    model, lang = stt_lang_mode()
    if not srv or not model.exists():
        return False
    try:
        p = subprocess.Popen(
            [srv, "-m", str(model), "-l", lang,
             "--port", str(WHISPER_PORT), "-nt"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        (core.STATE_DIR / "stt.pid").write_text(str(p.pid))
    except Exception as e:
        core.log(f"whisper server autostart failed: {e}")
        return False
    import time as _t
    t0 = _t.time()
    while _t.time() - t0 < wait_s:
        if whisper_up():
            core.log("whisper server autostarted")
            return True
        _t.sleep(0.4)
    return False


def _clean_text(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cleaned = " ".join(lines)
    for tag in ("[BLANK_AUDIO]", "(blank audio)", "[ Silence ]", "[silence]"):
        cleaned = cleaned.replace(tag, "")
    return cleaned.strip()


# whisper's own `-l auto` costs a FULL SECOND EXTRA on every utterance,
# because it runs the encoder twice: once to decide the language and once to
# transcribe. Measured on a 12.4 second hold with turbo: 2447ms of encode over
# 2 runs for auto, against 1230ms over 1 run for a pinned language, and the
# transcript is identical. The tiny model answers the same question in 0.2s.
_DETECT_MODEL = "ggml-tiny.bin"

# Below this the detector is guessing, and a wrong pin is worse than no pin:
# forcing Hindi on English audio triggered a temperature fallback storm that
# took 8.9 seconds. When unsure, fall back to letting whisper decide.
MIN_DETECT_P = 0.5


def audio_seconds(wav: str) -> float:
    try:
        import wave
        with wave.open(wav) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


def audio_ctx_for(secs: float) -> int:
    """How much of whisper's 30 second window this utterance actually needs.

    whisper.cpp encodes a full 30 seconds however long you spoke, and the
    encoder is 85 percent of the bill. Measured on a 12.4 second hold with
    turbo: 4554ms at the default 1500 frames, 1840ms at 700.

    Undershooting is dangerous, not merely lossy. At 600 frames (12 seconds,
    just under the audio) the same clip lost a word, and smaller still sends
    the decoder into a repetition loop that takes LONGER than full context. So
    this rounds up and adds margin, and returns the default when it cannot
    tell how long the audio is."""
    if secs <= 0:
        return 0
    frames = int(secs / 0.02) + 80
    return min(1500, max(200, frames))


def detect_language(wav: str) -> "tuple[str, float]":
    """(language code, probability) from the tiny model, or ("", 0.0).

    Cheap enough to be worth it: 0.2s against the 1.2s that whisper's own
    detection adds to every transcription."""
    m = MODEL_DIR / _DETECT_MODEL
    wb = whisper_bin()
    if not wb or not m.exists():
        return "", 0.0
    try:
        r = subprocess.run([wb, "-m", str(m), "-f", wav, "-dl", "-nt"],
                           capture_output=True, text=True, timeout=30)
        out = r.stdout + r.stderr
        hit = re.search(r"detected language:\s*([a-z]{2,3})\s*\(p\s*=\s*([0-9.]+)", out)
        if not hit:
            return "", 0.0
        return hit.group(1), float(hit.group(2))
    except Exception as e:
        core.log(f"stt: language detect failed: {e}")
        return "", 0.0


def pinned_language(wav: str, want: str) -> str:
    """Replace `auto` with a real language when we can work one out cheaply."""
    if want != "auto":
        return want
    code, p = detect_language(wav)
    if not code or p < MIN_DETECT_P:
        core.log(f"stt: language unclear ({code or 'none'} p={p:.2f}), "
                 f"letting whisper decide")
        return "auto"
    core.log(f"stt: detected {code} (p={p:.2f}) in the tiny model")
    return code


def _transcribe_server(wav: str) -> "tuple[str, float] | None":
    """Transcribe against the warm whisper-server. Returns (text, conf) with
    conf = mean per-word probability (same 0..1 scale the CLI path derives
    from token probabilities), or None if the server didn't answer so the
    caller falls back to the CLI."""
    if not whisper_up():
        return None
    # A server that is up is not the same as a server that is right. It is
    # started for one model and one language and cannot be told otherwise per
    # request, so sending Hinglish to an English one returns
    # "[NON-ENGLISH SPEECH]" and sending English to a multilingual one is
    # slower and less accurate. This check existed and was only consulted when
    # starting a server, which was harmless only for as long as nothing ever
    # started one.
    if not _server_matches():
        core.log(f"stt: warm server is not the one this needs "
                 f"({stt_lang_mode()[0].name}), using the CLI")
        return None
    # A server is started with one audio context and cannot be told otherwise
    # per request, so it always encodes the full 30 second window. For a short
    # utterance the CLI wins even after paying process start and model load.
    # Measured on a 12.4 second hold: 2.90s through the CLI with the window
    # sized and the language pinned, against 4.25s through this server, and
    # 3.16s through a server pinned to the same language.
    secs = audio_seconds(wav)
    if 0 < secs < 25:
        core.log(f"stt: {secs:.1f}s of audio, the CLI can size the window "
                 f"and this server cannot")
        return None
    try:
        r = subprocess.run(
            ["curl", "-s", "-m", "30", f"http://127.0.0.1:{WHISPER_PORT}/inference",
             "-F", f"file=@{wav}", "-F", "response_format=verbose_json",
             # vocabulary biasing (pure win). The anti-hallucination knobs
             # (no_fallback, aggressive no_speech) were DROPPING real speech
             # in noisy / far-mic conditions: no_fallback disables the
             # temperature retry that RECOVERS hard audio, so whisper returned
             # empty and the prompt silently never sent. Let it fall back.
             "-F", "prompt=" + whisper_prompt()],
            capture_output=True, timeout=35)
        data = json.loads(r.stdout.decode("utf-8", "replace"))
    except Exception as e:
        core.log(f"whisper server inference failed: {e}")
        return None
    text = _clean_text(data.get("text", "") or "")
    segs = data.get("segments", []) or []
    # Prefer per-word probabilities, but the server (started with -nt) usually
    # omits the words array, which left conf=0.0 and SILENTLY DISABLED the
    # confidence noise-gate on the warm path (loud TV/chatter could inject).
    # Fall back to the segment avg_logprob, which is always present: exp() of
    # it is a 0..1 confidence on the same scale the token-prob path produces.
    import math
    probs = [w.get("probability", 0.0)
             for seg in segs for w in seg.get("words", [])
             if isinstance(w.get("probability", None), (int, float))]
    if probs:
        conf = sum(probs) / len(probs)
    else:
        lps = [math.exp(seg["avg_logprob"]) for seg in segs
               if isinstance(seg.get("avg_logprob"), (int, float))]
        conf = sum(lps) / len(lps) if lps else 0.0
    return text, conf


def have_deps() -> dict:
    return {
        "whisper": whisper_bin(),
        "rec": _find("rec"),
        "model": str(MODEL) if MODEL.exists() else "",
    }


def ensure_model() -> bool:
    if MODEL.exists():
        return True
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    core.log(f"downloading model to {MODEL}")
    try:
        subprocess.run(
            ["curl", "-fSL", "-o", str(MODEL), MODEL_URL],
            check=True,
        )
        return MODEL.exists()
    except Exception as e:
        core.log(f"model download failed: {e}")
        return False


# ---- who has the microphone -------------------------------------------------
# The indicator must never be able to say "closed" while a mic is open, so it
# does not ask us: it checks CoreAudio for whether a device is capturing, and
# checks this lock for whether the open device is OURS. The kernel drops an
# flock when the holder dies, including on SIGKILL, so an orphaned recorder
# cannot leave a stale "we own the mic" claim behind. That is the whole reason
# it is a lock and not a flag file.
_MIC_LOCK = core.STATE_DIR / "mic.lock"


def _hold_mic_lock_while(proc) -> None:
    """Hold the lock for exactly as long as `proc` is recording.

    Runs on a daemon thread so no caller has to change. Best-effort: failing to
    take the lock must never stop a recording, it only means the indicator
    falls back to hiding, which is the safe direction.
    """
    import fcntl
    import threading

    def keep():
        try:
            core.STATE_DIR.mkdir(parents=True, exist_ok=True)
            f = open(_MIC_LOCK, "w")
        except Exception:
            return
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            f.close()          # somebody else is recording; not ours to claim
            return
        try:
            while proc.poll() is None:
                time.sleep(0.1)
        finally:
            try:
                fcntl.flock(f, fcntl.LOCK_UN)
            finally:
                f.close()

    threading.Thread(target=keep, daemon=True).start()


def record(wav: str, max_secs: int = 30,
           silence_stop: float = 2.0) -> bool:
    """Record mic to a 16kHz mono wav, stopping after silence.

    Waits for you to start speaking, then ends after `silence_stop`
    seconds of quiet. Whisper wants 16kHz mono, so we record that directly.
    """
    rec = _find("rec")
    if not rec:
        core.log("record: sox `rec` not found")
        return False
    # Start on the very first faint sound (0.05s @ 0.3%) so the opening word
    # isn't eaten by speech detection; stop after `silence_stop` of quiet.
    # `norm` levels it up so you don't have to be loud.
    cmd = [
        rec, "-q", "-c", "1", "-r", "16000", "-b", "16", wav,
        "trim", "0", str(max_secs),
        "silence", "1", "0.05", "0.3%", "1", str(silence_stop), "1.5%",
        "norm", "-1",
    ]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        _hold_mic_lock_while(p)
        p.wait()
        return os.path.exists(wav) and os.path.getsize(wav) > 1000
    except Exception as e:
        core.log(f"record failed: {e}")
        return False


def record_start(wav: str, max_secs: int = 30,
                 silence_stop: float = 2.0):
    """Start a recording as a Popen (same gating as record()); None on fail.

    Lets the caller poll/terminate mid-recording, which vb talk uses to cut
    a silent wait short when Claude's reply lands.
    """
    rec = _find("rec")
    if not rec:
        core.log("record_start: sox `rec` not found")
        return None
    # No `norm` here: it buffers the whole file until the end, which breaks
    # mid-recording did-speech-start checks that poll the wav's size.
    cmd = [
        rec, "-q", "-c", "1", "-r", "16000", "-b", "16", wav,
        "trim", "0", str(max_secs),
        "silence", "1", "0.05", "0.3%", "1", str(silence_stop), "1.5%",
    ]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        _hold_mic_lock_while(p)
        return p
    except Exception as e:
        core.log(f"record_start failed: {e}")
        return None


def record_hold(wav: str, max_secs: int = 120):
    """Record until told to stop. For push-to-talk, where YOU are the boundary.

    `record` and `record_start` both hand the boundaries to sox: `silence`
    trims leading quiet and ends the take after a pause. That is right when
    nobody is holding a key, and wrong here in two ways. Trimming the lead can
    eat the first word, because you start speaking as you press. And stopping
    on a pause cuts you off mid-thought every time you stop to think, while
    still holding the key down to say you have not finished.

    So: no silence effect at all. It records from the instant it starts until
    the caller kills it, which is the moment you let go."""
    rec = _find("rec")
    if not rec:
        core.log("record_hold: sox `rec` not found")
        return None
    cmd = [rec, "-q", "-c", "1", "-r", "16000", "-b", "16", wav,
           "trim", "0", str(max_secs)]
    try:
        # sox's stderr is kept, not discarded. When a recording comes back
        # empty, sox has almost always said why ("can't open input device",
        # a permission refusal, a device that vanished), and throwing that
        # away turns a one-line answer into an afternoon. The same mistake in
        # the key listener is what made the Accessibility problem invisible.
        errf = open(core.STATE_DIR / "rec.err", "w")
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=errf)
        _hold_mic_lock_while(p)
        return p
    except Exception as e:
        core.log(f"record_hold failed: {e}")
        return None


def live_level(wav: str, tail_ms: int = 200) -> float:
    """Cheap 0..1 loudness of the last ~tail_ms of a 16k mono s16le recording,
    for the live mic meter. Reads only the tail and does the RMS in-process
    (no sox), so it's fine to call every ~0.15s in the capture loop."""
    import array
    try:
        with open(wav, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            nbytes = min(size - 44, int(16000 * 2 * tail_ms / 1000))
            if nbytes <= 0:
                return 0.0
            nbytes -= nbytes % 2
            f.seek(size - nbytes)
            raw = f.read(nbytes)
        a = array.array("h")
        a.frombytes(raw)
        if not a:
            return 0.0
        rms = (sum(x * x for x in a) / len(a)) ** 0.5
        # sqrt curve: loudness is perceived roughly non-linearly, so a soft
        # voice still visibly moves the meter instead of barely twitching.
        return min(1.0, (rms / 6000.0) ** 0.5)
    except Exception:
        return 0.0


# Parakeet cannot write Devanagari, and for Hinglish that turns out to be a
# feature rather than a limitation. Measured on this machine:
#
#   said     "is branch ko rebase kar do phir tests chala dena"
#   whisper  इस ध्राँच को रिबेस कर दो फिर टेस्ट्स चला देना
#   parakeet Is bronchku rebase kardu fair tests chaladena
#
# Whisper mangles every English technical word into Devanagari (टेस्ट्स for
# "tests"), which is the failure the vendor we are chasing documents as its
# own. Parakeet leaves them exactly as English because it has no other script
# to put them in, and phonetically romanises the Hindi around them. For a
# coding tool the English terms ARE the payload, so this trade is the right
# way round. Its Hindi spelling is worse; its Hindi is still readable.
_PARAKEET = MODEL_DIR / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"


def parakeet_ready() -> bool:
    return _PARAKEET.exists() and bool(_find("parakeet-cli"))


def _parakeet(wav: str) -> str:
    """Transcribe with Parakeet. Empty string if it cannot, so the caller
    falls back rather than failing."""
    exe = _find("parakeet-cli")
    if not exe or not _PARAKEET.exists():
        return ""
    try:
        r = subprocess.run([exe, "-m", str(_PARAKEET), "-f", wav, "-np"],
                           capture_output=True, text=True, timeout=120)
        return " ".join((r.stdout or "").split())
    except Exception as e:
        core.log(f"parakeet failed: {e}")
        return ""


# Below this many words per second, Parakeet has dropped speech rather than
# transcribed it. Measured on real holds: a working English pass runs about
# 2.7, turbo on the same Hinglish audio about 2.1, and Parakeet failing on that
# audio 0.96. Anything under this is not a slow talker, it is missing content.
MIN_WORDS_PER_SEC = 1.5
MIN_SECS_TO_JUDGE = 3.0


def _too_little(text: str, wav: str) -> bool:
    """Did it return far less speech than the audio contains?

    The other two signatures catch Parakeet FUSING Hindi into blobs. They do
    not catch it doing something worse and less obvious: inventing fluent
    English that has nothing to do with what was said. A real hold of
    "jiske liye mujhe tumhari ek Hinglish line chahiye..." came back as
    "This is the English line. Bobi Bhikkhullah or Mare is English accuracy."
    Every word of that is ordinary English, so nothing about its shape is
    suspicious. What gives it away is that twelve seconds of speech produced
    twelve words."""
    try:
        import wave
        with wave.open(wav) as w:
            secs = w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return False
    if secs < MIN_SECS_TO_JUDGE:
        return False            # too short to tell a pause from a failure
    n = len(re.findall(r"[A-Za-z']+", text or ""))
    return (n / secs) < MIN_WORDS_PER_SEC


def _parakeet_lost(text: str) -> bool:
    """Did Parakeet fail because the sentence had no English in it?

    It has no Hindi at all, which is a feature when you are speaking Hinglish:
    it leaves the English technical words as English instead of burying them in
    Devanagari. But given a sentence with NO English to anchor on, it spells
    the Hindi phonetically and runs the words together:

        "kya tumko sab kuch samajh aa raha hai"
          -> "Kyatungko Sabkuch Samach Arahahe"

    That signature is what this looks for. Real speech, English or Hinglish,
    does not produce a run of very long tokens."""
    words = [w for w in (text or "").split() if w.isalpha()]
    if len(words) < 3:
        return False
    # Two signatures together, because either alone has false positives.
    # Long tokens: it fuses syllables it cannot segment ("Arahahe").
    mean_len = sum(len(w) for w in words) / len(words)
    # Title Case on every word: with no language model for what it is hearing,
    # it treats each fused blob as a proper noun. Ordinary speech, English or
    # Hinglish, does not come back capitalised word by word.
    capped = sum(1 for w in words[1:] if w[:1].isupper()) / max(1, len(words) - 1)
    return mean_len >= 6.0 and capped >= 0.6


def _romanise(text: str) -> str:
    """Devanagari out, English letters in, when the user asked for Hinglish.

    Here rather than in one caller, because every voice path in the product
    goes through transcribe_ex: dictation, voice-on, agent mode, wake word,
    the phone bridge and the remote relay. Putting it in dictate.py meant the
    key got readable Hinglish and every other way of talking to the tool still
    got Devanagari, which is the same product behaving two ways depending on
    how you reached it."""
    # Also when we fell back here on our own: the audio turned out not to be
    # English, so it needs the same treatment as if Hinglish had been asked
    # for. Without this the automatic path produces correct words in a script
    # the user cannot paste into a terminal, which reads as a worse failure
    # than the one it just fixed.
    if not text or (language() != "hinglish" and not _force_multilingual):
        return text
    try:
        from . import roman
        return roman.to_latin(text) if roman.has_devanagari(text) else text
    except Exception:
        return text        # never lose a transcript to the cosmetic step


def transcribe(wav: str) -> str:
    """Run whisper.cpp on a wav and return cleaned text."""
    return transcribe_ex(wav)[0]


def transcribe_ex(wav: str) -> "tuple[str, float]":
    # Hinglish goes to Parakeet when it is available, for the reason above: it
    # keeps the English technical words as English instead of burying them in
    # Devanagari, and for a coding tool those words are the whole point.
    # Parakeet on the ENGLISH path only.
    #
    # It is faster than whisper and more verbatim (whisper quietly substitutes
    # plausible words and drops repetitions). But it has no Hindi at all, so on
    # a mixed sentence it fuses the Hindi into blobs: "asli" came back as
    # "Busley", "ke saath" as "kesaty". Turbo gets both halves right on the same
    # audio, so Hinglish goes there instead and Parakeet keeps the job it is
    # actually best at.
    global LAST_ENGINE, _force_multilingual
    _force_multilingual = False
    try:
        return _transcribe_ex(wav)
    finally:
        _force_multilingual = False


def warm(background: bool = True) -> None:
    """Get the resident model up, so the first hold is not the slow one.

    ensure_whisper_server was written, commented and then never called from
    anywhere. Every transcription took the cold CLI path, paying process
    start and a 1.6GB model load on every single utterance, and the only
    reason it ever looked fast was that a separate voicebridge install
    happened to be running a server on the same port. Measured on a ten
    second hold: 3.89s cold against 2.8s warm.

    NOT called automatically any more, and the measurement is why. A server is
    started with one audio context and cannot be told otherwise per request,
    so it always encodes the full 30 second window, while the CLI can size the
    window to the utterance. On a 12.4 second hold the CLI is faster even
    after paying process start and model load, so the server is declined for
    anything under 25 seconds, which is very nearly every dictation. Leaving
    one resident then costs memory and contends for the GPU for no benefit:
    the same hold measured 3.2s with no server running and 5.8s with one up.

    Kept for long audio and for callers that want it, and available as
    `dictator warm`. Started in the background because warming can take twenty
    seconds and nothing should wait for it."""
    def go():
        try:
            ensure_whisper_server()
        except Exception as e:
            core.log(f"stt: could not warm the model: {e}")
    if background:
        import threading
        threading.Thread(target=go, daemon=True).start()
    else:
        go()


def _transcribe_ex(wav: str) -> "tuple[str, float]":
    global LAST_ENGINE, _force_multilingual
    if language() != "hinglish" and parakeet_ready():
        got = _parakeet(wav)
        if got and not _parakeet_lost(got) and not _too_little(got, wav):
            LAST_ENGINE = "parakeet"
            return got, 0.9
        if got:
            # Parakeet only drops speech like this when the audio is not
            # English, so falling back to the English model would just swap
            # one wrong answer for "[NON-ENGLISH SPEECH]". Go multilingual for
            # this one utterance regardless of what the setting says.
            _force_multilingual = True
            core.log(f"stt: parakeet dropped speech, falling back to "
                     f"{stt_lang_mode()[0].name}: {got[:60]!r}")

    """Transcribe and also return whisper's confidence (mean token
    probability, 0..1). Real directed speech scores ~0.7+; background
    chatter, mumble, and noise score low, which lets callers drop them."""
    # Fast path: the warm resident server (issue #2). Falls through to the
    # CLI if it's not up or didn't answer, so behavior is identical otherwise.
    served = _transcribe_server(wav)
    if served is not None:
        # The model the request actually goes to, not the module level
        # default. MODEL is resolved once at import from the English list, so
        # naming it here reported small.en for work that turbo had done.
        LAST_ENGINE = f"server:{stt_lang_mode()[0].name}"
        return _romanise(served[0]), served[1]
    LAST_ENGINE = f"cli:{stt_lang_mode()[0].name}"
    wb = whisper_bin()
    model, lang = stt_lang_mode()
    if not wb or not model.exists():
        core.log("transcribe: missing whisper binary or model")
        # Otherwise the user talks and NOTHING happens, with no clue why.
        core.surface_error(
            "transcribe", "Speech recognition isn't set up.",
            hint="Run setup on the Mac to install it.")
        return "", 0.0
    base = wav + ".vbout"
    lang = pinned_language(wav, lang)
    cmd = [wb, "-m", str(model), "-f", wav, "-nt", "-np", "-l", lang,
           "--prompt", whisper_prompt(),   # same vocabulary biasing as the server
           "-ojf", "-of", base]   # -ojf: full JSON includes token probabilities
    ac = audio_ctx_for(audio_seconds(wav))
    if ac:
        cmd += ["-ac", str(ac)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        core.log(f"transcribe failed: {e}")
        return "", 0.0
    text = (out.stdout or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cleaned = " ".join(lines)
    for tag in ("[BLANK_AUDIO]", "(blank audio)", "[ Silence ]", "[silence]"):
        cleaned = cleaned.replace(tag, "")
    conf = 0.0
    jpath = base + ".json"
    try:
        with open(jpath) as f:
            data = json.load(f)
        probs = [t.get("p", 0.0)
                 for seg in data.get("transcription", [])
                 for t in seg.get("tokens", [])
                 if not t.get("text", "").startswith("[_")]
        if probs:
            conf = sum(probs) / len(probs)
    except Exception:
        pass
    finally:
        try:
            os.remove(jpath)
        except OSError:
            pass
    return _romanise(cleaned.strip()), conf


def loudness(wav: str) -> float:
    """RMS amplitude of the capture (0..1). Directed out-loud speech near
    the mic is loud; background conversation and whispers are quiet."""
    sox = _find("sox")
    if not sox:
        return -1.0
    try:
        r = subprocess.run([sox, wav, "-n", "stat"], capture_output=True,
                           text=True, timeout=30)
        m = re.search(r"RMS\s+amplitude:\s+([0-9.]+)", r.stderr)
        return float(m.group(1)) if m else -1.0
    except Exception:
        return -1.0
