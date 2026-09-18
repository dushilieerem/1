const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_W = 720;
const MAX_H = 480;

/** 压缩评论/正文插图，返回 dataURL */
export function compressImageFile(
  file: File,
  opts?: { maxW?: number; maxH?: number },
): Promise<string> {
  const maxW = opts?.maxW ?? MAX_W;
  const maxH = opts?.maxH ?? MAX_H;
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error("只能插入图片文件"));
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      reject(new Error("单张图片请不超过 5MB"));
      return;
    }
    const objUrl = URL.createObjectURL(file);
    const img = new window.Image();
    img.onload = () => {
      URL.revokeObjectURL(objUrl);
      let { width, height } = img;
      const scale = Math.min(
        1,
        maxW / Math.max(width, 1),
        maxH / Math.max(height, 1),
      );
      width = Math.max(1, Math.round(width * scale));
      height = Math.max(1, Math.round(height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("无法处理图片"));
        return;
      }
      ctx.drawImage(img, 0, 0, width, height);
      const preferPng = file.type === "image/png" || file.type === "image/gif";
      resolve(
        preferPng
          ? canvas.toDataURL("image/png")
          : canvas.toDataURL("image/jpeg", 0.82),
      );
    };
    img.onerror = () => {
      URL.revokeObjectURL(objUrl);
      reject(new Error("读取图片失败"));
    };
    img.src = objUrl;
  });
}
