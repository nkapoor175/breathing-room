"""Announcements (A06): English announcement -> English + Tamil + Hindi.

A wrong loudspeaker instruction is worse than none, so each translation is either
  1. native-speaker approved: act/announcements_approved.json maps an exact English
     line to its Tamil and Hindi, e.g.
       {"Please move calmly to your left, towards Gate 1.":
          {"ta": "...", "hi": "...", "checked_by": "name, date"}}
     (entries without "checked_by" are ignored), or
  2. machine translated by Nemotron 3 Ultra and then checked in code: right script
     only, left/right not flipped, every gate number kept, not too long.
A language that fails the check twice is left out; the dashboard then plays English.

Model: Ultra with reasoning on. In an Oct 25 test Lightning and Super both turned
"left" into "right" in Tamil (Lightning also mixed in Korean); Ultra got directions
right in every line. ANNOUNCE_MODEL switches the model.
"""
import json, os, re
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel

ANNOUNCE_MODEL = os.environ.get("ANNOUNCE_MODEL", "ultra")
APPROVED_FILE = Path(__file__).parent / "announcements_approved.json"
MAX_WORDS = 25            # Tamil/Hindi run a little longer than the 20-word English line
LANGS = ("ta", "hi")


class Translations(BaseModel):
    ta: str
    hi: str


Ask = Callable[[str], Translations]

SCRIPT = {"ta": (0x0B80, 0x0BFF), "hi": (0x0900, 0x097F)}
NATIVE_DIGITS = {"ta": "௦௧௨௩௪௫௬௭௮௯", "hi": "०१२३४५६७८९"}
# Words for left and right. Tamil "இடம்" means "place/space", so match the direction forms only.
LEFT = {"en": r"\bleft\b", "ta": r"இடது|இடப்பக்க|இடப்புற|இடதுபுற", "hi": r"बा[ईएय]"}
RIGHT = {"en": r"\bright\b", "ta": r"வலது|வலப்பக்க|வலப்புற|வலதுபுற", "hi": r"दा[ईएयह]"}


def check(en: str, lang: str, text: str) -> list[str]:
    """Problems with one translation; empty list = OK."""
    problems = []
    lo, hi = SCRIPT[lang]
    foreign = {c for c in text if c.isalpha() and not c.isascii() and not lo <= ord(c) <= hi}
    if foreign:
        problems.append(f"letters from another script: {''.join(sorted(foreign))}")

    normal = text.translate(str.maketrans(NATIVE_DIGITS[lang], "0123456789"))
    missing = set(re.findall(r"\d+", en)) - set(re.findall(r"\d+", normal))
    if missing:
        problems.append(f"gate/number {sorted(missing)} missing")

    en_l = en.lower()
    for name, words, opposite in (("left", LEFT, RIGHT), ("right", RIGHT, LEFT)):
        says = bool(re.search(words["en"], en_l))
        if says and not re.search(words[lang], text):
            problems.append(f"English says {name}, translation doesn't")
        if not says and re.search(words[lang], text) and not re.search(opposite["en"], en_l):
            problems.append(f"translation adds '{name}'")
        if says and not re.search(opposite["en"], en_l) and re.search(opposite[lang], text):
            problems.append(f"English says {name}, translation says the opposite")

    if len(text.split()) > MAX_WORDS:
        problems.append(f"{len(text.split())} words")
    return problems


def load_approved(path: Path = APPROVED_FILE) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {en: v for en, v in data.items() if v.get("checked_by") and all(v.get(l) for l in LANGS)}


class Announcer:
    def __init__(self, ask: Ask, approved: Optional[dict] = None, log: Callable[[str], None] = print):
        self.ask = ask
        self.approved = load_approved() if approved is None else approved
        self.cache: dict[str, dict[str, str]] = {}
        self.log = log

    def texts(self, en: str) -> dict[str, str]:
        """{"en": ..., "ta": ..., "hi": ...}, leaving out any language that failed the check."""
        en = en.strip()
        if en in self.approved:
            return {"en": en, **{l: self.approved[en][l] for l in LANGS}}
        if en in self.cache:
            return dict(self.cache[en])

        out = {"en": en}
        for attempt in (1, 2):
            try:
                t = self.ask(en)
            except Exception as e:
                self.log(f"announce: translation call failed ({type(e).__name__}: {e})")
                break
            for lang in LANGS:
                if lang in out:
                    continue
                problems = check(en, lang, getattr(t, lang))
                if problems:
                    self.log(f"announce: {lang} attempt {attempt} rejected ({'; '.join(problems)}): {getattr(t, lang)}")
                else:
                    out[lang] = getattr(t, lang).strip()
            if all(l in out for l in LANGS):
                break
        missing = [l for l in LANGS if l not in out]
        if missing:
            self.log(f"announce: no safe {'/'.join(missing)} translation; English only for those")
        self.cache[en] = out
        return dict(out)


def nemotron_ask(on_cost, role: str = ANNOUNCE_MODEL) -> Ask:
    from common.llm import call_json
    system = (Path(__file__).parent / "prompts" / "announce.md").read_text(encoding="utf-8")

    def ask(en: str) -> Translations:
        return call_json(role, "announce", system, en, Translations, on_cost=on_cost)
    return ask
