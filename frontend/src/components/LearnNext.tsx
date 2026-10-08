import type { LearnItem } from "../types";

export function LearnNext({ items, total }: { items: LearnItem[]; total: number }) {
  if (!items.length) return null;
  const maxGain = Math.max(...items.map((i) => i.fit_gain), 0.01);
  return (
    <section className="learn" aria-label="Skills to learn next">
      <h2 className="section-title">What to learn next</h2>
      <p className="section-lede">
        Skills that your top {total} jobs ask for and your CV does not show yet. “Unlocks” counts the jobs where that skill is the only
        must-have you are missing.
      </p>
      <div className="table-wrap">
        <table className="learn-table">
          <thead>
            <tr>
              <th scope="col">Skill</th>
              <th scope="col" className="num">
                Jobs asking
              </th>
              <th scope="col" className="num">
                As a must-have
              </th>
              <th scope="col" className="num">
                Unlocks
              </th>
              <th scope="col" className="gain-col">
                Average fit gain
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.skill}>
                <th scope="row">{i.skill}</th>
                <td className="num">{i.jobs_requiring}</td>
                <td className="num">{i.must_count}</td>
                <td className={`num${i.unlocks ? " unlocks" : " muted"}`}>{i.unlocks}</td>
                <td className="gain-col">
                  <span className="gain">
                    <span className="gain-track">
                      <span className="gain-bar" style={{ width: `${Math.max(6, (i.fit_gain / maxGain) * 100)}%` }} />
                    </span>
                    <span className="gain-value">+{Math.round(i.fit_gain * 100)} points</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
