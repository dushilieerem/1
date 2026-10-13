import { contentLength, lengthError } from "@/lib/communityLimits";

export function ContentLengthHint({ value, limit, label, id }: {
  value: string; limit: number; label: string; id?: string;
}) {
  const error = lengthError(value, limit, label);
  return <p id={id} aria-live="polite" className={`mt-2 text-xs ${error ? "text-red-600" : "text-slate-500"}`}>
    {label} {contentLength(value)} / {limit} 字符（不计首尾空白）{error ? `；${error}` : ""}
  </p>;
}
