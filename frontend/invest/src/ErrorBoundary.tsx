import React, { type ErrorInfo, type ReactNode } from "react";

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
      return (
        <div className="state-box" style={{ margin: 24 }}>
          <b>页面出错了</b>
          <p>{this.state.error.message || "未知错误"}</p>
          <button className="btn btn-ghost" onClick={() => location.reload()}>重新加载</button>
        </div>
      );
    }
    return this.props.children;
  }
}
