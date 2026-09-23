"""Turn a spoken transcript into text that looks like it was typed.

Nothing here talks to a model. Whole-transcript rewriting by an LLM has been
measured to make accuracy WORSE, and the vendors who ship it document their own
damage: a leading "so" that carried a condition removed as filler, deliberate
repetition collapsed, and "one point something percent" turned into "1%". That
last one is not a formatting bug, it is data corruption. So this file is
deterministic string handling and nothing else: pure, no I/O, no subprocess, no
network, and it never touches a number.

THE RULE THIS FILE IS BUILT AROUND
----------------------------------
Restructuring someone's words needs evidence that they MEANT the structure.
The cost is asymmetric. A list the user wanted and did not get is a mild
annoyance they can fix with two keystrokes. A list they did not want, built out
of a sentence that merely began with "first of all", is text they have to pull
apart, and the next time they dictate they are wondering what it will do to
them. So every rule below is allowed to miss, and none of them is allowed to
guess.

Three things follow from that.

1. Spoken punctuation is a SUBSTITUTION, never an inference. The word has to be
   said. Nothing is inserted because a pause sounded like a comma.

2. A word that is also an ordinary English word is only treated as a command
   when its position says it cannot be the ordinary word. "a comma", "the
   colon", "the word comma" stay as they are.

3. List detection needs three markers in ascending order, each at the start of
   a clause, each followed by real content. One marker is a discourse
   connective, not a list. Two can be a contrast. Three ascending markers that
   a speaker laid out one after another is a structure they built on purpose.

And it is off unless the caller asks for it. Every loud complaint about this
category of feature is the same complaint: it could not be turned off.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
  * Filler removal. This is where meaning is lost, and it is not worth the
    words it saves.
  * Any conversion of spoken numbers to digits, anywhere, for any reason.
  * "period" as a full stop. It is a noun this user says often (grace period,
    the period of the loop, a period of time) and "full stop" already covers
    the intent with none of the risk. Losing the American phrasing is cheaper
    than eating the noun.
  * "dash" and "point" as punctuation. Both are common words, and "point"
    in particular appears in the middle of ordinary Hinglish ("pehla point yeh
    hai ki..."), which is exactly the sentence that must survive untouched.
  * Any dash character other than the plain hyphen.
"""
import re

__all__ = ["shape"]


# --- spoken punctuation ----------------------------------------------------
#
# How each replacement sits against the words either side:
#   "punct"  the character hugs the word on its left, one space after it
#   "open"   a space before, hugs the word on its right
#   "tight"  no space either side, because it joins two words
#   "break"  a line break, with no spaces left clinging to it
#   "quote"  a straight quote that alternates open, close, open, close
#
# Phrases are matched longest first, so "new paragraph" wins over "new line"
# and "inverted commas" is never seen as "comma".
_PUNCT = [
    ("new paragraph", "\n\n", "break"),
    ("start a new paragraph", "\n\n", "break"),
    ("new line", "\n", "break"),
    ("newline", "\n", "break"),
    ("next line", "\n", "break"),
    ("line break", "\n", "break"),
    ("question mark", "?", "punct"),
    ("exclamation mark", "!", "punct"),
    ("exclamation point", "!", "punct"),
    ("full stop", ".", "punct"),
    ("semicolon", ";", "punct"),
    ("semi colon", ";", "punct"),
    ("comma", ",", "punct"),
    ("colon", ":", "punct"),
    ("hyphen", "-", "tight"),
    ("forward slash", "/", "tight"),
    ("backslash", "\\", "tight"),
    ("back slash", "\\", "tight"),
    ("ampersand", "&", "open"),
    ("percent sign", "%", "punct"),
    ("ellipsis", "...", "punct"),
    ("open bracket", "(", "open"),
    ("open parenthesis", "(", "open"),
    ("close bracket", ")", "punct"),
    ("close parenthesis", ")", "punct"),
    ("open quote", '"', "open"),
    ("open quotes", '"', "open"),
    ("close quote", '"', "punct"),
    ("close quotes", '"', "punct"),
    ("inverted commas", '"', "quote"),
    ("at the rate", "@", "tight"),
]

# The ones that have to come in pairs before they are believed. "inverted
# commas" wraps something; a single one is somebody talking ABOUT quoting, and
# converting it leaves a stray quote mark on screen, which is worse than doing
# nothing. So an odd count means the transcript keeps the words.
_PAIRED = {"inverted commas"}

# A punctuation word straight after one of these is a noun, not a command.
# This is the escape hatch as well as the guard: if you actually want the word
# "comma" in your text, say "a comma" or "the word comma". Without something
# like this we would have rebuilt the bug where a word can never be dictated.
_LITERAL_BEFORE = {
    "a", "an", "the", "this", "that", "these", "those", "my", "your", "our",
    "his", "her", "its", "their", "one", "two", "each", "every", "some",
    "any", "no", "another", "double", "single",
    "word", "words", "literal", "literally", "spell", "spelled", "spelt",
    "capital",
}
# "said", "type" and "write" are NOT in that set, although they look like they
# belong. "he said open quote hello close quote" is the ordinary way people
# dictate a quotation, and guarding on the verb would break the commonest use
# of the commands to protect a phrasing nobody uses. A determiner already
# covers "type a comma", and "the word comma" covers the rest.

_PUNCT_BY_PHRASE = {p: (rep, kind) for p, rep, kind in _PUNCT}

_PUNCT_RE = re.compile(
    "(?<![\\w'])("
    + "|".join(re.escape(p).replace("\\ ", r"\s+")
               for p in sorted(_PUNCT_BY_PHRASE, key=lambda s: (-len(s.split()), -len(s))))
    + ")(?![\\w'])",
    re.IGNORECASE,
)

_WORD_BEFORE_RE = re.compile(r"([\w']+)[^\w']*$")
_WORD_AFTER_RE = re.compile(r"^[^\w']*([\w']+)")


def _word_before(text, pos):
    """The word immediately in front, ignoring anything across a boundary.

    "he is number two" must not start a list, which is why the word in front
    is checked at all. But "my goals are: one, ... two, ... three, ..." is the
    most natural way there is to dictate a list out loud, and the colon is
    exactly the speaker saying the sentence ended and the items begin. So the
    lookback stops at a boundary rather than reaching through it."""
    head = text[:pos]
    cut = max(head.rfind(":"), head.rfind("."), head.rfind("\n"))
    if cut >= 0:
        head = head[cut + 1:]
    m = _WORD_BEFORE_RE.search(head)
    return m.group(1).lower() if m else ""


def _word_after(text, pos):
    m = _WORD_AFTER_RE.match(text[pos:])
    return m.group(1).lower() if m else ""


def _spoken_punctuation(text):
    """Replace the punctuation the speaker actually named. Nothing is inferred."""
    def a_command(m, phrase):
        if _word_before(m.string, m.start()) in _LITERAL_BEFORE:
            return False
        # "at the rate of five percent" is a real sentence and not an address.
        if phrase == "at the rate" and _word_after(m.string, m.end()) == "of":
            return False
        return True

    # Count only the ones that would be converted, so that a guarded "the word
    # inverted commas" cannot make its partner look unpaired.
    counts = {}
    for m in _PUNCT_RE.finditer(text):
        phrase = re.sub(r"\s+", " ", m.group(1)).lower()
        if a_command(m, phrase):
            counts[phrase] = counts.get(phrase, 0) + 1

    slots = []

    def take(m):
        phrase = re.sub(r"\s+", " ", m.group(1)).lower()
        rep, kind = _PUNCT_BY_PHRASE[phrase]
        if not a_command(m, phrase):
            return m.group(0)
        if phrase in _PAIRED and counts.get(phrase, 0) % 2 != 0:
            return m.group(0)
        slots.append((rep, kind))
        return "\x00%d\x00" % (len(slots) - 1)

    return _settle(_PUNCT_RE.sub(take, text), slots)


# Whatever the recogniser put around the spoken word (it hears a pause and
# writes a comma, so "hello comma world" arrives as "hello, comma, world") is
# taken with the word, otherwise every substitution doubles up.
_SLOT_RE = re.compile(r"(?:[ \t]*([,.]))?[ \t]*\x00(\d+)\x00[ \t]*([,.])?[ \t]*")


def _settle(text, slots):
    """Put the substituted characters against the words the right way round."""
    quotes = [0]

    def fix(m):
        eaten = m.group(1) or ""
        rep, kind = slots[int(m.group(2))]
        before = m.string[:m.start()]
        after = m.string[m.end():]
        # The comma on the far side is the same pause being written down twice.
        # Whatever the speaker meant by the punctuation, they said it out loud,
        # so the guessed one goes.
        if kind == "quote":
            # Alternating, because a straight quote looks the same both ways
            # but does not sit the same way against the words.
            kind = "open" if quotes[0] % 2 == 0 else "punct"
            quotes[0] += 1
        if kind == "break":
            # The sentence keeps its own full stop. Only the spaces go.
            return eaten + rep
        if kind == "punct":
            # A closing quote or bracket is not a sentence end, so a full stop
            # behind it is the sentence's own and comes back out on the far
            # side of the mark. Only a replacement that IS sentence punctuation
            # swallows the one the recogniser guessed.
            keep = "" if rep in ".,;:!?" else (m.group(3) or "")
            tail = "" if not after or after[0] in ")]}\x00\n" else " "
            return rep + keep + tail
        if kind == "open":
            head = eaten + (" " if before and before[-1] not in " \t\n([{" else "")
            return head + rep
        return eaten + rep      # tight: it joins the words either side

    return _SLOT_RE.sub(fix, text)


# --- lists -----------------------------------------------------------------

# Ordinals are strong markers: nobody counts "first, second, third" by accident.
# Hinglish ordinals are here for the same reason the rest of this project
# exists, and they carry the same three-in-a-row requirement, which is what
# makes "pehla point yeh hai ki the loop is slow" safe: one marker is never a
# list, in any language.
_ORDINALS = {
    "first": 1, "firstly": 1, "second": 2, "secondly": 2, "third": 3,
    "thirdly": 3, "fourth": 4, "fourthly": 4, "fifth": 5, "fifthly": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "pehla": 1, "pehle": 1, "pehli": 1,
    "dusra": 2, "doosra": 2, "dusre": 2, "doosre": 2, "dusri": 2,
    "teesra": 3, "tisra": 3, "teesre": 3, "teesri": 3,
    "chautha": 4, "chauthe": 4, "paanchwa": 5, "panchwa": 5,
}

# Counting words are weak markers. "one" is a pronoun, an article in most of
# the ways people speak, and half of "one second". It only counts as a list
# marker when the speaker put a pause after it that the recogniser wrote down,
# or when they said "number one" or "point one" outright.
_COUNTING = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_MARKER_RE = re.compile(
    r"(?<![\w'])(?:(number|point|step)\s+)?("
    + "|".join(sorted(list(_ORDINALS) + list(_COUNTING), key=len, reverse=True))
    + r"|\d{1,2})(?![\w'])(\.|,|:)?",
    re.IGNORECASE,
)

# A marker followed by one of these is not introducing an item. Some are
# discourse ("first of all", "first and foremost", "first off"), some are time
# ("one second", "two minutes"), and some are just compounds ("first name",
# "second hand", "third world", "first aid").
_NOT_A_MARKER_BEFORE_WORD = {
    "of", "and", "off", "or",
    "time", "times", "thing", "things", "thought", "thoughts", "half",
    "quarter", "place", "person", "hand", "opinion", "language", "aid",
    "world", "name", "names", "draft", "attempt", "try", "chance",
    "second", "seconds", "minute", "minutes", "hour", "hours", "day", "days",
    "week", "weeks", "month", "months", "year", "years", "percent", "degree",
    # A copula means the marker is the SUBJECT of a sentence, not a label on an
    # item: "point one is the loop" is a statement about point one, and turning
    # it into "1. is the loop" destroys it. Items are things, not predicates.
    "is", "are", "was", "were", "means", "meant", "will", "would", "should",
    "could", "might", "must", "hai", "hain", "tha", "thi",
}

# A clause boundary is the strongest cheap signal that a marker is introducing
# something rather than sitting inside a sentence. It is what saves "he came
# first, she came second, I came third": those markers are at the END of their
# clauses, not the start, so none of them counts.
_CLAUSE_END = set(".!?;:,\n")

# A marker directly after one of these is part of the sentence, not in front of
# it: "the first thing", "he is number two", "in one go", "at first".
_NOT_A_MARKER_AFTER_WORD = _LITERAL_BEFORE | {
    "is", "was", "are", "were", "am", "be", "been", "being",
    "at", "in", "on", "of", "to", "for", "by", "from", "with",
    "came", "finished", "ranked", "came", "place", "placed",
}

_JOINER_RE = re.compile(r"(?<![\w'])(?:and|or|aur|ya|then|phir)$", re.IGNORECASE)

_MIN_ITEMS = 3          # see the module docstring: one is a connective, two is a contrast
_MIN_ITEM_WORDS = 2     # "one, two, three" is counting, not a list


def _markers(text):
    found = []
    for m in _MARKER_RE.finditer(text):
        prefix, word, trailer = m.group(1), m.group(2).lower(), m.group(3)
        if _word_before(text, m.start()) in _NOT_A_MARKER_AFTER_WORD:
            continue
        # "number two", "point two", "step two" and a written "2." are somebody
        # enumerating out loud, so they are allowed mid-sentence: people say
        # "number one do this number two do that" in one breath with no pauses
        # for the recogniser to write down. A bare ordinal gets no such
        # licence, because the clause boundary is the only thing separating
        # "second, add a test" from "she came second".
        written_out = word.isdigit() and trailer == "."
        if not prefix and not written_out:
            head = text[:m.start()].rstrip(" \t")
            # "and third, write code": the conjunction joins the items and is
            # still a boundary. What is behind it has to be one too, so "he
            # came second and I came third" is not rescued by this.
            head = _JOINER_RE.sub("", head).rstrip(" \t")
            if head and head[-1] not in _CLAUSE_END:
                continue
        if word.isdigit():
            value, strong = int(word), bool(prefix) or trailer in (".", ",", ":")
        elif word in _ORDINALS:
            value, strong = _ORDINALS[word], True
        else:
            value, strong = _COUNTING[word], bool(prefix) or trailer in (",", ":")
        if not strong:
            continue
        if _word_after(text, m.end()) in _NOT_A_MARKER_BEFORE_WORD:
            continue
        found.append((m.start(), m.end(), value))
    return found


def _numbered(text):
    """Rebuild as a numbered list, or hand the text back untouched."""
    found = _markers(text)
    if len(found) < _MIN_ITEMS:
        return text
    # Strictly 1, 2, 3, ... with nothing missing and nothing repeated. A stray
    # "first" later in the transcript breaks the sequence and cancels the whole
    # thing, which is the conservative direction to fail in.
    if [v for _, _, v in found] != list(range(1, len(found) + 1)):
        return text

    items = []
    for i, (_, end, _v) in enumerate(found):
        stop = found[i + 1][0] if i + 1 < len(found) else len(text)
        item = text[end:stop].strip().lstrip(",:.-").strip()
        # "first do X, second do Y, and third do Z": the joining word belongs to
        # the sentence, not to the item it trails.
        item = re.sub(r"[,;]?\s+(?:and|or|aur|ya)$", "", item, flags=re.IGNORECASE)
        item = item.rstrip(" \t,;")
        if len(item.split()) < _MIN_ITEM_WORDS or len(item) < 4:
            return text
        items.append(item)

    head = text[:found[0][0]].strip().rstrip(",;")
    lines = [head] if head else []
    lines += ["%d. %s" % (i + 1, item) for i, item in enumerate(items)]
    return "\n".join(lines)


# "bullet point" is not a word anyone uses mid-sentence by accident, so unlike
# an ordinal it is an explicit instruction and two of them are enough evidence.
# It still needs the literal guard, for "the bullet points I sent you".
_BULLET_RE = re.compile(r"(?<![\w'])bullet(?:\s+points?)?(?![\w'])", re.IGNORECASE)


def _bulleted(text):
    found = [m for m in _BULLET_RE.finditer(text)
             if _word_before(text, m.start()) not in _LITERAL_BEFORE]
    if len(found) < 2:
        return text
    items = []
    for i, m in enumerate(found):
        stop = found[i + 1].start() if i + 1 < len(found) else len(text)
        item = text[m.end():stop].strip().lstrip(",:.-").strip().rstrip(" \t,;")
        if not item:
            return text
        items.append(item)
    head = text[:found[0].start()].strip().rstrip(",;")
    lines = [head] if head else []
    lines += ["- " + item for item in items]
    return "\n".join(lines)


# --- sentences -------------------------------------------------------------

# Words that are commands, not the start of a sentence. Dictating into a
# terminal is one of the things this project is for, and "Git push" does not
# run. The list is deliberately short: it covers what people actually say into
# a shell and is not trying to be a dictionary.
_KEEP_LOWER = {
    "git", "npm", "npx", "pnpm", "yarn", "node", "pip", "pip3", "python",
    "python3", "brew", "sudo", "ssh", "scp", "curl", "wget", "grep", "sed",
    "awk", "jq", "ls", "cd", "rm", "mv", "cp", "mkdir", "chmod", "chown",
    "cargo", "docker", "kubectl", "tmux", "vim", "nano", "gh", "rustc",
    "swiftc",
}
# Words like "open", "make", "go", "touch" and "cat" are commands too, and they
# are deliberately absent: they are ordinary English far more often than they
# are a shell, and "Open the file" is the right answer for a sentence.

_WRAPPERS = "\"'(["
# Markers that carry no words of their own, so the sentence has not started yet.
_LIST_PREFIXES = ("-", "*")


def _capitalise_sentences(text):
    """Walk the words and capitalise the ones that open a sentence.

    A scanner rather than one regex over the whole string, because the obvious
    regex has to consume the full stop that ends "yes." to find the word, and
    then that same full stop is no longer there to start the next sentence. So
    every other sentence kept its lowercase letter.
    """
    out = []
    fresh = True
    for piece in re.split(r"(\s+)", text):
        if not piece:
            continue
        if piece.isspace():
            if "\n" in piece:
                fresh = True
            out.append(piece)
            continue
        if fresh:
            if _capitalisable(piece):
                k = 0
                while k < len(piece) and piece[k] in _WRAPPERS:
                    k += 1
                piece = piece[:k] + piece[k].upper() + piece[k + 1:]
                fresh = False
            elif not (piece in _LIST_PREFIXES or piece.rstrip(".").isdigit()):
                fresh = False        # a bullet or a "1." is not the sentence yet
        if piece.rstrip("\"')]").endswith((".", "!", "?")):
            fresh = True
        out.append(piece)
    return "".join(out)


def _capitalisable(word):
    # The punctuation the word is wrapped in is not part of the word: "yes."
    # is still "yes", and stopping at the full stop here was making the last
    # word of every sentence look like a file name.
    core = word.lstrip("\"'([").rstrip(".,;:!?)]\"'")
    if not core or not core[0].isalpha() or not core[0].islower():
        return False
    # useState, iPhone, gRPC: the shape of the word is the meaning, so leave it.
    if any(c.isupper() for c in core):
        return False
    # package.json, v2, src/main, some_name: not prose, do not touch.
    if any(c.isdigit() or c in "._/\\@#" for c in core):
        return False
    return core not in _KEEP_LOWER


def _tidy(text):
    """Spacing and sentence capitals, and nothing more adventurous than that."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    # A space in front of punctuation is always a mistake. A MISSING space after
    # it is not: "package.json" and "3.5" are correct as they stand, so nothing
    # here inserts one.
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _capitalise_sentences(text)


# --- the one public function -----------------------------------------------



# Sounds a person makes while thinking. Parakeet is verbatim and writes them
# down; whisper quietly drops them, which is why they appeared the moment the
# language setting was put back and English started going to Parakeet again.
#
# The list is deliberately tiny. Wispr Flow's own documentation records what
# happens when it is not: a leading "so" carries a condition, deliberate
# repetition carries emphasis, and stripping those "can result in dropping or
# rewriting words that actually mattered". So this removes only the sounds
# that are not words in any sentence, and never "like", "you know", "I mean",
# "actually" or "so", all of which mean something.
_FILLER = re.compile(r"(?<![\w'])(uh+|um+|uhm+|erm+|hmm+|mm+)(?![\w'])[,]?\s*",
                     re.IGNORECASE)


def drop_fillers(text: str) -> str:
    """Remove thinking sounds, and nothing that carries meaning."""
    if not text:
        return text
    out = _FILLER.sub("", text)
    # Whatever is left of the spacing and the capital the filler was holding.
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([,.!?])", r"\1", out)
    if out and text[:1].isupper():
        out = out[:1].upper() + out[1:]
    return out or text


def shape(text, enabled=True, punctuation=True, lists=False, sentences=True,
          fillers=True):
    """Shape a raw transcript into text that reads as though it was typed.

    Pure: the same string in gives the same string out, and nothing else
    happens. Safe to call on anything, including an empty transcript.

    enabled      the single switch. False hands the transcript straight back,
                 byte for byte, which is what somebody wants the moment this
                 gets one thing wrong in the middle of their work.
    punctuation  spoken punctuation becomes characters ("question mark" -> "?").
                 Only words that were actually said; nothing is guessed from a
                 pause. Say "a comma" or "the word comma" to keep the word.
    lists        restructure a spoken list into numbered lines or bullets.
                 Off by default, and on purpose: this is the only rule that
                 moves the user's words around, so it is the only one that
                 needs asking for. Needs three ascending markers at clause
                 starts, each with real content behind it.
    sentences    tidy the spacing and put a capital at the start of a sentence.
    """
    if not enabled:
        return text
    if fillers:
        text = drop_fillers(text)
    if not enabled or not text or not text.strip():
        return text
    out = text
    if punctuation:
        out = _spoken_punctuation(out)
    if lists:
        shaped = _bulleted(out)
        if shaped == out:           # one shape per utterance, never both
            shaped = _numbered(out)
        out = shaped
    if sentences:
        out = _tidy(out)
    return out.strip("\n") if out.strip("\n") else out
