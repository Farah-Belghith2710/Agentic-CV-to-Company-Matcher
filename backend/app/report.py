"""Markdown report of a run (downloadable from the UI)."""
from __future__ import annotations

from datetime import datetime

from .schemas import EvidenceUnit, Job, JobAnalysis, LearnItem, Profile, TailoredBullet

MARK = {"met": "✔ met", "partial": "◐ partial", "missing": "✘ missing"}


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{round(x * 100)}%"


def build_report(
    profile: Profile,
    units: list[EvidenceUnit],
    jobs: dict[str, Job],
    ranked: list[JobAnalysis],
    learn: list[LearnItem],
    tailored: list[TailoredBullet],
    meta: dict,
) -> str:
    unit_by_id = {u.id: u for u in units}
    lines: list[str] = []
    w = lines.append
    w("# CV-to-job match report")
    w("")
    w(f"Generated {datetime.now():%Y-%m-%d %H:%M} · mode: {meta.get('mode', '?')} · similarity: {meta.get('similarity', '?')}")
    w("")
    w("## Profile")
    w(f"- **Headline:** {profile.headline or '—'}")
    w(f"- **Target titles:** {', '.join(profile.target_titles) or '—'}")
    w(f"- **Seniority:** {profile.seniority} (~{profile.years_experience:g} years professional, {profile.internship_months} months of internships)")
    w(f"- **Languages:** {', '.join(f'{l.name} ({l.level}/5)' for l in profile.languages) or '—'}")
    w(f"- **Skills found:** {', '.join(profile.skills[:30]) or '—'}")
    w("")
    w("## Ranked jobs")
    w("")
    w("| # | Job | Company | Fit | Must-haves | Nice-to-haves | Flags |")
    w("|---|-----|---------|-----|------------|---------------|-------|")
    for a in ranked:
        j = jobs[a.job_id]
        title = f"[{j.title}]({j.url})" if j.url else j.title
        flags = "; ".join(f.message for f in a.flags) or "—"
        w(f"| {a.rank} | {title} | {j.company} | {round(a.fit * 100)} | {_pct(a.must_coverage)} | {_pct(a.nice_coverage)} | {flags} |")
    w("")
    for a in ranked:
        j = jobs[a.job_id]
        w(f"### {a.rank}. {j.title} — {j.company}")
        w(f"{j.location or 'Location not stated'} · {j.workplace} · source: {j.attribution or j.source_label}")
        if j.url:
            w(f"Posting: {j.url}")
        w("")
        w("| Requirement | Kind | Verdict | Evidence from your CV |")
        w("|---|---|---|---|")
        reqs = {r.id: r for r in a.requirements.requirements}
        for jd in a.judgments:
            r = reqs.get(jd.req_id)
            if not r:
                continue
            ev = " / ".join(f"{eid}: “{unit_by_id[eid].text[:90]}”" for eid in jd.evidence_ids if eid in unit_by_id) or "—"
            if jd.gap_type == "wording" and jd.cv_term and jd.jd_term:
                ev += f" *(you write “{jd.cv_term}”, they write “{jd.jd_term}”)*"
            w(f"| {r.text} | {r.kind} | {MARK[jd.verdict]} | {ev} |")
        w("")
    if learn:
        w("## Learn next")
        w("")
        w("| Skill | Jobs asking | As must-have | Jobs fully unlocked | Avg. fit gain |")
        w("|---|---|---|---|---|")
        for it in learn:
            w(f"| {it.skill} | {it.jobs_requiring} | {it.must_count} | {it.unlocks} | +{round(it.fit_gain * 100)} pts |")
        w("")
    if tailored:
        w("## Tailored bullets")
        w("")
        for b in tailored:
            j = jobs.get(b.job_id)
            w(f"**For {j.title if j else b.job_id}** ({b.evidence_id}, {b.status.replace('_', ' ')})")
            w("")
            w(f"- Before: {b.original}")
            w(f"- After: {b.final}")
            rejected = [d for d in b.attempts if not d.ok]
            for d in rejected:
                w(f"  - Rejected draft: “{d.text}” — {'; '.join(d.problems)}")
            w("")
    sources = sorted({jobs[a.job_id].attribution or jobs[a.job_id].source_label for a in ranked})
    if sources:
        w("## Sources")
        for s in sources:
            w(f"- {s}")
    return "\n".join(lines) + "\n"
