import type { LearnItem } from "../types";

export function LearnNext({ items, total }: { items: LearnItem[]; total: number }) {
  if (!items.length) return null;
  const maxGain = Math.max(...items.map((i) => i.fit_gain), 0.01);
  return (
    <section className="learn" aria-label="Skills to learn next">
      <h2 className="panel-title">Learn next</h2>
      <p className="muted">
        Skills your top {total} jobs ask for that your CV does not show yet. A job is unlocked when the skill is its only missing
        must-have.
      </p>
      <table className="learn-table">
        <thead>
          <tr>
            <th scope="col">Skill</th>
            <th scope="col" className="num">
              Jobs asking
            </th>
            <th scope="col" className="num">
              As must-have
            </th>
            <th scope="col" className="num">
              Unlocks
            </th>
            <th scope="col">Average fit gain</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.skill}>
              <th scope="row">{i.skill}</th>
              <td className="num">{i.jobs_requiring}</td>
              <td className="num">{i.must_count}</td>
              <td className={`num${i.unlocks ? " strong" : ""}`}>{i.unlocks}</td>
              <td>
                <span className="gain">
                  <span className="gain-bar" style={{ width: `${Math.max(4, (i.fit_gain / maxGain) * 100)}%` }} />
                  <span className="gain-value">+{Math.round(i.fit_gain * 100)} pts</span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
