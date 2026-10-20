from applyfirst.tailor.contract import ScreeningQA, TailoredPackage
from applyfirst.tailor.plain import plain_package, plain_words


def test_stiff_words_become_plain():
    assert plain_words("I leverage AI tools to optimize code.") == "I use AI tools to improve code."
    assert plain_words("The employer is seeking a proficient developer.") == "The employer wants a skilled developer."
    assert plain_words("build modern, scalable web apps") == "build modern web apps"
    assert plain_words("build scalable Next.js apps") == "build Next.js apps"
    assert plain_words("Leveraging Claude, I ship fast") == "Using Claude, I ship fast"


def test_dashes_in_sentences_become_commas():
    assert plain_words("Fast work — real results") == "Fast work, real results"


def test_links_and_plain_text_are_untouched():
    text = "See https://example.com/optimize-leverage and sweetblooms.ph (shop)"
    assert plain_words(text) == text
    assert plain_words("") == ""


def test_package_cleans_letter_digest_and_answers_but_not_subject():
    pkg = TailoredPackage(
        digest="They are seeking robust code.",
        application_subject="Web Developer – Omhar Regidor",
        screening_questions=[ScreeningQA(question="Git?", drafted_answer="I utilize Git daily.")],
        cover_letter="Hi. I leverage n8n.",
    )
    out = plain_package(pkg)
    assert out.digest == "They want solid code."
    assert out.screening_questions[0].drafted_answer == "I use Git daily."
    assert out.cover_letter == "Hi. I use n8n."
    assert out.application_subject == "Web Developer – Omhar Regidor"


def test_required_opening_word_is_kept_exactly():
    pkg = TailoredPackage(compliance_token="LEVERAGE", cover_letter="LEVERAGE Hi, I leverage AI.")
    assert plain_package(pkg).cover_letter == "LEVERAGE Hi, I use AI."
