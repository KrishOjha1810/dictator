"""dictator STT: local, private speech-to-text via whisper.cpp.

Nothing about your code leaves the machine. Push-to-talk records through
AVFoundation (see recorder.py), falling back to sox (`rec`) only where the
Swift toolchain is missing. The older hands-free helpers here, `record` and
`record_start`, still use sox's silence detection to end a take by themselves.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import core, loops, script

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

# The models this product is actually shipped with, as opposed to the fallback
# names in the lists above. The installer downloads exactly these and doctor
# reports on exactly these, so the two cannot disagree about what is missing:
# naming a file the installer never fetches sends the user looking for
# something that was never going to be there.
#   (filename, megabytes, what it is for, needed before first use)
SHIPPED = (
    ("ggml-tiny.bin", 74, "works out which language you spoke", True),
    ("ggml-parakeet-tdt-0.6b-v3-q8_0.bin", 638, "English, fast", True),
    ("ggml-large-v3-turbo.bin", 1549, "Hindi and Hinglish", False),
)


def missing(essential_only: bool = False) -> list:
    """Which shipped models are not on disk yet."""
    return [m for m in SHIPPED
            if not (MODEL_DIR / m[0]).exists()
            and (m[3] or not essential_only)]


def arriving(name: str) -> bool:
    """Is this one being downloaded right now?"""
    return (MODEL_DIR / (name + ".part")).exists()


# What a person calls each shipped model, for `dictator models remove english`.
ALIASES = {
    "quick": "ggml-tiny.bin",
    "english": "ggml-parakeet-tdt-0.6b-v3-q8_0.bin",
    "hinglish": "ggml-large-v3-turbo.bin",
}


def resolve_model(name: str) -> str:
    """A shipped model's file name, from its file name or its alias. Raises
    ValueError naming the choices, because a typo here should not read as
    "nothing to remove"."""
    n = name.strip().lower()
    n = ALIASES.get(n, n)
    for m in SHIPPED:
        if m[0].lower() == n:
            return m[0]
    raise ValueError(f"no model called {name!r}; choose one of: "
                     + ", ".join(ALIASES))


# A model the user removed stays removed. The app downloads whatever is
# missing every time dictation starts, so without this a deleted model was
# back the next time the key was changed, and the space never stayed free.
def _removed_file() -> Path:
    return core.STATE_DIR / "models-removed"


def removed() -> set:
    try:
        return {l.strip() for l in _removed_file().read_text().splitlines()
                if l.strip()}
    except Exception:
        return set()


def _set_removed(name: str, on: bool) -> None:
    now = removed()
    now = (now | {name}) if on else (now - {name})
    f = _removed_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(n + "\n" for n in sorted(now)))


# The last download failure per model, so the app can show why and offer a
# Retry instead of a progress bar that never moves.
def _failed_file() -> Path:
    return core.STATE_DIR / "models-failed.json"


def failures() -> dict:
    try:
        return json.loads(_failed_file().read_text())
    except Exception:
        return {}


def note_failure(name: str, why: "str|None") -> None:
    """Record why `name` failed to download, or clear it with None."""
    now = failures()
    if why:
        now[name] = " ".join(str(why).split())[:200]
    else:
        now.pop(name, None)
    try:
        f = _failed_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(now))
    except Exception:
        pass


def fetching() -> str:
    """The model a download process is working on right now, or "".

    Read from the pid file fetch_missing writes while it holds the lock, not
    by probing the lock: a probe that takes the lock for a moment makes a
    download starting in that moment think another process has it, and skip."""
    try:
        pid, name = (MODEL_DIR / ".fetch.pid").read_text().split(None, 1)
        os.kill(int(pid), 0)
        return name.strip()
    except Exception:
        return ""


def own_models() -> bool:
    """Are the models in a directory this product owns? A voicebridge install
    shares its directory with us, and deleting from it would break it."""
    if os.environ.get("DICTATOR_MODELS"):
        return True
    try:
        return MODEL_DIR.resolve() == (core.STATE_DIR / "models").resolve()
    except Exception:
        return False


def remove(name: str) -> dict:
    """Delete one shipped model from this Mac, and keep it deleted.

    Returns {"name", "freed" (bytes), "language" (set when the language had
    to change)}. Raises ValueError with a sentence for the user when it will
    not: a model directory another app shares, or a download in progress."""
    name = resolve_model(name)
    if not own_models():
        raise ValueError(f"the models are in {MODEL_DIR}, which another app "
                         "also uses; removing one there would break it")
    if fetching() == name:
        raise ValueError(f"{name} is downloading right now; remove it once "
                         "the download has finished")
    # A resident server keeps the file mapped; stop it rather than leave the
    # memory and the disk space held by a model that is meant to be gone.
    try:
        pid = int((core.STATE_DIR / "stt.pid").read_text().strip())
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=10).stdout
        if name in cmd:
            _stop_whisper_server()
    except Exception:
        pass
    freed = 0
    for f in (MODEL_DIR / name, MODEL_DIR / (name + ".part")):
        try:
            freed += f.stat().st_size
            f.unlink()
        except FileNotFoundError:
            pass
    _set_removed(name, True)
    note_failure(name, None)
    out = {"name": name, "freed": freed, "language": None}
    # Without the multilingual model, Hinglish has nothing to run on.
    essential = next(m[3] for m in SHIPPED if m[0] == name)
    if not essential and language() == "hinglish":
        (core.STATE_DIR / "lang").write_text("english")
        out["language"] = "english"
    return out


def model_status() -> dict:
    """{filename: {"have", "progress", "essential", "mb", "removed",
    "downloading", "error"}} for every shipped model, for status.json.

    `removed` is the user's own choice and is never downloaded behind their
    back. `downloading` is true only while a process is fetching that file;
    a .part with nobody fetching it is a download that stopped, and `error`
    says why when it is known. Both are what the app's Retry button reads.

    `essential` is the last column of SHIPPED, so the app can wait for the
    models English needs and not for the Hinglish one, which is allowed to
    keep arriving after the user has moved on. Without it the app had to
    wait for all of them, 1.5 GB of optional model included.

    Progress is the size of the .part file against the size in SHIPPED, which
    is in mebibytes and rounded, so it is held just under 1.0 until the file
    is actually in place: a bar that reads full while the model is still
    missing is a bar that lies. Three stat calls, so it is cheap enough to
    run on every state change."""
    out = {}
    gone = removed()
    failed = failures()
    now = fetching()
    for name, mb, _what, essential in SHIPPED:
        if (MODEL_DIR / name).exists():
            out[name] = {"have": True, "progress": 1.0,
                         "essential": essential, "mb": mb, "removed": False,
                         "downloading": False, "error": None}
            continue
        got = 0.0
        try:
            size = (MODEL_DIR / (name + ".part")).stat().st_size
            got = min(0.99, size / float(mb * 1024 * 1024))
        except Exception:
            pass
        out[name] = {"have": False, "progress": round(got, 3),
                     "essential": essential, "mb": mb,
                     "removed": name in gone, "downloading": now == name,
                     "error": failed.get(name)}
    return out

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
    # The app's own copy first. Inside the downloadable app whisper and
    # parakeet ship in Contents/Helpers, built from the pinned source, and a
    # Homebrew install on the same Mac is a different version that the app
    # was never tested against. Falling through to it is still better than
    # nothing, so the search below stays.
    if core.BUNDLE is not None:
        own = core.helper_path(name)
        if own.exists() and os.access(own, os.X_OK):
            return str(own)
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
                             capture_output=True, text=True, errors="replace", timeout=10).stdout
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


def release_server() -> bool:
    """Stop the resident server this product started, if one is running.

    It is started in its own session so a hold never waits on it, which also
    meant it outlived Pause and Quit and kept its model in memory with
    nothing left to use it. Only the pid we wrote is stopped: a server on the
    same port that somebody else started is theirs. True if one was stopped."""
    f = core.STATE_DIR / "stt.pid"
    try:
        pid = int(f.read_text().strip())
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return False
    try:
        f.unlink()
    except FileNotFoundError:
        pass
    if "whisper-server" not in cmd:
        return False        # gone already, or the pid now belongs to another program
    try:
        os.kill(pid, 15)
        return True
    except Exception:
        return False


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


# Whisper says these when it heard no speech. They are not a transcript, they
# are the model telling you there was nothing, and pasting them into somebody's
# editor is worse than pasting nothing: it looks like a wrong transcription
# rather than like silence. Seen in real logs: [MUSIC PLAYING], [INAUDIBLE],
# [No speech detected], [BLANK_AUDIO], [SOUND].
_NOT_SPEECH = re.compile(
    r"^\s*(\[[^\]]*\]|\([^)]*\)|\*[^*]*\*)\s*$", re.I)


def is_silence(text: str) -> bool:
    """Did the model say 'there was nothing', rather than transcribe words?"""
    t = (text or "").strip()
    if not t:
        return True
    # Several markers in a row is still nothing: "[no speech] [no speech]".
    parts = re.findall(r"\[[^\]]*\]|\([^)]*\)|[^\[\]()]+", t)
    return all(not p.strip() or _NOT_SPEECH.match(p.strip()) for p in parts)


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

# The only two answers worth acting on. This product routes between English
# and Hinglish and nothing else, so any other answer is the detector being
# confused rather than useful information.
#
# It confuses easily, and the failure is spectacular rather than subtle. On
# short holds containing Indian names the tiny model returned Malayalam at
# p=0.80 and Malay at p=0.40, and pinning those produced "Аманди." and
# "منن تھیلرر آنڈے": correct-looking transcription of a language nobody spoke,
# in a script that cannot be pasted anywhere. Confidence did not separate the
# good answers from the bad ones, so the language list does.
PINNABLE = ("en", "hi")

# Language identification off a second or two of audio is a coin flip, and a
# hold that short is usually a name or a single word, which is exactly when
# getting it wrong hurts most.
#
# Was 4.0. Lowered because what the alternative costs depends on the Mac, and
# on the one it was set on it cost almost nothing. Below this, whisper decides
# the language itself by running the encoder twice. Measured on an 8 GB M2
# with turbo (9 October 2026): a 3 second hold took 5.15s with `-l auto` and
# 3.42s pinned, while the tiny detector answered in 0.18s. The accuracy side
# was already measured (see audio_ctx_for: pinning short holds, 4.98% against
# 4.98%), and MIN_DETECT_P and PINNABLE still refuse an unsure or unlikely
# answer, so an unclear short hold still goes to whisper as before.
MIN_DETECT_SECS = 1.0


def audio_seconds(wav: str) -> float:
    try:
        import wave
        with wave.open(wav) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


# Shorter than this and shrinking the encoder costs accuracy and time both.
# See audio_ctx_for for the table.
WORTH_TRIMMING = 6.0


def audio_ctx_for(secs: float) -> int:
    """How much of whisper's 30 second window this utterance actually needs.

    whisper.cpp encodes a full 30 seconds however long you spoke, and the
    encoder is 85 percent of the bill. Measured on a 12.4 second hold with
    turbo: 4554ms at the default 1500 frames, 1840ms at 700.

    Undershooting is dangerous, not merely lossy. At 600 frames (12 seconds,
    just under the audio) the same clip lost a word, and smaller still sends
    the decoder into a repetition loop that takes LONGER than full context. So
    this rounds up and adds margin, and returns the default when it cannot
    tell how long the audio is.

    Below `WORTH_TRIMMING` it does not trim at all, because there the trade
    stops being a trade. Measured over 146 real holds, trimmed against full:

        band        trimmed          full encoder
        under 3s    7.59%  0.83s     3.95%  0.58s
        3 to 6s     2.29%  0.75s     2.26%  0.64s
        6 to 12s    0.30%  0.55s     0.00%  0.72s
        12 to 30s   0.28%  0.86s     0.28%  1.08s

    Under six seconds trimming is worse AND slower: it halves the accuracy of
    the shortest holds and costs a quarter of a second doing it, because a
    decoder given too little context loops, and looping takes longer than the
    encoding it saved. Above six seconds it buys real time for nothing, which
    is what it was written for.

    The same measurement killed the other suspect in the same issue: pinning
    the language on short holds changes the accuracy by nothing at all
    (4.98% against 4.98%) and costs 0.13s, so `MIN_DETECT_SECS` was never the
    problem it looked like."""
    if secs <= 0:
        return 0
    if secs < WORTH_TRIMMING:
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
                           capture_output=True, text=True, errors="replace", timeout=30)
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
    secs = audio_seconds(wav)
    if secs and secs < MIN_DETECT_SECS:
        core.log(f"stt: only {secs:.1f}s of audio, too short to identify a "
                 f"language from, letting whisper decide")
        return "auto"
    code, p = detect_language(wav)
    if code not in PINNABLE:
        core.log(f"stt: detector said {code or 'nothing'} (p={p:.2f}), which "
                 f"is not a language this handles, letting whisper decide")
        return "auto"
    if p < MIN_DETECT_P:
        core.log(f"stt: language unclear ({code} p={p:.2f}), "
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
    # per request, so it always encodes the full 30 second window. Where the
    # CLI would size that window smaller, it wins even after paying process
    # start and model load: measured on a 12.4 second hold, 2.90s through the
    # CLI with the window sized against 4.25s through this server.
    #
    # Below WORTH_TRIMMING the CLI does not size the window either, so that
    # reason stops applying and the comparison inverts. Both encode the full
    # window; only one of them also reads a 1.6GB model first. Measured on 57
    # real holds under six seconds, interleaved, against the multilingual
    # model: 5.57s through the CLI, 3.60s through this server, with the error
    # rate the same inside noise (2.18% against 2.41%).
    #
    # The model load is why. On a warm page cache a 12.1s hold spends 906ms of
    # its 1523ms loading the model and 138ms encoding, because whisper-cli is
    # a new process every time. The server pays that once.
    secs = audio_seconds(wav)
    if audio_ctx_for(secs) and secs < 25:
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
    # "rec" stays in the answer under its old name because callers outside
    # this repo read it, but it is now satisfied by the native recorder too:
    # what the question means is "can this machine record", and since the
    # Swift recorder landed that no longer implies sox.
    from . import recorder as _rec
    return {
        "whisper": whisper_bin(),
        "rec": _rec.build() or _find("rec"),
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


def recorder_in_use() -> str:
    """Which recorder a hold would use right now: "native", "sox" or "".

    Named out loud because the two are not interchangeable to anyone
    debugging: they open the microphone differently, they fail differently,
    and only one of them is a dependency the user had to install."""
    from . import recorder as _rec
    if _rec.build():
        return "native"
    return "sox" if _find("rec") else ""


def record_hold(wav: str, max_secs: int = 120):
    """Record until told to stop. For push-to-talk, where YOU are the boundary.

    `record` and `record_start` both hand the boundaries to sox: `silence`
    trims leading quiet and ends the take after a pause. That is right when
    nobody is holding a key, and wrong here in two ways. Trimming the lead can
    eat the first word, because you start speaking as you press. And stopping
    on a pause cuts you off mid-thought every time you stop to think, while
    still holding the key down to say you have not finished.

    So: no silence effect at all. It records from the instant it starts until
    the caller kills it, which is the moment you let go.

    AVFoundation does this, so sox is only the fallback (see recorder.py). The
    shape is unchanged either way: a Popen the caller polls and terminates."""
    # stderr is kept, not discarded, whichever recorder answers. When a
    # recording comes back empty the recorder has almost always said why
    # ("can't open input device", a permission refusal, a device that
    # vanished), and throwing that away turns a one-line answer into an
    # afternoon. The same mistake in the key listener is what made the
    # Accessibility problem invisible.
    errf = None
    try:
        core.STATE_DIR.mkdir(parents=True, exist_ok=True)
        errf = open(core.STATE_DIR / "rec.err", "w")
    except Exception:
        pass

    from . import recorder as _rec
    p = _rec.start(wav, max_secs, errf)
    if p is not None:
        _hold_mic_lock_while(p)
        return p

    rec = _find("rec")
    if not rec:
        core.log("record_hold: no recorder (swiftc missing and sox not found)")
        return None
    cmd = [rec, "-q", "-c", "1", "-r", "16000", "-b", "16", wav,
           "trim", "0", str(max_secs)]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=errf or subprocess.DEVNULL)
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
    # The native recorder publishes the level AVFoundation measured, which is
    # the input itself rather than whatever has reached the disk yet. The tail
    # read below stays for sox, which publishes nothing, and for the gap
    # before the first level is written.
    from . import recorder as _rec
    published = _rec.level(wav)
    if published is not None:
        return published
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
                           capture_output=True, text=True, errors="replace", timeout=120)
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
    "This is the English line. Torvi Skallandrup or Vayne is English accuracy."
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


# Curly quotes and an ellipsis are the only characters above ASCII that a
# transcriber of English has any business producing.
_FINE_ABOVE_ASCII = "\u2018\u2019\u201c\u201d\u2026"


# Two words in a row that are in neither dictionary. One is an ordinary
# mishearing inside a good sentence; two in a row is a stretch of speech the
# transcriber could not represent at all.
MANGLED_RUN = 2


def _mangled_stretch(text: str) -> bool:
    """Did Parakeet get the English right and invent the Hindi.

    The failure the other three checks cannot see, and the one that matters
    most, because it is this product's whole case. A hold with both languages
    in it comes back with the English half correct and the Hindi half turned
    into English-looking proper nouns:

        "Can you listen to me now? Kia Abdumujason paraheo."
        "Are you able to listen to me now? Kya Abdumjesun Paraheho."

    Both are "kya aap mujhe sun pa rahe ho". The English half makes the word
    rate normal, the capitalisation ordinary and every character ASCII, so
    `_too_little`, `_parakeet_lost` and `_not_english` all pass it. They judge
    the whole answer, and half of the answer is fine.

    This looks at the run instead. Measured over 127 Parakeet answers that the
    other three checks kept: exactly THREE have two or more consecutive words
    in neither dictionary, and all three are the mangled ones above. Nothing
    good is caught. A run of one is left alone, because that is a single odd
    word in a working sentence ("Manit", "acur") and rejecting those would
    send good holds to the slower model.
    """
    from . import known
    run = 0
    for w in re.findall(r"[A-Za-z'][A-Za-z']*", text or ""):
        if len(w) > 2 and not known._known(w.lower()):
            run += 1
            if run >= MANGLED_RUN:
                return True
        else:
            run = 0
    return False


def _not_english(text: str) -> bool:
    """Did it answer in a language it does not have?

    Parakeet has English and nothing else, so its correct output is plain
    ASCII. When the audio switches to Hindi mid sentence it sometimes reaches
    for whichever language its tokenizer can spell the sounds in, and the
    giveaway is in the characters rather than the words. Two real holds:

        "Mujal okta heangtoe plazma, iz jidti bazej kutka ku banana cajk."
                             with Polish and Czech diacritics on iz, jidti, cajk
        "Menen Telerande."   in Cyrillic

    Neither looks odd by word length or by capitalisation, which is what the
    other two checks measure, and the second is short enough that the word
    rate check will not judge it either. One foreign letter is enough: an
    English transcriber has no reason to emit even one."""
    return any(ord(c) > 127 and c not in _FINE_ABOVE_ASCII
               for c in (text or ""))


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

    NOT called automatically, and the measurement is why. A server is started
    with one audio context and cannot be told otherwise per request, so it
    always encodes the full 30 second window, while the CLI can size the
    window to the utterance. On a 12.4 second hold the CLI is faster even
    after paying process start and model load. Leaving one resident costs
    memory and contends for the GPU: the same hold measured 3.2s with no
    server running and 5.8s with one up.

    That contention is why this is still not automatic, and it is the whole of
    what decides it. A server would help the short holds and hurt the rest,
    and on this corpus the holds it would help are 39% of the total. Nobody
    has measured the two populations together, so turning it on would be a
    guess dressed as an optimisation.

    What DID change: `_transcribe_server` used to decline anything under 25
    seconds, on the grounds that the CLI could size the window. Below
    WORTH_TRIMMING the CLI no longer sizes it either, so that reason stopped
    applying and the comparison inverted. Measured on 57 real holds under six
    seconds against the multilingual model, interleaved: 5.57s through the
    CLI, 3.60s through a running server, error the same inside noise. So a
    server that is already up is now used for those, where before it was
    ignored. This does not start one.

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


def _looks_indic(text: str) -> bool:
    """Is this the right language written in the wrong alphabet.

    Arabic script here means Urdu, which is Hindi by another name and another
    writing system, so the words are right and only the script is unusable.
    Anything else foreign (Cyrillic, Han, Greek) is the model having lost the
    thread, and asking it again in Hindi would not help."""
    return any("\u0600" <= c <= "\u06ff" or "\u0750" <= c <= "\u077f"
               for c in (text or ""))


def _transcribe_ex(wav: str) -> "tuple[str, float]":
    global LAST_ENGINE, _force_multilingual
    if language() != "hinglish" and parakeet_ready():
        got = _parakeet(wav)
        if got and not _parakeet_lost(got) and not _too_little(got, wav) \
                and not _not_english(got) and not _mangled_stretch(got):
            LAST_ENGINE = "parakeet"
            return got, 0.9
        # Parakeet only drops speech like this when the audio is not English,
        # so falling back to the English model would just swap one wrong
        # answer for "[NON-ENGLISH SPEECH]". Go multilingual for this one
        # utterance regardless of what the setting says.
        #
        # Including when it returned NOTHING. That was treated as "no opinion"
        # and fell through to the English model, which then produced
        # "[NON-ENGLISH SPEECH]", "[INAUDIBLE]" and "[No speech detected]" on
        # real Hinglish holds. An empty answer from an English-only model on
        # audio that was not English is the same signal as a wrong one.
        _force_multilingual = True
        if got:
            core.log(f"stt: parakeet dropped speech, falling back to "
                     f"{stt_lang_mode()[0].name}: {got[:60]!r}")
        # The multilingual model may not be here yet: the app fetches it in
        # the background after English is ready. Saying "speech recognition
        # isn't set up" then was wrong, and dropping what parakeet heard was
        # worse. Keep the English answer and say why Hindi is not used yet.
        multi = stt_lang_mode()[0]
        if not multi.exists():
            pct = model_status().get(multi.name, {}).get("progress", 0.0)
            core.surface_error(
                "transcribe",
                "The Hindi and Hinglish model is still downloading"
                + (f" ({pct:.0%})." if pct else "."),
                hint="English works meanwhile; Hinglish starts working "
                     "when it lands.")
            if got:
                LAST_ENGINE = "parakeet"
                return got, 0.6
            return "", 0.0

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
        # errors="replace" rather than strict, on every engine call in this
        # file. whisper.cpp writes the model's own bytes, and a hold that ended
        # mid-character produced `'utf-8' codec can't decode bytes in position
        # 37-38`, which raised here and was logged as "nothing was said". The
        # user said something; we threw it away because one byte was ugly.
        out = subprocess.run(cmd, capture_output=True, text=True,
                             errors="replace", timeout=120)
    except Exception as e:
        core.log(f"transcribe failed: {e}")
        return "", 0.0
    text = (out.stdout or "").strip()
    # A shrunk encoder sometimes makes the decoder repeat itself instead of
    # transcribing, and what comes out ("ndernderndernder") is not speech and
    # is not worth pasting. The trimming is ours, so the answer is to spend the
    # second or so and run it again at full size rather than deliver that.
    if ac and text and loops.looped(text):
        core.log(f"transcribe: {loops.why(text)}, running again at full size")
        try:
            again = subprocess.run([a for a in cmd if a != "-ac"
                                    and a != str(ac)],
                                   capture_output=True, text=True, errors="replace", timeout=120)
            retried = (again.stdout or "").strip()
            # Only if it actually helped. A loop on both passes means the audio
            # is the problem, and the first answer is no worse than the second.
            if retried and not loops.looped(retried):
                text = retried
            else:
                core.log("transcribe: it looped at full size too, "
                         "so the audio is the problem, not the setting")
                text = loops.collapse(text)
        except Exception as e:
            core.log(f"transcribe: the second pass failed: {e}")
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
    answer = _romanise(cleaned.strip())

    # The guard turbo never had. `_not_english` is applied to Parakeet's answer
    # and to nothing else, so the multilingual model, which is where every
    # Hinglish hold lands, could return any alphabet at all and have it pasted.
    # Real examples from one history, all delivered: a Hindi sentence in Arabic
    # script, a line of Spanish, and a 0.67s hold that came back as Hiragana,
    # Han and Polish at once.
    #
    # Devanagari is deliberately NOT refused: it is a correct intermediate
    # answer that `_romanise` has just converted, and refusing it would throw
    # away a good hold one step before it is made readable.
    answer = script.repair(answer)
    if answer and not script.usable(answer):
        bad = "".join(dict.fromkeys(script.foreign(answer)))[:12]
        # Urdu is the case worth separating, and it is not the model failing.
        # Hindi and Urdu are the same spoken language, so `-l auto` picks
        # between them on nothing, and when it picks Urdu the transcription is
        # CORRECT and in an alphabet that cannot be pasted and that
        # `_romanise` does not convert. A real hold: the user asked "kya tumhe
        # sunai de raha hai" and got back 'کیاتمجھےسنپر', which was then
        # dropped, so he said something and received silence.
        #
        # Asking again with the language pinned to Hindi gets the same
        # sentence in Devanagari, which `_romanise` turns into something he
        # can read. One extra pass, only on a hold that would otherwise have
        # produced nothing at all.
        if lang == "auto" and _looks_indic(answer):
            core.log(f"transcribe: answered in {bad!r}, which is the right "
                     f"words in an alphabet nothing here can use. Asking "
                     f"again in Hindi.")
            again = [a for a in cmd]
            again[again.index("-l") + 1] = "hi"
            try:
                r2 = subprocess.run(again, capture_output=True, text=True,
                                    errors="replace", timeout=120)
                second = script.repair(_romanise(
                    _clean_text((r2.stdout or "").strip())))
                if second and script.usable(second):
                    return second, conf
            except Exception as e:
                core.log(f"transcribe: the Hindi pass failed: {e}")
        core.log(f"transcribe: answered in an alphabet this does not handle "
                 f"({bad!r}), so it was not transcribing. Dropping it.")
        return "", 0.0
    return answer, conf


def loudness(wav: str) -> float:
    """RMS amplitude of the capture (0..1), or -1 if it cannot be read.

    Directed out-loud speech near the mic is loud; background conversation and
    whispers are quiet. This used to shell out to `sox stat` and parse its
    stderr, which meant an answer of -1 on any machine without sox even though
    the number is one pass over samples we already have."""
    import array
    import wave
    try:
        with wave.open(str(wav), "rb") as w:
            if w.getsampwidth() != 2:
                return -1.0
            frames = w.readframes(w.getnframes())
        a = array.array("h")
        a.frombytes(frames[:len(frames) - len(frames) % 2])
        if not a:
            return 0.0
        # Scaled to 0..1 the way sox reported it, so any threshold written
        # against the old numbers still means the same thing.
        return (sum(x * x for x in a) / len(a)) ** 0.5 / 32768.0
    except Exception:
        return -1.0
