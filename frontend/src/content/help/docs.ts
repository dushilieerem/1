import type { HelpDocId } from "./catalog";
import factorWriting from "../../../../docs/用户指南/因子与策略指南/01-factor-writing.md?raw";
import vectorizedStrategy from "../../../../docs/用户指南/因子与策略指南/02-vectorized-strategy-writing.md?raw";
import eventStrategy from "../../../../docs/用户指南/因子与策略指南/03-event-strategy-writing.md?raw";
import examplesFaq from "../../../../docs/用户指南/因子与策略指南/04-examples-and-faq.md?raw";
import paperTrading from "../../../../docs/用户指南/因子与策略指南/05-paper-trading.md?raw";

const BODY: Record<HelpDocId, string> = {
  "factor-writing": factorWriting,
  "vectorized-strategy": vectorizedStrategy,
  "event-strategy": eventStrategy,
  "examples-faq": examplesFaq,
  "paper-trading": paperTrading,
};

/** 去掉指向仓外相对路径的链接，避免帮助页 404 */
function polishHelpMarkdown(md: string): string {
  return md
    .replace(/\[([^\]]+)\]\(\.\.\/[^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\(\.\/[^)]+\.md\)/g, "$1");
}

export function loadHelpMarkdown(id: HelpDocId): string {
  return polishHelpMarkdown(BODY[id] || "");
}


