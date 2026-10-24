"""Announcement translation checks: catch the mistakes the models actually made on Oct 25."""
import pytest

from act.announce import Announcer, Translations, check

GATE1_LEFT = "Please move calmly to your left, towards Gate 1."
GOOD_TA = "அமைதியாக உங்கள் இடப்பக்கம், கேட் 1 நோக்கி செல்லுங்கள்."
GOOD_HI = "शांति से अपने बाईं ओर, गेट 1 की तरफ बढ़ें।"


def test_good_translations_pass():
    assert check(GATE1_LEFT, "ta", GOOD_TA) == []
    assert check(GATE1_LEFT, "hi", GOOD_HI) == []
    assert check("Gate 3 is closed. Please use Gate 2 on your right.", "hi",
                 "गेट 3 बंद है। कृपया अपने दाईं ओर गेट 2 का उपयोग करें।") == []


def test_flipped_direction_caught():
    # Super's real Oct 25 output: English says left, Tamil says right (வலதுபக்கம்).
    problems = check(GATE1_LEFT, "ta", "தயவுசெய்து உங்கள் வலதுபக்கம், கேட் 1க்கு செல்க.")
    assert any("opposite" in p for p in problems) and any("doesn't" in p for p in problems)


def test_other_script_caught():
    # Lightning's real output mixed in Korean.
    problems = check(GATE1_LEFT, "ta", "தயவுசெய்து உங்கள் இடது 쪽으로 செல்லவும், கேட் 1.")
    assert any("another script" in p for p in problems)


def test_malayalam_letters_caught():
    problems = check("Please walk to the Overflow ground.", "ta", "ஓவർഃப்லோ மைதானம் நோக்கி நடக்கவும்.")
    assert any("another script" in p for p in problems)


def test_missing_gate_number_caught():
    assert any("missing" in p for p in check(GATE1_LEFT, "hi", "कृपया शांति से बाईं ओर गेट की तरफ जाएं।"))


def test_native_digits_accepted():
    assert check(GATE1_LEFT, "hi", "शांति से अपने बाईं ओर, गेट १ की तरफ बढ़ें।") == []


def test_added_direction_caught():
    assert any("adds 'right'" in p for p in check("Please walk towards Gate 1.", "hi", "दाईं ओर गेट 1 की तरफ चलें।"))


def test_tamil_word_for_space_is_not_left():
    # "இடம்" (place/space) must not count as "left".
    assert check("Do not push. Keep space for others.", "ta", "தள்ளாதீர்கள். மற்றவர்களுக்கு இடம் கொடுக்கவும்.") == []


def test_too_long_caught():
    assert any("words" in p for p in check("Move left.", "hi", " ".join(["बाईं"] * 30)))


class FakeModel:
    def __init__(self, *replies, fail=False):
        self.replies, self.fail, self.calls = list(replies), fail, 0

    def __call__(self, en):
        self.calls += 1
        if self.fail:
            raise RuntimeError("down")
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


def test_announcer_good_first_try_and_cached():
    m = FakeModel(Translations(ta=GOOD_TA, hi=GOOD_HI))
    a = Announcer(m, approved={}, log=lambda s: None)
    assert a.texts(GATE1_LEFT) == {"en": GATE1_LEFT, "ta": GOOD_TA, "hi": GOOD_HI}
    a.texts(GATE1_LEFT)
    assert m.calls == 1


def test_announcer_retries_only_failed_language():
    bad_ta = "தயவுசெய்து உங்கள் வலதுபக்கம், கேட் 1க்கு செல்க."
    m = FakeModel(Translations(ta=bad_ta, hi=GOOD_HI), Translations(ta=GOOD_TA, hi="wrong"))
    out = Announcer(m, approved={}, log=lambda s: None).texts(GATE1_LEFT)
    assert out == {"en": GATE1_LEFT, "ta": GOOD_TA, "hi": GOOD_HI} and m.calls == 2


def test_announcer_drops_language_that_keeps_failing():
    bad_ta = "தயவுசெய்து உங்கள் வலதுபக்கம், கேட் 1க்கு செல்க."
    m = FakeModel(Translations(ta=bad_ta, hi=GOOD_HI))
    out = Announcer(m, approved={}, log=lambda s: None).texts(GATE1_LEFT)
    assert out == {"en": GATE1_LEFT, "hi": GOOD_HI} and m.calls == 2


def test_announcer_model_down_gives_english_only():
    out = Announcer(FakeModel(fail=True), approved={}, log=lambda s: None).texts(GATE1_LEFT)
    assert out == {"en": GATE1_LEFT}


def test_approved_line_skips_model():
    m = FakeModel(fail=True)
    approved = {GATE1_LEFT: {"ta": "APPROVED TA", "hi": "APPROVED HI", "checked_by": "Priya, Oct 26"}}
    out = Announcer(m, approved=approved, log=lambda s: None).texts(GATE1_LEFT)
    assert out["ta"] == "APPROVED TA" and m.calls == 0


def test_unchecked_approved_entries_ignored(tmp_path):
    from act.announce import load_approved
    f = tmp_path / "a.json"
    f.write_text('{"Move left.": {"ta": "x", "hi": "y"}, "Move right.": {"ta": "x", "hi": "y", "checked_by": "R"}}',
                 encoding="utf-8")
    assert list(load_approved(f)) == ["Move right."]
