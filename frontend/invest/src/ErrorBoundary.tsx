import React, { type ErrorInfo, type ReactNode } from "react";
import { LocaleProvider, useLocale } from "./i18n";

function CrashNotice({ error }: { error: Error }) {
  const { t } = useLocale();
  return (
    <div className="state-box" style={{ margin: 24 }}>
      <b>{t("页面出错了", "Something went wrong")}</b>
      <p>{error.message || t("未知错误", "Unknown error")}</p>
      <button className="btn btn-ghost" onClick={() => location.reload()}>{t("重新加载", "Reload")}</button>
    </div>
  );
}

export default class ErrorBoundary extends React.Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Invest H5 crashed", error, info);
  }

  render() {
    if (this.state.error) {
      // ErrorBoundary 在 LocaleProvider 外层，崩溃时原 Provider 已卸载，
      // 这里补一个 Provider 以便 useLocale 读到本地保存的语言设置。
      return (
        <LocaleProvider>
          <CrashNotice error={this.state.error} />
        </LocaleProvider>
      );
    }
    return this.props.children;
  }
}
