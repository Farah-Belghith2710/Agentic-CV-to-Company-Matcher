import time
import uuid

from conftest import sample_text
from fastapi.testclient import TestClient
from langgraph.types import Command

from app.graph import GRAPH, RunContext
from app.main import app


def _config():
    return {"configurable": {"thread_id": uuid.uuid4().hex, "ctx": RunContext(llm=None)}}


def test_graph_interrupts_for_selection_then_tailors():
    cfg = _config()
    logs = []
    for mode, chunk in GRAPH.stream(
        {"cv_text": sample_text("lina_haddad_reliability"), "options": {"source": "demo", "location": "Tunis"}},
        cfg,
        stream_mode=["custom", "updates"],
    ):
        if mode == "custom" and chunk.get("type") == "log":
            logs.append(chunk["message"])
    state = GRAPH.get_state(cfg)
    assert state.next == ("pick_jobs",)
    analyses = state.values["analyses"]
    assert len(analyses) == 12 and analyses[0]["fit"] >= analyses[-1]["fit"]
    assert any("Round 1" in m for m in logs), "the query refinement loop should run for this CV"

    picked = [a["job_id"] for a in analyses[:2]]
    for _ in GRAPH.stream(Command(resume=picked), cfg, stream_mode="updates"):
        pass
    final = GRAPH.get_state(cfg).values
    assert final["selected"] == picked
    assert final["tailored"] and all(b["status"] in ("verified", "kept_original") for b in final["tailored"])
    assert final["report_md"].startswith("# CV-to-job match report")


def test_api_end_to_end():
    client = TestClient(app)
    r = client.post("/api/runs", data={"sample_id": "sami", "source": "demo", "location": "Sfax, Tunisie"})
    assert r.status_code == 200, r.text
    rid = r.json()["run_id"]
    view = {}
    for _ in range(100):
        view = client.get(f"/api/runs/{rid}").json()
        if view["status"] in ("awaiting_selection", "error"):
            break
        time.sleep(0.1)
    assert view["status"] == "awaiting_selection", view.get("error")
    assert view["ranked"][0]["job"]["title"] and view["learn_next"]
    job_id = view["ranked"][0]["job_id"]
    assert client.post(f"/api/runs/{rid}/select", json={"job_ids": [job_id]}).status_code == 200
    for _ in range(100):
        view = client.get(f"/api/runs/{rid}").json()
        if view["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert view["status"] == "done"
    report = client.get(f"/api/runs/{rid}/report.md")
    assert report.status_code == 200 and "Tailored bullets" in report.text
    events = client.get(f"/api/runs/{rid}/events").text
    assert '"type": "end"' in events and '"node": "verify"' in events


def test_api_validation_errors():
    client = TestClient(app)
    assert client.post("/api/runs", data={"source": "demo"}).status_code == 400
    assert client.post("/api/runs", data={"sample_id": "lina", "source": "companies"}).status_code == 400
    assert client.post("/api/runs", data={"sample_id": "lina", "source": "nope"}).status_code == 400
    assert client.get("/api/runs/does-not-exist").status_code == 404
