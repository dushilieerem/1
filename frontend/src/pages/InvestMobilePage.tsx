import { getToken } from "@/lib/auth";

/**
 * 手机 H5 嵌入主站：同域 iframe + 主站令牌换会话。
 * 保留移动端独立构建（避免桌面 CSS 冲突），但入口、域名、账号与后端已合并。
 */
export default function InvestMobilePage() {
  const token = getToken();
  const src = `/mobile/${token ? `#svq_token=${encodeURIComponent(token)}` : ""}`;
  return (
    <div className="mx-auto max-w-[460px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2 text-xs text-slate-500">
        <span>SVQuant 手机版</span>
        <a href="/mobile/" target="_blank" rel="noreferrer" className="text-red-600 hover:underline">
          新窗口打开
        </a>
      </div>
      <iframe
        title="SVQuant 手机版"
        src={src}
        className="h-[calc(100vh-10rem)] min-h-[640px] w-full border-0"
      />
    </div>
  );
}
