import { Link } from "react-router-dom";

export function PlaceholderPage({
  title,
  hint,
  cta,
}: {
  title: string;
  hint: string;
  cta?: { to: string; label: string };
}) {
  return (
    <div className="mx-auto max-w-[900px] px-6 py-16 text-center">
      <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
      <p className="mt-3 text-sm leading-relaxed text-slate-500">{hint}</p>
      {cta && (
        <Link
          to={cta.to}
          className="mt-8 inline-flex rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
        >
          {cta.label}
        </Link>
      )}
    </div>
  );
}
