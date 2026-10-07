"""The LLM code path, exercised with a fake provider (no network, no API key).

Checks: JSON repair retry, canonicalization of LLM skills, the evidence guard (verdicts citing
no valid CV line are downgraded), and the rewrite -> verify loop rejecting invented numbers.
"""
import dataclasses
import json
import re
import uuid

from conftest import sample_text
from langgraph.types import Command

from app.config import settings
from app.graph import GRAPH, RunContext
from app.llm import LLMClient, extract_json


class FakeProvider:
    def __init__(self):
        self.calls: list[str] = []
        self.rewrites: dict[str, int] = {}
        self.plan_attempts = 0

    def __call__(self, model, messages, temperature):
        system, user = messages[0]["content"], messages[1]["content"]
        if "structured profile" in system:
            self.calls.append("profile")
            return json.dumps({
                "headline": "Reliability engineering student", "target_titles": ["Reliability Engineer", "Maintenance Engineer"],
                "skills": ["sklearn", "AMDEC", "Weibull"], "domains": ["Reliability engineering"], "years_experience": 0,
                "seniority": "student", "languages": [{"name": "French", "level": "fluent"}], "location": "Tunis",
            })
        if "plan job searches" in system:
            self.calls.append("plan")
            self.plan_attempts += 1
            if self.plan_attempts == 1:
                return "Sure! Here are some queries: reliability engineer"  # not JSON -> repair retry
            return json.dumps({"queries": ["reliability engineer", "maintenance engineer"], "rationale": "test"})
        if "improve a job search" in system:
            self.calls.append("refine")
            return json.dumps({"queries": ["condition monitoring engineer", "ingénieur maintenance"], "rationale": "broaden"})
        if "extract hiring requirements" in system:
            self.calls.append("requirements")
            return json.dumps({
                "requirements": [
                    {"text": "Hands-on FMEA practice", "kind": "must", "category": "skill", "skills": ["FMEA"]},
                    {"text": "Python for data analysis", "kind": "must", "category": "skill", "skills": ["Python"]},
                    {"text": "Kubernetes", "kind": "nice", "category": "skill", "skills": ["k8s"]},
                ],
                "seniority": "junior", "min_years": None, "languages": [], "workplace": "onsite",
            })
        if "strict technical recruiter" in system:
            self.calls.append("judge")
            return json.dumps({"judgments": [
                {"req_id": "R1", "verdict": "met", "evidence_ids": ["E3"], "note": "AMDEC", "cv_term": "AMDEC", "jd_term": "FMEA"},
                {"req_id": "R2", "verdict": "met", "evidence_ids": ["E999"], "note": "made-up evidence id"},
                {"req_id": "R3", "verdict": "missing", "evidence_ids": [], "note": ""},
            ]})
        if "tailor ONE CV bullet" in system:
            self.calls.append("rewrite")
            original = user.split("Original bullet:\n", 1)[1].split("\nYour previous draft", 1)[0].strip()
            n = self.rewrites[original] = self.rewrites.get(original, 0) + 1
            if n == 1:
                return json.dumps({"rewritten": original.rstrip(".") + ", cutting downtime by 37%.", "changes": ["added impact"]})
            return json.dumps({"rewritten": original, "changes": ["kept facts"]})
        if "verify a rewritten CV bullet" in system:
            self.calls.append("verify")
            return json.dumps({"supported": True, "unsupported_claims": []})
        raise AssertionError("unexpected prompt: " + system[:80])


def test_extract_json_is_lenient():
    assert extract_json('```json\n{"a": 1,}\n```') == {"a": 1}
    assert extract_json("<think>hmm</think> {\"b\": 2}") == {"b": 2}


def test_full_run_with_fake_llm():
    cfg = dataclasses.replace(settings, llm_model="fake-model", llm_api_key="test", force_offline=False, llm_concurrency=1)
    llm = LLMClient(cfg)
    fake = FakeProvider()
    llm._create = fake  # type: ignore[assignment]
    config = {"configurable": {"thread_id": uuid.uuid4().hex, "ctx": RunContext(llm=llm)}}
    for _ in GRAPH.stream(
        {"cv_text": sample_text("lina_haddad_reliability"), "options": {"source": "demo", "location": "Tunis"}},
        config,
        stream_mode="updates",
    ):
        pass
    state = GRAPH.get_state(config).values
    assert fake.plan_attempts == 2, "invalid JSON should trigger one repair retry"
    assert "scikit-learn" in state["profile"]["skills"] and "FMEA" in state["profile"]["skills"]
    first = state["analyses"][0]
    verdicts = {j["req_id"]: j for j in first["judgments"]}
    assert verdicts["R1"]["verdict"] == "met" and verdicts["R1"]["cv_term"] == "AMDEC"
    assert verdicts["R2"]["verdict"] == "missing" and "downgraded" in verdicts["R2"]["note"]
    assert first["downgraded"] == 1
    reqs = {r["id"]: r for r in first["requirements"]["requirements"]}
    assert reqs["R3"]["skills"] == ["Kubernetes"]  # "k8s" canonicalized

    for _ in GRAPH.stream(Command(resume=[first["job_id"]]), config, stream_mode="updates"):
        pass
    tailored = GRAPH.get_state(config).values["tailored"]
    assert tailored
    for b in tailored:
        assert b["status"] == "verified"
        assert len(b["attempts"]) == 2 and not b["attempts"][0]["ok"]
        assert "37" in " ".join(b["attempts"][0]["problems"])
        assert "37%" not in b["final"]
    assert "verify" in fake.calls
