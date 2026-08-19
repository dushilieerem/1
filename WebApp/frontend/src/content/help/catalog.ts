/** 帮助中心目录（对应 docs/help/07-factor-strategy-guide） */
export type HelpDocId =
  | "factor-writing"
  | "vectorized-strategy"
  | "event-strategy"
  | "examples-faq"
  | "frontend-factor-library";

export type HelpDocMeta = {
  id: HelpDocId;
  title: string;
  /** 侧栏分组标题 */
  group: string;
  file: string;
};

export const HELP_DOCS: HelpDocMeta[] = [
  {
    id: "factor-writing",
    title: "因子编写规范",
    group: "因子与策略编写",
    file: "01-factor-writing.md",
  },
  {
    id: "vectorized-strategy",
    title: "向量化策略编写",
    group: "因子与策略编写",
    file: "02-vectorized-strategy-writing.md",
  },
  {
    id: "event-strategy",
    title: "事件策略编写",
    group: "因子与策略编写",
    file: "03-event-strategy-writing.md",
  },
  {
    id: "examples-faq",
    title: "示例与常见问题",
    group: "因子与策略编写",
    file: "04-examples-and-faq.md",
  },
  {
    id: "frontend-factor-library",
    title: "前端因子库映射",
    group: "平台与开发",
    file: "05-frontend-factor-library.md",
  },
];

export const DEFAULT_HELP_DOC: HelpDocId = "factor-writing";

export function getHelpDoc(id: string | undefined): HelpDocMeta {
  return HELP_DOCS.find((d) => d.id === id) ?? HELP_DOCS[0];
}

/** 从 Markdown 抽 ## / ### 作页内目录 */
export function extractHelpHeadings(md: string): { id: string; text: string; level: 2 | 3 }[] {
  const out: { id: string; text: string; level: 2 | 3 }[] = [];
  for (const line of md.split("\n")) {
    const m = /^(#{2,3})\s+(.+?)\s*$/.exec(line);
    if (!m) continue;
    const level = m[1].length as 2 | 3;
    const text = m[2].replace(/#+$/, "").trim();
    if (!text) continue;
    out.push({ id: slugifyHeading(text), text, level });
  }
  return out;
}

export function slugifyHeading(text: string): string {
  return text
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^\w\u4e00-\u9fff\-]/g, "")
    .toLowerCase();
}
