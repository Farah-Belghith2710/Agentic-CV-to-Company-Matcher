"""Jobs collected from LinkedIn by you: the paste box, the Send to CV Matcher button, and ranking them."""
import time
from pathlib import Path

from conftest import sample_text
from fastapi.testclient import TestClient

from app.main import app
from app.sources.linkedin import looks_like_linkedin, parse_linkedin_text
from app.sources.local import parse_pasted

FIX = Path(__file__).parent / "fixtures" / "linkedin"


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_logged_in_page_in_english():
    f = parse_linkedin_text(read("logged_in_en.txt"))
    assert f.title == "Reliability Engineering Intern (PFE)"
    assert f.company == "Medjerda Rail Services"
    assert f.location == "Tunis, Tunisia"
    assert f.workplace == "onsite" and f.internship
    assert f.description.startswith("Medjerda Rail Services maintains")
    assert "Weibull analysis" in f.description and "Power BI" in f.description
    for junk in ("See more", "Set alert", "About the company", "Easy Apply", "Meet the hiring team"):
        assert junk not in f.description


def test_logged_in_page_in_french():
    f = parse_linkedin_text(read("logged_in_fr.txt"))
    assert f.title == "Stage PFE - Ingénierie de maintenance"
    assert f.company == "Sahelia Food Industries"
    assert f.location == "Sousse, Tunisie"
    assert f.workplace == "onsite" and f.internship
    assert f.description.startswith("Sahelia Food Industries recherche")
    assert "AMDEC" in f.description and "Afficher moins" not in f.description


def test_signed_out_page():
    f = parse_linkedin_text(read("signed_out_en.txt"))
    assert (f.title, f.company, f.location) == ("Condition Monitoring Engineer (Wind Turbines)", "Kerkennah Wind Services", "Sfax, Tunisia")
    assert f.description.startswith("Kerkennah Wind Services runs") and "ISO 18436" in f.description
    assert "Seniority level" not in f.description and "Show more" not in f.description


def test_only_whole_linkedin_pages_are_treated_as_such():
    for name in ("logged_in_en.txt", "logged_in_fr.txt", "signed_out_en.txt"):
        assert looks_like_linkedin(read(name)), name
    plain = "Title: Reliability Engineer\nCompany: Atlas Rail\n\nRequirements\n- FMEA\n- Weibull analysis\n- Fluent French"
    assert not looks_like_linkedin(plain)


def test_paste_box_reads_copied_linkedin_pages():
    jobs = parse_pasted(read("logged_in_en.txt") + "\n---\n" + read("signed_out_en.txt"))
    assert [j.title for j in jobs] == ["Reliability Engineering Intern (PFE)", "Condition Monitoring Engineer (Wind Turbines)"]
    assert jobs[0].company == "Medjerda Rail Services" and jobs[0].location == "Tunis, Tunisia"
    assert "Skip to main content" not in jobs[0].description and "Weibull" in jobs[0].description


def _wait(client, rid, states):
    view = {}
    for _ in range(150):
        view = client.get(f"/api/runs/{rid}").json()
        if view["status"] in states:
            break
        time.sleep(0.1)
    return view


def test_button_saves_jobs_and_they_can_be_ranked():
    client = TestClient(app)
    client.delete("/api/saved")
    en = parse_linkedin_text(read("logged_in_en.txt"))
    body = {
        "url": "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=reliability",
        "title": "Reliability Engineering Intern (PFE)",
        "company": "Medjerda Rail Services",
        "location": "Tunis, Tunisia",
        "top": "Tunis, Tunisia · 1 week ago\nOn-site\nInternship",
        "description": "About the job\n" + en.description,
    }
    r = client.post("/api/saved", json=body)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["created"] and first["count"] == 1
    assert first["job"]["url"] == "https://www.linkedin.com/jobs/view/4012345678/"
    assert first["job"]["internship"] and first["job"]["workplace"] == "onsite"

    again = client.post("/api/saved", json=body).json()  # the same job twice is kept once
    assert again["created"] is False and again["count"] == 1

    # The page's description element was not found: the server reads the whole page text instead.
    r = client.post("/api/saved", json={"url": "https://www.linkedin.com/jobs/view/stage-pfe-at-sahelia-4099999999", "page_text": read("logged_in_fr.txt")})
    assert r.status_code == 200, r.text
    assert r.json()["job"]["company"] == "Sahelia Food Industries" and r.json()["count"] == 2

    r = client.post("/api/saved", json={"url": "https://www.linkedin.com/feed/", "title": "Not a job"})
    assert r.status_code == 400 and "select the description" in r.json()["detail"]

    # Only JSON from the app itself is accepted (a form posted by another website is refused).
    assert client.post("/api/saved", data={"title": "x"}).status_code == 422

    listed = client.get("/api/saved").json()
    assert listed["count"] == 2 and listed["jobs"][0]["company"] == "Sahelia Food Industries"

    r = client.post("/api/runs", data={"cv_text": sample_text("lina_haddad_reliability"), "source": "linkedin", "location": "Tunis"})
    assert r.status_code == 200, r.text
    view = _wait(client, r.json()["run_id"], ("awaiting_selection", "error"))
    assert view["status"] == "awaiting_selection", view.get("error")
    assert len(view["ranked"]) == 2 and {j["job"]["source"] for j in view["ranked"]} == {"linkedin"}
    assert all(j["requirements"]["seniority"] == "intern" for j in view["ranked"])

    assert client.delete(f"/api/saved/{listed['jobs'][0]['id']}").json()["count"] == 1
    assert client.delete("/api/saved").json()["count"] == 0
    r = client.post("/api/runs", data={"cv_text": sample_text("lina_haddad_reliability"), "source": "linkedin"})
    assert r.status_code == 400
