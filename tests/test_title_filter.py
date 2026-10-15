from applyfirst.pipeline import title_matches

WORDS = ["developer", "engineer", "programmer", "n8n", "automation", "coding"]


def test_no_words_lets_every_job_through():
    assert title_matches("Senior Accountant", [])
    assert title_matches("Senior Accountant", None)


def test_dev_titles_pass_any_case():
    assert title_matches("Senior Full-Stack Mobile and Web Developer", WORDS)
    assert title_matches("AI Agent Developer (Claude Agent SDK)", WORDS)
    assert title_matches("N8N Workflow Builder", WORDS)
    assert title_matches("Shopify Editor | Shopify Website Specialist & Coding Expert", WORDS)


def test_off_topic_titles_are_skipped():
    assert not title_matches("E-Commerce Shopify Customer Service Specialist", WORDS)
    assert not title_matches("Senior Meta Ads Media Buyer (E-Commerce)", WORDS)
    assert not title_matches(None, WORDS)
