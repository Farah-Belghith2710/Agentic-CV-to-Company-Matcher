import type { Verdict } from "../types";

const VERDICT_LABEL: Record<Verdict, string> = { met: "Met", partial: "Partly met", missing: "Missing" };

/** Harvey ball: full = met, half = partly met, empty = missing (shape carries meaning, not just color). */
export function HarveyBall({ verdict, size = 16 }: { verdict: Verdict; size?: number }) {
  const r = size / 2 - 1.5;
  const c = size / 2;
  return (
    <svg className={`harvey harvey-${verdict}`} width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={VERDICT_LABEL[verdict]}>
      <title>{VERDICT_LABEL[verdict]}</title>
      <circle cx={c} cy={c} r={r} className="harvey-ring" />
      {verdict === "met" && <circle cx={c} cy={c} r={r - 2.2} className="harvey-fill" />}
      {verdict === "partial" && <path d={`M ${c} ${c - r + 2.2} A ${r - 2.2} ${r - 2.2} 0 0 0 ${c} ${c + r - 2.2} Z`} className="harvey-fill" />}
    </svg>
  );
}

/** Evidence balloon, like a callout on an engineering drawing: points to one line of the CV. */
export function Balloon({
  id,
  title,
  active,
  onFocus,
  onBlur,
}: {
  id: string;
  title: string;
  active?: boolean;
  onFocus?: () => void;
  onBlur?: () => void;
}) {
  return (
    <button
      type="button"
      className={`balloon${active ? " is-active" : ""}`}
      title={title}
      aria-label={`Evidence ${id}: ${title}`}
      onMouseEnter={onFocus}
      onMouseLeave={onBlur}
      onFocus={onFocus}
      onBlur={onBlur}
    >
      {id.replace(/^E/, "")}
    </button>
  );
}

export function pct(x: number | null | undefined): string {
  return x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`;
}

export function CoverageBar({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="coverage" aria-label={`${label}: ${pct(value)}`}>
      <span className="coverage-label">{label}</span>
      <span className="coverage-track">
        <span className="coverage-fill" style={{ width: value === null ? 0 : `${Math.round(value * 100)}%` }} />
      </span>
      <span className="coverage-value">{pct(value)}</span>
    </div>
  );
}
