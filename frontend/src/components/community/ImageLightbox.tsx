import { useEffect, useState, type WheelEvent } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

const MIN_SCALE = 0.5;
const MAX_SCALE = 4;

/**
 * 点开预览：大图缩进当前视口，小图不强制放大。
 * 滚轮向上放大、向下缩小；遮罩 / Esc / ✕ 关闭。
 */
export function ImageLightbox({
  src,
  onClose,
}: {
  src: string | null;
  onClose: () => void;
}) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    setScale(1);
  }, [src]);

  useEffect(() => {
    if (!src) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [src, onClose]);

  if (!src) return null;

  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const delta = e.deltaY < 0 ? 0.12 : -0.12;
    setScale((s) =>
      Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.round((s + delta) * 100) / 100)),
    );
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center overflow-hidden bg-black/60 p-5"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      onWheel={onWheel}
    >
      <button
        type="button"
        className="absolute right-5 top-5 z-[10000] rounded-full bg-white p-2.5 text-slate-800 shadow-lg hover:bg-slate-100"
        aria-label="关闭"
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
      >
        <X className="h-5 w-5" />
      </button>
      <p className="pointer-events-none absolute bottom-5 left-1/2 z-[10000] -translate-x-1/2 rounded-full bg-black/55 px-3 py-1 text-xs text-white">
        滚轮缩放 · {Math.round(scale * 100)}%
      </p>
      <img
        src={src}
        alt=""
        draggable={false}
        onClick={(e) => e.stopPropagation()}
        style={{
          display: "block",
          maxWidth: "min(72vw, 960px)",
          maxHeight: "min(78vh, 720px)",
          width: "auto",
          height: "auto",
          objectFit: "contain",
          borderRadius: 12,
          boxShadow: "0 20px 50px rgba(0,0,0,0.35)",
          background: "#fff",
          transform: `scale(${scale})`,
          transformOrigin: "center center",
          transition: "transform 60ms linear",
          willChange: "transform",
        }}
      />
    </div>,
    document.body,
  );
}
