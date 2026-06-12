"""Tests für das Keyword-Matching und die Score-Kombination."""
from __future__ import annotations

from backend.config import (
    DEFAULT_NEGATIVE_KEYWORDS,
    DEFAULT_POSITIVE_KEYWORDS,
    DEFAULT_TITLE_BLOCKLIST,
)
from backend.matching import (
    combined_score,
    keyword_score,
    location_allowed,
    looks_remote,
    title_blocked,
    title_matches,
)

JAVA_JOB = (
    "Wir suchen einen Java Developer mit Spring Boot, Angular und TypeScript. "
    "Sie arbeiten mit REST APIs, MongoDB, Git und GitLab im Backend-Team. "
    "JUnit-Tests gehören zum Alltag."
)

SAP_JOB = (
    "Senior Lead SAP Architect gesucht. 10+ Jahre Erfahrung mit COBOL und "
    "Embedded-Systemen zwingend erforderlich. Principal-Level."
)


def test_java_job_scores_above_threshold() -> None:
    score = keyword_score(JAVA_JOB, DEFAULT_POSITIVE_KEYWORDS, DEFAULT_NEGATIVE_KEYWORDS)
    assert score >= 60


def test_sap_job_scores_below_threshold() -> None:
    score = keyword_score(SAP_JOB, DEFAULT_POSITIVE_KEYWORDS, DEFAULT_NEGATIVE_KEYWORDS)
    assert score < 60


def test_score_is_clamped_between_0_and_100() -> None:
    many_negatives = " ".join(DEFAULT_NEGATIVE_KEYWORDS) * 3
    assert keyword_score(many_negatives, DEFAULT_POSITIVE_KEYWORDS, DEFAULT_NEGATIVE_KEYWORDS) == 0
    many_positives = " ".join(DEFAULT_POSITIVE_KEYWORDS) * 3
    assert 0 <= keyword_score(many_positives, DEFAULT_POSITIVE_KEYWORDS, DEFAULT_NEGATIVE_KEYWORDS) <= 100


def test_word_boundaries_prevent_false_positives() -> None:
    # "rest" in "Restaurant" darf nicht als REST-Treffer zählen
    score_restaurant = keyword_score("Restaurant Manager", ("REST",), ())
    assert score_restaurant == keyword_score("Manager", ("REST",), ())


def test_combined_score_without_llm_uses_keyword_score() -> None:
    assert combined_score(70, None) == 70


def test_combined_score_weights_llm_higher_by_default() -> None:
    # Standard: 40 % Keywords, 60 % LLM
    assert combined_score(60, 80) == 72
    assert combined_score(0, 100) == 60


def test_combined_score_respects_custom_weight() -> None:
    assert combined_score(60, 80, llm_weight=0.5) == 70
    assert combined_score(60, 80, llm_weight=1.0) == 80
    assert combined_score(60, 80, llm_weight=0.0) == 60


def test_title_matches_accepts_relevant_titles() -> None:
    keywords = ("Java Developer", "Backend Engineer")
    assert title_matches("Junior Java Developer (m/w/d)", keywords)
    assert title_matches("Softwareentwickler Backend", keywords)
    assert title_matches("Full Stack Engineer", keywords)


def test_title_matches_rejects_irrelevant_titles() -> None:
    keywords = ("Java Developer", "Backend Engineer")
    assert not title_matches("Marketing Manager", keywords)
    assert not title_matches("Pflegefachkraft", keywords)


def test_title_matches_rejects_bare_engineer_titles() -> None:
    # Regression: "Value Engineer" & Co. dürfen nicht über das nackte
    # Wort "engineer" hereinrutschen
    keywords = ("Java Developer", "Backend Engineer")
    assert not title_matches("Value Engineer", keywords)
    assert not title_matches("System Engineer", keywords)


def test_title_matches_accepts_csharp_and_dotnet() -> None:
    keywords = ("Java Developer",)
    assert title_matches("C# Entwickler (m/w/d)", keywords)
    assert title_matches(".NET Developer", keywords)


def test_title_blocked_filters_senior_roles() -> None:
    assert title_blocked("Senior Software Engineer", DEFAULT_TITLE_BLOCKLIST)
    assert title_blocked("Staff System Engineer", DEFAULT_TITLE_BLOCKLIST)
    assert title_blocked("Vice President, Value Engineering", DEFAULT_TITLE_BLOCKLIST)
    assert title_blocked("Tech Lead Backend", DEFAULT_TITLE_BLOCKLIST)
    assert title_blocked("Engineering Manager", DEFAULT_TITLE_BLOCKLIST)


def test_title_blocked_allows_junior_and_mid_roles() -> None:
    assert not title_blocked("Junior Java Developer", DEFAULT_TITLE_BLOCKLIST)
    assert not title_blocked("Softwareentwickler Java (m/w/d)", DEFAULT_TITLE_BLOCKLIST)
    assert not title_blocked("Backend Engineer", DEFAULT_TITLE_BLOCKLIST)
    # "Leadership" enthält "lead" nur als Teilwort und darf nicht sperren
    assert not title_blocked("Developer with leadership training", DEFAULT_TITLE_BLOCKLIST)


def test_location_allowed_accepts_germany() -> None:
    assert location_allowed("Berlin", remote=False)
    assert location_allowed("München, Deutschland", remote=False)
    assert location_allowed("Geldern, Germany", remote=False)
    assert location_allowed("Düsseldorf (Hybrid)", remote=False)


def test_location_allowed_rejects_foreign_onsite() -> None:
    assert not location_allowed("Sacramento, CA", remote=False)
    assert not location_allowed("New York, USA", remote=False)
    assert not location_allowed("Paris, France", remote=False)
    assert not location_allowed("Zürich, Schweiz", remote=False)


def test_location_allowed_accepts_remote_anywhere() -> None:
    assert location_allowed("New York, USA", remote=True)
    assert location_allowed("Remote - Europe", remote=True)


def test_location_allowed_keeps_unknown_location() -> None:
    assert location_allowed("", remote=False)
    assert location_allowed("   ", remote=False)


def test_looks_remote_detects_remote_hints() -> None:
    assert looks_remote("Java Developer", "Remote, Germany")
    assert looks_remote("Entwickler (Homeoffice möglich)", "")
    assert not looks_remote("Java Developer", "Berlin")
