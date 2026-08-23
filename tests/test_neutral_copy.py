"""The cast's copy says "they".

The wording is spread over a shelf, a library tab, a mention menu, three
dictionaries and two documents, so a stray "she" written back into any of them
would be invisible until somebody read it on screen.

`presets/atlas.js` and `prompts/` are skipped: both describe the people in
example footage rather than the user's cast.

    python3 tests/test_neutral_copy.py
"""

import os
import re
import sys

import layout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The pronouns, and the two nouns that carry the same reading.
ENGLISH = re.compile(r"\b(she|her|hers|herself|he|him|his|himself|woman|women|man|men)\b",
                     re.IGNORECASE)
# The same words in each dictionary.
# 他 is matched only where it stands alone: it is the second half of 其他
# ("other"), which is an ordinary word and all over the Chinese dictionary.
GENDERED = {"ja": ["彼女", "彼氏"], "zh": ["她", "(?<!其)他"], "ko": ["그녀"]}

SKIP = {os.path.join("web", "creator", "presets", "atlas.js")}

# "man" and "men" are in the pattern for the cast's sake and are ordinary words
# elsewhere — a *man*ifest, the *men*u. These are the ones this pack means.
# Two sentences that are somebody else's words rather than the pack's: the
# example the user is shown for "who does this clip's occupant get replaced by",
# and MiniMax's own guide example, quoted so the code beside it can be checked
# against the guide.
ALLOWED = re.compile(r"man at the counter|<Subject 1> is the young woman", re.IGNORECASE)


def files():
    for name in ("README.md", "CHANGELOG.md"):
        yield os.path.join(ROOT, name)
    for base, dirs, names in os.walk(os.path.join(ROOT, "web")):
        dirs[:] = [d for d in dirs if d != "atlas"]
        for name in names:
            path = os.path.join(base, name)
            if name.endswith(".js") and os.path.relpath(path, ROOT) not in SKIP:
                yield path
    for name in sorted(os.listdir(ROOT)):
        if name.endswith(".py"):
            yield os.path.join(ROOT, name)


from harness import FAILURES, passed

for path in files():
    where = os.path.relpath(path, ROOT)
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            # The English pronouns, in the pack's own sentences.
            for match in ENGLISH.finditer(line):
                word = match.group(0).lower()
                # Only the pronouns are unconditional; the nouns are ordinary
                # words in the wrong context and are checked where the cast is
                # actually being described.
                if word in {"man", "men", "woman", "women"} and "subject" not in line.lower():
                    continue
                if ALLOWED.search(line):
                    continue
                FAILURES.append(f"{where}:{number} says {match.group(0)!r} — "
                                f"the cast is 'they': {line.strip()[:90]}")
            for lang, words in GENDERED.items():
                if not where.endswith(f"locales/{lang}.js"):
                    continue
                for word in words:
                    if re.search(word, line):
                        FAILURES.append(f"{where}:{number} says {word!r} — "
                                        f"the cast is 'they' in every language")

passed("the cast has no gender the user did not give it")
