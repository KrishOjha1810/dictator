"""Different formatting in different applications, because they are different.

A spoken list belongs in Slack. In a terminal it is four lines of text with
"1." in front of each one, pasted at a shell prompt, and the shell will try to
run the first of them. A capital letter belongs at the start of a sentence. In
a terminal it is the difference between a command and an error.

The competitors sell this as "tone": the product looks at the application and
has a cloud model rewrite you to sound formal in email and casual in chat.
That is a model rewriting your words based on a guess about the room, which is
the one thing this project has measured and refused (see shape.py). What is
underneath the marketing, and what people actually notice day to day, is much
smaller and entirely deterministic: WHICH FORMATTING RULES ARE ON. So that is
what this file does, and it does not pretend to do the other thing.

HOW A SET OF RULES IS CHOSEN
----------------------------
Three layers, each one overriding the last:

    the defaults          shape.py's own, the conservative ones
    your global settings  `dictator format lists on`
    this file             `dictator format in Slack lists on`

And within this file, a group is weaker than a name:

    terminal   every terminal emulator, one entry, because nobody wants to
               configure Ghostty and iTerm and Terminal separately to say the
               same thing. The list is paste.py's, which already had to know
               what a terminal was.
    Slack      an application, by the name macOS reports for it

An override only ever moves a rule the caller already had. A key in this file
that shape.py does not know about is ignored rather than passed along, because
these flags are handed to shape() as keyword arguments and a stray one would
be a TypeError on the dictation path, in a thread, where the user would see
nothing at all except a hold that produced no words.
"""
import json
from pathlib import Path

from . import core

__all__ = ["rules", "overlay", "set_rule", "clear", "group", "FILE"]

FILE = core.STATE_DIR / "app-format.json"

# The one group. Named rather than inferred, and there is deliberately only
# one: a "chat" group covering Slack and Discord and Messages would be a
# guess about what those applications have in common, and the user can name
# them separately in one command each.
GROUPS = ("terminal",)


def rules() -> dict:
    """Everything set per application, keyed by lowercase name or group."""
    try:
        raw = json.loads(FILE.read_text())
    except Exception:
        return {}
    out = {}
    for name, flags in raw.items():
        if isinstance(flags, dict):
            out[str(name).strip().lower()] = {k: bool(v) for k, v in flags.items()}
    return out


def save(all_rules: dict) -> None:
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(FILE) + ".tmp"
        Path(tmp).write_text(json.dumps(all_rules, indent=1, sort_keys=True))
        Path(tmp).replace(FILE)
    except Exception as e:
        core.log(f"profiles: {e}")


def group(app: str) -> str:
    """The group an application belongs to, or "".

    Terminals are asked of paste.py rather than listed again here. That module
    already had to know which applications collapse a long paste, and two
    lists of terminal emulators in one codebase would drift the first time
    somebody installed a new one."""
    try:
        from . import paste
        if paste._is_terminal(app):
            return "terminal"
    except Exception:
        pass
    return ""


def applying(app: str) -> list:
    """Which stored entries apply to this application, weakest first."""
    if not app:
        return []
    all_rules = rules()
    out = []
    g = group(app)
    if g and g in all_rules:
        out.append((g, all_rules[g]))
    name = app.strip().lower()
    if name in all_rules:
        out.append((name, all_rules[name]))
    return out


def overlay(flags: dict, app: str) -> dict:
    """`flags` with this application's overrides applied.

    Never adds a key. The result has exactly the keys it came in with, so a
    caller that was going to pass this to shape() as keyword arguments still
    can, whatever is in the file."""
    out = dict(flags or {})
    if not app or not out:
        return out
    for _, over in applying(app):
        for k, v in over.items():
            if k in out:
                out[k] = bool(v)
    return out


def set_rule(app: str, key: str, value: bool) -> dict:
    """Turn one rule on or off for one application or group."""
    name = (app or "").strip().lower()
    if not name:
        return {}
    all_rules = rules()
    entry = dict(all_rules.get(name) or {})
    entry[key] = bool(value)
    all_rules[name] = entry
    save(all_rules)
    return entry


def clear(app: str) -> bool:
    """Drop every override for an application, back to the global settings."""
    name = (app or "").strip().lower()
    all_rules = rules()
    if name not in all_rules:
        return False
    del all_rules[name]
    save(all_rules)
    return True
