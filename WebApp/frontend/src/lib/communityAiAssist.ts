import type { CommunitySection } from "./communityApi";
import type { PlatformMetricsRef } from "./communityShare";

const IN_KEY = "svquant_ai_assist_in";
const OUT_KEY = "svquant_ai_assist_out";

export type AiAssistInbound = {
  title: string;
  body: string;
  section: CommunitySection;
  code_snippet?: string;
  returnTo: string;
  platform_ref?: PlatformMetricsRef;
};

export type AiAssistOutbound = {
  title: string;
  body: string;
  section: CommunitySection;
  code_snippet?: string;
  aiAssisted: boolean;
};

function readJson<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function stashAiAssistInbound(payload: AiAssistInbound) {
  sessionStorage.setItem(IN_KEY, JSON.stringify(payload));
}

/** 读入助手页；默认保留直到带回或主动清，便于刷新不丢 */
export function peekAiAssistInbound(): AiAssistInbound | null {
  return readJson<AiAssistInbound>(IN_KEY);
}

export function clearAiAssistInbound() {
  sessionStorage.removeItem(IN_KEY);
}

export function stashAiAssistOutbound(payload: AiAssistOutbound) {
  sessionStorage.setItem(OUT_KEY, JSON.stringify(payload));
}

export function takeAiAssistOutbound(): AiAssistOutbound | null {
  const v = readJson<AiAssistOutbound>(OUT_KEY);
  sessionStorage.removeItem(OUT_KEY);
  return v;
}
