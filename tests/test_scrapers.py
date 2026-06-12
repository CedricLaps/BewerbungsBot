"""Tests für API-basierte Scraper (mit gemockter HTTP-Session) und URL-Bereinigung."""
from __future__ import annotations

import json

import pytest

from backend.ats import is_supported_ats
from backend.config import AppConfig
from scrapers.base import JobPosting, clean_url
from scrapers.greenhouse import GreenhouseScraper
from scrapers.lever import LeverScraper
from scrapers.linkedin import extract_apply_url
from scrapers.manager import ScraperManager

GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "title": "Backend Engineer (Java)",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/123?gh_src=abc",
            "location": {"name": "Berlin, Germany"},
            "content": "<p>Wir suchen Java und Spring Boot Erfahrung.</p>",
            "company_name": "Acme",
        },
        {
            "title": "Marketing Manager",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/124",
            "location": {"name": "Berlin"},
            "content": "<p>Marketing</p>",
        },
    ]
}

LEVER_PAYLOAD = [
    {
        "text": "Java Developer",
        "hostedUrl": "https://jobs.lever.co/acme/abc-def",
        "categories": {"location": "Remote, Germany"},
        "descriptionPlain": "Spring Boot, REST APIs",
        "workplaceType": "remote",
    },
    {
        "text": "Sales Representative",
        "hostedUrl": "https://jobs.lever.co/acme/xyz",
        "categories": {"location": "Berlin"},
        "descriptionPlain": "Vertrieb",
    },
]


def patch_session_get(scraper: object, fake_response_class: type, payload: object) -> None:
    def fake_get(url: str, timeout: int = 30, **kwargs: object) -> object:
        return fake_response_class(
            status_code=200, json_data=payload, text=json.dumps(payload)
        )

    scraper.session.get = fake_get  # type: ignore[attr-defined]


def test_greenhouse_scraper_filters_by_title(
    fake_response_class: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(greenhouse_boards=("acme",), request_delay_seconds=0.0)
    scraper = GreenhouseScraper(config)
    patch_session_get(scraper, fake_response_class, GREENHOUSE_PAYLOAD)
    postings = scraper.search()
    assert len(postings) == 1
    posting = postings[0]
    assert posting.title == "Backend Engineer (Java)"
    assert posting.company == "Acme"
    assert "Spring Boot" in posting.description
    assert "gh_src" not in posting.url


def test_lever_scraper_detects_remote(
    fake_response_class: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig(lever_companies=("acme",), request_delay_seconds=0.0)
    scraper = LeverScraper(config)
    patch_session_get(scraper, fake_response_class, LEVER_PAYLOAD)
    postings = scraper.search()
    assert len(postings) == 1
    assert postings[0].remote is True
    assert postings[0].source == "lever"


def test_scraper_handles_404_board(fake_response_class: type) -> None:
    config = AppConfig(greenhouse_boards=("gibtsnicht",), request_delay_seconds=0.0)
    scraper = GreenhouseScraper(config)

    def fake_get(url: str, timeout: int = 30, **kwargs: object) -> object:
        return fake_response_class(status_code=404, json_data=None)

    scraper.session.get = fake_get  # type: ignore[method-assign]
    assert scraper.search() == []


def test_clean_url_strips_tracking_params() -> None:
    url = "https://example.com/job/1?refId=xyz&utm_source=feed&page=2#section"
    cleaned = clean_url(url)
    assert "refId" not in cleaned
    assert "utm_source" not in cleaned
    assert "page=2" in cleaned
    assert "#" not in cleaned


def test_job_posting_normalizes_and_detects_remote() -> None:
    posting = JobPosting(
        title="  Java Developer  ",
        company=" Acme ",
        url="https://example.com/job?trackingId=1",
        source="test",
        location="Remote (Germany)",
    )
    assert posting.title == "Java Developer"
    assert posting.company == "Acme"
    assert posting.remote is True
    assert "trackingId" not in posting.url


def test_extract_apply_url_from_guest_html() -> None:
    detail_html = (
        '<code id="applyUrl" style="display: none">'
        '<!--"https://acme.jobs.personio.de/job/123?src=LinkedIn&amp;x=1"--></code>'
    )
    assert (
        extract_apply_url(detail_html)
        == "https://acme.jobs.personio.de/job/123?src=LinkedIn&x=1"
    )


def test_extract_apply_url_returns_none_without_target() -> None:
    assert extract_apply_url("<html><body>kein Ziel</body></html>") is None


def test_is_supported_ats_recognizes_platforms() -> None:
    assert is_supported_ats("https://boards.greenhouse.io/acme/jobs/1")
    assert is_supported_ats("https://jobs.lever.co/acme/abc")
    assert is_supported_ats("https://acme.jobs.personio.de/job/1")
    assert is_supported_ats("https://acme.wd3.myworkdayjobs.com/External/job/X")
    assert not is_supported_ats("https://de.linkedin.com/jobs/view/1")
    assert not is_supported_ats("https://www.firma-karriere.de/jobs/1")


def test_manager_deduplicates_by_url_and_identity() -> None:
    postings = [
        JobPosting(title="Java Dev", company="Acme", url="https://a.example/1", source="s1"),
        JobPosting(title="Java Dev", company="Acme", url="https://a.example/1", source="s2"),
        JobPosting(title="Java Dev", company="Acme", url="https://b.example/2", source="s3"),
        JobPosting(title="Backend Dev", company="Acme", url="https://a.example/3", source="s1"),
    ]
    unique = ScraperManager._deduplicate(postings)
    assert len(unique) == 2
    assert {posting.title for posting in unique} == {"Java Dev", "Backend Dev"}
