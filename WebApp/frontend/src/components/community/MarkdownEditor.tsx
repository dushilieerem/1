import { useEffect, useRef, type ReactNode } from "react";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import Underline from "@tiptap/extension-underline";
import Image from "@tiptap/extension-image";
import CodeBlockLowlight from "@tiptap/extension-code-block-lowlight";
import { common, createLowlight } from "lowlight";
import {
  Bold,
  Code2,
  Heading1,
  Heading2,
  Heading3,
  ImagePlus,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  Quote,
  SquareCode,
  Underline as UnderlineIcon,
} from "lucide-react";

const lowlight = createLowlight(common);
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const EDITOR_IMG_MAX_W = 880;
const EDITOR_IMG_MAX_H = 560;

function plainToHtml(source: string): string {
  const t = source.trim();
  if (!t) return "";
  if (/^\s*</.test(t) && /<\/[a-z][\w-]*>/i.test(t)) return t;
  const esc = t
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return esc
    .split(/\n{2,}/)
    .map((p) => `<p>${p.replace(/\n/g, "<br>")}</p>`)
    .join("");
}

function textLen(html: string): number {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim().length;
}

/** 压缩并限制尺寸，避免正文被大图撑爆 */
function compressImageFile(file: File): Promise<string> {
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
        EDITOR_IMG_MAX_W / Math.max(width, 1),
        EDITOR_IMG_MAX_H / Math.max(height, 1),
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

async function insertImages(editor: Editor, files: File[]) {
  for (const file of files) {
    try {
      const src = await compressImageFile(file);
      editor.chain().focus().setImage({ src }).run();
    } catch (ex) {
      window.alert(ex instanceof Error ? ex.message : String(ex));
    }
  }
}

type BtnProps = {
  active?: boolean;
  title: string;
  onClick: () => void;
  children: ReactNode;
};

function ToolBtn({ active, title, onClick, children }: BtnProps) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`inline-flex h-8 min-w-8 items-center justify-center gap-0.5 rounded-md px-1.5 text-[11px] font-semibold transition ${
        active
          ? "bg-red-50 text-red-600"
          : "text-slate-500 hover:bg-white hover:text-slate-800"
      }`}
    >
      {children}
    </button>
  );
}

/** 所见即所得正文：标题 / 图片粘贴 / 链接 */
export function MarkdownEditor({
  value,
  onChange,
  placeholder = "直接写思路、参数与观察结论即可",
  minHeightClass = "min-h-[min(640px,72vh)]",
  className = "",
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  minHeightClass?: string;
  className?: string;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const editorRef = useRef<Editor | null>(null);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        codeBlock: false,
      }),
      CodeBlockLowlight.configure({
        lowlight,
        defaultLanguage: "python",
      }),
      Underline,
      Image.configure({
        allowBase64: true,
        HTMLAttributes: { class: "community-rte-img" },
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
        linkOnPaste: true,
        HTMLAttributes: { rel: "noopener noreferrer", target: "_blank" },
      }),
      Placeholder.configure({ placeholder }),
    ],
    content: plainToHtml(value),
    editorProps: {
      attributes: {
        class: `community-rte outline-none px-4 py-3.5 text-[15px] leading-7 text-slate-800 ${minHeightClass}`,
      },
      handlePaste: (_view, event) => {
        const ed = editorRef.current;
        const items = event.clipboardData?.items;
        if (!ed || !items) return false;
        const images: File[] = [];
        for (const item of Array.from(items)) {
          if (item.type.startsWith("image/")) {
            const f = item.getAsFile();
            if (f) images.push(f);
          }
        }
        if (images.length === 0) return false;
        event.preventDefault();
        void insertImages(ed, images);
        return true;
      },
      handleDrop: (_view, event) => {
        const ed = editorRef.current;
        const files = event.dataTransfer?.files;
        if (!ed || !files?.length) return false;
        const images = Array.from(files).filter((f) => f.type.startsWith("image/"));
        if (images.length === 0) return false;
        event.preventDefault();
        void insertImages(ed, images);
        return true;
      },
    },
    onCreate: ({ editor: ed }) => {
      editorRef.current = ed;
    },
    onUpdate: ({ editor: ed }) => {
      onChange(ed.isEmpty ? "" : ed.getHTML());
    },
  });

  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  useEffect(() => {
    if (!editor) return;
    if (value === "" && !editor.isEmpty) {
      editor.commands.clearContent(true);
    }
  }, [editor, value]);

  if (!editor) return null;

  const setLink = () => {
    const prev = editor.getAttributes("link").href as string | undefined;
    const selected = editor.state.doc.textBetween(
      editor.state.selection.from,
      editor.state.selection.to,
      " ",
    );
    const url = window.prompt(
      selected
        ? `给「${selected.slice(0, 40)}」添加网站链接`
        : "输入网站链接（留空可取消链接）",
      prev || "https://",
    );
    if (url === null) return;
    const trimmed = url.trim();
    if (!trimmed) {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
      return;
    }
    const href = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
    if (editor.state.selection.empty && !prev) {
      editor
        .chain()
        .focus()
        .insertContent(`<a href="${href}">${href}</a>`)
        .run();
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
  };

  return (
    <div
      className={`flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white focus-within:border-red-300 focus-within:ring-2 focus-within:ring-red-100 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-0.5 border-b border-slate-100 bg-slate-50/80 px-2 py-1.5">
        <ToolBtn
          title="一级标题"
          active={editor.isActive("heading", { level: 1 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        >
          <Heading1 className="h-3.5 w-3.5" />
          <span>H1</span>
        </ToolBtn>
        <ToolBtn
          title="二级标题"
          active={editor.isActive("heading", { level: 2 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        >
          <Heading2 className="h-3.5 w-3.5" />
          <span>H2</span>
        </ToolBtn>
        <ToolBtn
          title="三级标题"
          active={editor.isActive("heading", { level: 3 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        >
          <Heading3 className="h-3.5 w-3.5" />
          <span>H3</span>
        </ToolBtn>
        <span className="mx-1 h-4 w-px bg-slate-200" />
        <ToolBtn
          title="加粗"
          active={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()}
        >
          <Bold className="h-3.5 w-3.5" />
        </ToolBtn>
        <ToolBtn
          title="斜体"
          active={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        >
          <Italic className="h-3.5 w-3.5" />
        </ToolBtn>
        <ToolBtn
          title="下划线"
          active={editor.isActive("underline")}
          onClick={() => editor.chain().focus().toggleUnderline().run()}
        >
          <UnderlineIcon className="h-3.5 w-3.5" />
        </ToolBtn>
        <ToolBtn
          title="无序列表"
          active={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        >
          <List className="h-3.5 w-3.5" />
        </ToolBtn>
        <ToolBtn
          title="有序列表"
          active={editor.isActive("orderedList")}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        >
          <ListOrdered className="h-3.5 w-3.5" />
        </ToolBtn>
        <ToolBtn
          title="引用"
          active={editor.isActive("blockquote")}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
        >
          <Quote className="h-3.5 w-3.5" />
        </ToolBtn>
        <ToolBtn
          title="行内代码"
          active={editor.isActive("code")}
          onClick={() => editor.chain().focus().toggleCode().run()}
        >
          <Code2 className="h-3.5 w-3.5" />
        </ToolBtn>
        <ToolBtn
          title="代码块（Python 高亮）"
          active={editor.isActive("codeBlock")}
          onClick={() =>
            editor.chain().focus().toggleCodeBlock({ language: "python" }).run()
          }
        >
          <SquareCode className="h-3.5 w-3.5" />
        </ToolBtn>
        <span className="mx-1 h-4 w-px bg-slate-200" />
        <ToolBtn title="网站链接" active={editor.isActive("link")} onClick={setLink}>
          <LinkIcon className="h-3.5 w-3.5" />
        </ToolBtn>
        <ToolBtn
          title="插入图片（自动缩小；也可粘贴）"
          onClick={() => fileRef.current?.click()}
        >
          <ImagePlus className="h-3.5 w-3.5" />
        </ToolBtn>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void insertImages(editor, [file]);
          }}
        />
        <span className="ml-auto pr-1 text-[11px] text-slate-400">
          {textLen(value || editor.getHTML())} 字 · 图片自动缩小
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}
