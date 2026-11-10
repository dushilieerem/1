type FourLineProps = {
  judgment?: string | null;
  basis?: string | null;
  impact?: string | null;
  action?: string | null;
  className?: string;
};

const ROWS: Array<["judgment" | "basis" | "impact" | "action", string]> = [
  ["judgment", "判断"],
  ["basis", "依据"],
  ["impact", "影响"],
  ["action", "动作"],
];

export function InstV3FourLine({
  judgment,
  basis,
  impact,
  action,
  className = "",
}: FourLineProps) {
  const values = { judgment, basis, impact, action };
  return (
    <div className={`v3-four-line ${className}`.trim()}>
      {ROWS.map(([key, label]) => (
        <div className={`v3-four-row v3-four-${key}`} key={key}>
          <span className="v3-four-label">{label}</span>
          <span className="v3-four-text">{values[key] || "—"}</span>
        </div>
      ))}
    </div>
  );
}
