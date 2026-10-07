export type Verdict = "met" | "partial" | "missing";
export type RunStatus = "queued" | "running" | "awaiting_selection" | "done" | "error";
export type Source = "demo" | "companies" | "keywords" | "paste";

export interface Health {
  ok: boolean;
  llm: { configured: boolean; model: string | null; host: string | null };
  similarity: string;
  snapshot: { file: string; jobs: number };
}

export interface Sample {
  id: string;
  name: string;
  headline: string;
  language: string;
}

export interface EvidenceUnit {
  id: string;
  section: string;
  text: string;
  context: string;
  kind: string;
}

export interface Profile {
  headline: string;
  target_titles: string[];
  skills: string[];
  domains: string[];
  years_experience: number;
  internship_months: number;
  seniority: string;
  languages: { name: string; level: number }[];
  education: string[];
  location: string;
  cv_language: string;
  source: string;
}

export interface Requirement {
  id: string;
  text: string;
  kind: "must" | "nice";
  category: string;
  skills: string[];
  min_years: number | null;
  languages: string[];
}

export interface Judgment {
  req_id: string;
  verdict: Verdict;
  evidence_ids: string[];
  note: string;
  gap_type: "none" | "wording" | "skill";
  cv_term: string | null;
  jd_term: string | null;
  missing_skills: string[];
}

export interface JobInfo {
  id: string;
  title: string;
  company: string;
  location: string;
  workplace: string;
  url: string;
  source: string;
  source_label: string;
  attribution: string | null;
  posted_at: string | null;
}

export interface RankedJob {
  job_id: string;
  rank: number;
  fit: number;
  must_coverage: number | null;
  nice_coverage: number | null;
  flags: { kind: string; message: string }[];
  retrieval_score: number;
  downgraded: number;
  requirements: {
    requirements: Requirement[];
    seniority: string;
    min_years: number | null;
    languages: string[];
    workplace: string;
    posting_language: string;
    source: string;
  };
  judgments: Judgment[];
  job: JobInfo;
  description: string;
  bm25: number | null;
  semantic: number | null;
  triage_reason: string;
}

export interface LearnItem {
  skill: string;
  jobs_requiring: number;
  must_count: number;
  unlocks: number;
  fit_gain: number;
  job_ids: string[];
}

export interface Draft {
  text: string;
  ok: boolean;
  problems: string[];
  note: string;
}

export interface TailoredBullet {
  job_id: string;
  evidence_id: string;
  original: string;
  context: string;
  final: string;
  status: "pending" | "verified" | "kept_original";
  attempts: Draft[];
  targets: string[];
  alignments: { cv_term: string; jd_term: string; skill: string }[];
}

export interface RunView {
  id: string;
  status: RunStatus;
  error: string | null;
  created: number;
  cv_label: string;
  options: { source: Source; companies?: string; keywords?: string; location?: string; remote_ok?: boolean };
  mode: { llm: boolean; model: string | null };
  redaction: Record<string, number>;
  profile: Profile | null;
  units: EvidenceUnit[];
  queries: string[];
  query_log: { round: number; queries: string[]; rationale: string }[];
  pool_size: number;
  relevant_count: number;
  similarity: string | null;
  ranked: RankedJob[];
  learn_next: LearnItem[];
  selected: string[];
  tailored: TailoredBullet[];
  has_report: boolean;
  warnings: string[];
  llm_stats: { calls: number; cache_hits: number; failures: number; by_task: Record<string, number> } | null;
  nodes: string[];
  event_count: number;
}

export interface RunEvent {
  seq: number;
  ts: number;
  type: "log" | "stage" | "status" | "end";
  node?: string;
  level?: "info" | "warn" | "error" | "success";
  message?: string;
  status?: string;
  ms?: number;
  data?: Record<string, unknown>;
}
