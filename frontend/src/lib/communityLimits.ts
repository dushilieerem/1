export const POST_BODY_LIMIT = 20_000;
export const COMMENT_LIMIT = 2_000;
export const REPORT_DETAIL_LIMIT = 500;

// Count Unicode code points, matching Python len(), after submission trimming.
export const contentLength = (value: string) => Array.from(value.trim()).length;

export function lengthError(value: string, limit: number, label: string): string | null {
  const extra = contentLength(value) - limit;
  return extra > 0 ? `${label}最多 ${limit} 字符，已超出 ${extra} 字符，请缩短后再提交。` : null;
}
