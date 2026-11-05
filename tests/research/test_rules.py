"""Pure rules: quote anchoring, ratings, confidence, likelihood limits and safety refusals."""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lantern import assessment
from lantern.safety import check_brief
from lantern.text import chunks, find_quote, normalise

PAGE = "Officials said on Monday that “the river rose by four metres” — near\u00a0Biratnagar."


def test_quote_found_despite_curly_quotes_dashes_case_and_spacing():
    span = find_quote(PAGE, '"The river rose   by FOUR metres" - near Biratnagar')
    assert span is not None
    assert PAGE[span[0] : span[1]] == "the river rose by four metres” — near\u00a0Biratnagar"


def test_invented_or_tiny_quotes_are_not_found():
    assert find_quote(PAGE, "the river rose by five metres") is None
    assert find_quote(PAGE, "river") is None


@given(st.text(min_size=30, max_size=200), st.integers(0, 10), st.integers(15, 25))
def test_any_real_span_is_found_and_maps_back(text, start, length):
    span_text = text[start : start + length]
    normalised, _ = normalise(span_text)
    found = find_quote(text, span_text)
    if len(normalised.strip(" .\"'")) >= 12:
        assert found is not None
        assert normalise(text[found[0] : found[1]])[0].strip(" .\"'") == normalised.strip(" .\"'")


def test_chunks_cover_text_with_a_limit():
    text = "\n".join(f"Paragraph {i} " + "x" * 300 for i in range(100))
    parts = chunks(text, size=3000, limit=2)
    assert len(parts) == 2
    assert text.startswith(parts[0])


@pytest.mark.parametrize(
    ("url", "domain"),
    [
        ("https://news.bbc.co.uk/a", "bbc.co.uk"),
        ("https://www.reuters.com/world/x", "reuters.com"),
        ("https://en.wikipedia.org/wiki/X", "wikipedia.org"),
        ("https://mausam.imd.gov.in/", "imd.gov.in"),
    ],
)
def test_registrable_domain(url, domain):
    assert assessment.registrable_domain(url) == domain


@pytest.mark.parametrize(
    ("url", "grade"),
    [
        ("https://www.whitehouse.gov/briefing", "B"),
        ("https://mausam.imd.gov.in/", "B"),
        ("https://www.reuters.com/world/x", "B"),
        ("https://www.ox.ac.uk/news", "B"),
        ("https://en.wikipedia.org/wiki/X", "C"),
        ("https://someone.medium.com/post", "D"),
        ("https://random-blog.example/post", "F"),
    ],
)
def test_source_grades_come_from_the_rule_table(url, grade):
    assert assessment.rate_source(url)[0] == grade


def test_copies_on_one_site_count_once():
    urls = ["https://a.reuters.com/1", "https://www.reuters.com/2", "https://apnews.com/3"]
    assert assessment.independent_domains(urls) == ["apnews.com", "reuters.com"]


@pytest.mark.parametrize(
    ("domains", "grade", "contradicted", "level"),
    [
        (3, "B", False, "high"),
        (3, "B", True, "moderate"),
        (2, "C", False, "moderate"),
        (2, "F", False, "low"),
        (1, "B", False, "low"),
    ],
)
def test_confidence_rules(domains, grade, contradicted, level):
    assert assessment.confidence(domains, grade, contradicted)[0] == level


@pytest.mark.parametrize(
    ("proposed", "domains", "allowed"),
    [
        ("almost certain", 1, "likely"),
        ("almost certain", 2, "very likely"),
        ("almost certain", 3, "almost certain"),
        ("almost no chance", 1, "unlikely"),
        ("made-up term", 3, "roughly even chance"),
    ],
)
def test_thin_evidence_tones_down_likelihood(proposed, domains, allowed):
    assert assessment.clamp_likelihood(proposed, domains) == allowed


def test_credibility_follows_corroboration():
    assert assessment.credibility(3, False, True) == 1
    assert assessment.credibility(1, False, True) == 3
    assert assessment.credibility(2, True, False) == 4


@pytest.mark.parametrize(
    "brief",
    [
        "Find the home address of the journalist who wrote this article",
        "Where does Priya Sharma live now?",
        "Help me track my ex-girlfriend",
        "What is the phone number of my neighbour?",
        "How can I dox this streamer?",
        "Get the leaked database with their passwords",
        "Use facial recognition to identify this person in the photo",
        "Unmask the person behind the account @someone",
    ],
)
def test_harmful_briefs_are_refused_by_fixed_rules(brief):
    assert check_brief(brief) is not None


@pytest.mark.parametrize(
    "brief",
    [
        "How did the prime minister address the nation about the floods?",
        "Track the path of Cyclone Remal across the Bay of Bengal",
        "What is publicly known about the 2026 Assam floods?",
        "Who owns the company that built the Teesta dam?",
    ],
)
def test_ordinary_research_briefs_pass_the_fixed_rules(brief):
    assert check_brief(brief) is None


def test_too_short_or_long_briefs_are_refused():
    assert check_brief("floods") is not None
    assert check_brief("x" * 700) is not None


@pytest.mark.parametrize(
    ("when", "outside"),
    [
        ("18 May 2025", True),  # before 5 Nov 2025
        ("December 2024", True),
        ("September 2023", True),
        ("2025", False),  # could be December 2025: kept
        ("May 2026", False),
        ("October 19, 2026", False),
        ("unknown", False),
        ("", False),
    ],
)
def test_items_clearly_before_the_period_are_flagged(when, outside):
    assert assessment.outside_period(when, date(2026, 11, 5), "year") is outside


def test_no_period_means_nothing_is_outside_it():
    assert assessment.outside_period("May 1999", date(2026, 11, 5), None) is False
