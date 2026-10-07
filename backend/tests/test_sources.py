"""Parsers for the job-board APIs, tested against fixtures shaped like the documented responses."""
import pytest

from app.sources import ats, boards, parse_board_spec, parse_pasted

GREENHOUSE_JOBS = {
    "jobs": [
        {
            "id": 101,
            "title": "Reliability Engineer",
            "location": {"name": "Remote - EMEA"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
            "updated_at": "2026-09-01T10:00:00Z",
            "content": "&lt;h3&gt;Requirements&lt;/h3&gt;&lt;ul&gt;&lt;li&gt;FMEA&lt;/li&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;",
            "departments": [{"name": "Engineering"}],
        }
    ]
}
LEVER = [
    {
        "id": "abc",
        "text": "Data Analyst",
        "categories": {"location": "Paris", "team": "Data", "commitment": "Full-time"},
        "workplaceType": "hybrid",
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "createdAt": 1767225600000,
        "descriptionPlain": "Join our data team.",
        "lists": [{"text": "Requirements", "content": "<li>SQL</li><li>Power BI</li>"}],
        "additionalPlain": "",
    }
]
ASHBY = {
    "jobs": [
        {
            "id": "x1",
            "title": "ML Engineer",
            "location": "Berlin",
            "isListed": True,
            "isRemote": False,
            "workplaceType": "OnSite",
            "descriptionPlain": "Requirements\n- PyTorch\n- Docker",
            "jobUrl": "https://jobs.ashbyhq.com/acme/x1",
        },
        {"id": "x2", "title": "Hidden", "isListed": False, "jobUrl": "u"},
    ]
}
REMOTIVE = {
    "jobs": [
        {
            "id": 7,
            "url": "https://remotive.com/remote-jobs/data/7",
            "title": "Data Engineer",
            "company_name": "Remote Co",
            "category": "Data",
            "job_type": "full_time",
            "publication_date": "2026-09-30T00:00:00",
            "candidate_required_location": "Europe",
            "description": "<p>Spark and Airflow</p>",
        }
    ]
}
ARBEITNOW = {
    "data": [
        {
            "slug": "dev-berlin-1",
            "company_name": "Berlin GmbH",
            "title": "Backend Developer",
            "description": "<p>Go and Kubernetes</p>",
            "remote": True,
            "url": "https://www.arbeitnow.com/jobs/dev-berlin-1",
            "tags": ["IT"],
            "job_types": ["full time"],
            "location": "Berlin",
            "created_at": 1767225600,
        }
    ]
}


@pytest.fixture
def fake_http(monkeypatch):
    def fake_get_json(url, params=None, ttl=0, allow_404=False):
        if "greenhouse" in url:
            return GREENHOUSE_JOBS if url.endswith("/jobs") else {"name": "Acme Corp"}
        if "lever" in url:
            return LEVER
        if "ashby" in url:
            return ASHBY
        if "remotive" in url:
            return REMOTIVE
        if "arbeitnow" in url:
            return ARBEITNOW if (params or {}).get("page") == 1 else {"data": []}
        return None

    monkeypatch.setattr(ats, "get_json", fake_get_json)
    monkeypatch.setattr(boards, "get_json", fake_get_json)


def test_board_specs():
    assert parse_board_spec("https://boards.greenhouse.io/stripe").ats == "greenhouse"
    assert parse_board_spec("https://jobs.lever.co/palantir/123").slug == "palantir"
    assert parse_board_spec("jobs.ashbyhq.com/linear").ats == "ashby"
    assert parse_board_spec("notion").ats is None


def test_greenhouse(fake_http):
    desc, jobs = ats.fetch_board("greenhouse:acme")
    j = jobs[0]
    assert j.company == "Acme Corp" and j.workplace == "remote"
    assert "• FMEA" in j.description and "<" not in j.description


def test_lever_and_ashby(fake_http):
    _, lever = ats.fetch_board("lever:acme")
    assert lever[0].workplace == "hybrid" and "Power BI" in lever[0].description
    _, ashby = ats.fetch_board("ashby:acme")
    assert len(ashby) == 1 and ashby[0].workplace == "onsite"


def test_keyword_boards(fake_http):
    r = boards.fetch_remotive("data")
    assert r[0].attribution.startswith("Job via Remotive") and r[0].workplace == "remote"
    a = boards.fetch_arbeitnow(pages=2)
    assert a[0].workplace == "remote" and "Kubernetes" in a[0].description


def test_pasted_postings():
    jobs = parse_pasted("Title: QA Engineer\nCompany: Foo\n\nRequirements\n- Cypress\n---\nData Analyst\nSQL and Excel needed.")
    assert [j.title for j in jobs] == ["QA Engineer", "Data Analyst"]
    assert jobs[0].company == "Foo"
