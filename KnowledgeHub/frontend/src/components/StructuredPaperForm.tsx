import { useMemo, useRef, useState } from "react";
import { FileText, FileType2, Trash2, Upload, X } from "lucide-react";

export type StructuredPayload = {
  document: {
    title: string;
    authors: string[];
    organization: string[];
    publish_date: string;
    url: string;
    doc_type: string;
    language: string;
    tags: string[];
  };
  research_note: {
    summary: string;
    background: string;
    motivation: string;
    what_it_does: string;
    key_idea: string[];
    ml_tech: string[];
    qf_tech: string[];
    data: string[];
    result: string;
    limitation: string;
    conclusion: string;
  };
  schema_version: string;
};

const DOC_TYPES = ["paper", "blog", "report", "code", "news", "others"] as const;
const LANGS = ["zh", "en", "other"] as const;

/** 中英对照标签 */
const LABEL_EN: Record<string, string> = {
  domain: "Domain",
  chunk_strategy: "Chunking Method",
  title: "Title",
  authors: "Authors",
  organization: "Organization",
  publish_date: "Publish Date",
  url: "URL",
  doc_type: "Doc Type",
  language: "Language",
  tags: "Tags",
  summary: "Summary",
  background: "Background",
  motivation: "Motivation",
  what_it_does: "What It Does",
  key_idea: "Key Ideas",
  ml_tech: "ML Tech",
  qf_tech: "Quant Finance Tech",
  data: "Data",
  result: "Result",
  limitation: "Limitation",
  conclusion: "Conclusion",
  attachment: "Attachment",
};

function emptyPayload(): StructuredPayload {
  return {
    document: {
      title: "",
      authors: [""],
      organization: [""],
      publish_date: "",
      url: "",
      doc_type: "paper",
      language: "zh",
      tags: [""],
    },
    research_note: {
      summary: "",
      background: "",
      motivation: "",
      what_it_does: "",
      key_idea: [""],
      ml_tech: [""],
      qf_tech: [""],
      data: [""],
      result: "",
      limitation: "",
      conclusion: "",
    },
    schema_version: "1.0",
  };
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function FileIcon({ name }: { name: string }) {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  const isPdf = ext === "pdf";
  return (
    <div
      className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${
        isPdf ? "bg-rose-50 text-rose-600" : "bg-sky-50 text-sky-700"
      }`}
    >
      {isPdf ? <FileType2 className="h-6 w-6" /> : <FileText className="h-6 w-6" />}
    </div>
  );
}

function FieldLabel({ zh, enKey }: { zh: string; enKey: string }) {
  const en = LABEL_EN[enKey] || enKey;
  return (
    <span className="text-sm font-medium text-slate-700">
      {zh} <span className="font-normal text-slate-400">({en})</span>
    </span>
  );
}

function ListField({
  zh,
  enKey,
  items,
  onChange,
  placeholder,
}: {
  zh: string;
  enKey: string;
  items: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const rows = items.length ? items : [""];
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <FieldLabel zh={zh} enKey={enKey} />
        <button
          type="button"
          className="shrink-0 text-xs font-medium text-[var(--kh-teal-deep)] hover:underline"
          onClick={() => onChange([...rows, ""])}
        >
          + 添加
        </button>
      </div>
      {rows.map((v, i) => (
        <div key={i} className="flex gap-2">
          <input
            className="min-h-12 flex-1 rounded-xl border border-slate-200 px-3.5 py-3 text-sm"
            value={v}
            placeholder={placeholder}
            onChange={(e) => {
              const next = [...rows];
              next[i] = e.target.value;
              onChange(next);
            }}
          />
          {rows.length > 1 ? (
            <button
              type="button"
              className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
              onClick={() => {
                const next = rows.filter((_, j) => j !== i);
                onChange(next.length ? next : [""]);
              }}
              aria-label="删除"
              title="删除"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      ))}
    </div>
  );
}

type ChunkStrategyOpt = { id: string; labelZh: string };

type Props = {
  domain: string;
  onDomainChange: (v: string) => void;
  chunkStrategy: string;
  onChunkStrategyChange: (v: string) => void;
  strategies: ChunkStrategyOpt[];
  payload: StructuredPayload;
  onPayloadChange: (p: StructuredPayload) => void;
  attachment: File | null;
  onAttachmentChange: (f: File | null) => void;
};

export function StructuredPaperForm({
  domain,
  onDomainChange,
  chunkStrategy,
  onChunkStrategyChange,
  strategies,
  payload,
  onPayloadChange,
  attachment,
  onAttachmentChange,
}: Props) {
  const doc = payload.document;
  const note = payload.research_note;
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const setDoc = (patch: Partial<StructuredPayload["document"]>) => {
    onPayloadChange({ ...payload, document: { ...doc, ...patch } });
  };
  const setNote = (patch: Partial<StructuredPayload["research_note"]>) => {
    onPayloadChange({ ...payload, research_note: { ...note, ...patch } });
  };

  return (
    <div className="max-h-[70vh] space-y-5 overflow-y-auto pr-1">
      {/* —— Document 元数据 —— */}
      <section className="space-y-5">
        <div>
          <div className="mb-1.5">
            <FieldLabel zh="领域" enKey="domain" />
          </div>
          <select
            className="min-h-12 w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm"
            value={domain}
            onChange={(e) => onDomainChange(e.target.value)}
          >
            <option value="paper">论文 (Paper)</option>
          </select>
        </div>

        <div>
          <div className="mb-1.5">
            <FieldLabel zh="分块方法" enKey="chunk_strategy" />
          </div>
          <select
            className="min-h-12 w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm"
            value={chunkStrategy}
            onChange={(e) => onChunkStrategyChange(e.target.value)}
          >
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.labelZh}
              </option>
            ))}
          </select>
        </div>

        <div className="relative py-2">
          <div className="absolute inset-x-0 top-1/2 border-t border-slate-200" />
          <div className="relative mx-auto flex w-fit items-center gap-2 bg-white px-3">
            <span className="text-sm font-semibold text-slate-800">文献元数据</span>
            <span className="text-xs text-slate-400">(Document)</span>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <div className="mb-1.5">
              <FieldLabel zh="标题 *" enKey="title" />
            </div>
            <input
              className="min-h-12 w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm"
              value={doc.title}
              onChange={(e) => setDoc({ title: e.target.value })}
            />
          </div>
          <div>
            <div className="mb-1.5">
              <FieldLabel zh="文档类型" enKey="doc_type" />
            </div>
            <select
              className="min-h-12 w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm"
              value={doc.doc_type}
              onChange={(e) => setDoc({ doc_type: e.target.value })}
            >
              {DOC_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="mb-1.5">
              <FieldLabel zh="语言" enKey="language" />
            </div>
            <select
              className="min-h-12 w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm"
              value={doc.language}
              onChange={(e) => setDoc({ language: e.target.value })}
            >
              {LANGS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>

        <ListField
          zh="作者"
          enKey="authors"
          items={doc.authors}
          onChange={(authors) => setDoc({ authors })}
          placeholder="作者姓名"
        />
        <ListField
          zh="机构"
          enKey="organization"
          items={doc.organization}
          onChange={(organization) => setDoc({ organization })}
          placeholder="机构名称"
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-1.5">
              <FieldLabel zh="发表日期" enKey="publish_date" />
            </div>
            <input
              className="min-h-12 w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm"
              value={doc.publish_date}
              onChange={(e) => setDoc({ publish_date: e.target.value })}
            />
          </div>
          <div>
            <div className="mb-1.5">
              <FieldLabel zh="链接" enKey="url" />
            </div>
            <input
              className="min-h-12 w-full rounded-xl border border-slate-200 px-3.5 py-3 text-sm"
              value={doc.url}
              onChange={(e) => setDoc({ url: e.target.value })}
            />
          </div>
        </div>

        <ListField
          zh="标签"
          enKey="tags"
          items={doc.tags}
          onChange={(tags) => setDoc({ tags })}
          placeholder="关键词"
        />
      </section>

      {/* —— ResearchNote 分界 —— */}
      <div className="relative py-2">
        <div className="absolute inset-x-0 top-1/2 border-t border-slate-200" />
        <div className="relative mx-auto flex w-fit items-center gap-2 bg-white px-3">
          <span className="text-sm font-semibold text-slate-800">读后笔记</span>
          <span className="text-xs text-slate-400">(Research Note)</span>
        </div>
      </div>

      <section className="space-y-5">
        {(
          [
            ["summary", "摘要", note.summary, (v: string) => setNote({ summary: v }), 6],
            ["background", "背景", note.background, (v: string) => setNote({ background: v }), 5],
            ["motivation", "动机", note.motivation, (v: string) => setNote({ motivation: v }), 5],
            [
              "what_it_does",
              "方法概述",
              note.what_it_does,
              (v: string) => setNote({ what_it_does: v }),
              5,
            ],
            ["result", "结果", note.result, (v: string) => setNote({ result: v }), 5],
            ["limitation", "局限", note.limitation, (v: string) => setNote({ limitation: v }), 5],
            ["conclusion", "结论", note.conclusion, (v: string) => setNote({ conclusion: v }), 5],
          ] as const
        ).map(([key, zh, val, setVal, rows]) => (
          <div key={key}>
            <div className="mb-1.5">
              <FieldLabel zh={zh} enKey={key} />
            </div>
            <textarea
              className="w-full resize-y rounded-xl border border-slate-200 px-3.5 py-3.5 text-sm leading-relaxed"
              rows={rows}
              value={val}
              onChange={(e) => setVal(e.target.value)}
            />
          </div>
        ))}

        <ListField
          zh="核心思想"
          enKey="key_idea"
          items={note.key_idea}
          onChange={(key_idea) => setNote({ key_idea })}
        />
        <ListField
          zh="机器学习技术"
          enKey="ml_tech"
          items={note.ml_tech}
          onChange={(ml_tech) => setNote({ ml_tech })}
        />
        <ListField
          zh="量化金融模型"
          enKey="qf_tech"
          items={note.qf_tech}
          onChange={(qf_tech) => setNote({ qf_tech })}
        />
        <ListField
          zh="数据"
          enKey="data"
          items={note.data}
          onChange={(data) => setNote({ data })}
        />
      </section>

      <div className="relative py-2">
        <div className="absolute inset-x-0 top-1/2 border-t border-slate-200" />
        <div className="relative mx-auto flex w-fit items-center gap-2 bg-white px-3">
          <span className="text-sm font-semibold text-slate-800">原文附件</span>
          <span className="text-xs text-slate-400">(Attachment)</span>
        </div>
      </div>

      <div>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx"
          className="hidden"
          onChange={(e) => {
            onAttachmentChange(e.target.files?.[0] || null);
            e.target.value = "";
          }}
        />
        {attachment ? (
          <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
            <FileIcon name={attachment.name} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-slate-800">{attachment.name}</p>
              <p className="text-xs text-slate-500">{formatBytes(attachment.size)}</p>
            </div>
            <button
              type="button"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-white hover:text-rose-600"
              onClick={() => onAttachmentChange(null)}
              aria-label="移除附件"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const f = e.dataTransfer.files?.[0];
              if (f) onAttachmentChange(f);
            }}
            className={`flex w-full flex-col items-center gap-3 rounded-xl border border-dashed px-4 py-14 text-sm transition ${
              dragOver
                ? "border-sky-400 bg-sky-50 text-sky-700"
                : "border-slate-300 bg-slate-50 text-slate-500 hover:border-sky-400 hover:text-sky-700"
            }`}
          >
            <Upload className="h-12 w-12" />
            <span className="text-base font-medium">点击或拖拽上传原文</span>
          </button>
        )}
      </div>
    </div>
  );
}

export function useStructuredFormState() {
  const [domain, setDomain] = useState("paper");
  const [payload, setPayload] = useState<StructuredPayload>(() => emptyPayload());
  const [attachment, setAttachment] = useState<File | null>(null);
  const reset = () => {
    setDomain("paper");
    setPayload(emptyPayload());
    setAttachment(null);
  };
  return useMemo(
    () => ({
      domain,
      setDomain,
      payload,
      setPayload,
      attachment,
      setAttachment,
      reset,
    }),
    [domain, payload, attachment],
  );
}

export function sanitizePayload(p: StructuredPayload): StructuredPayload {
  const trimList = (xs: string[]) =>
    xs.map((x) => x.trim()).filter(Boolean);
  return {
    schema_version: p.schema_version || "1.0",
    document: {
      ...p.document,
      title: p.document.title.trim(),
      authors: trimList(p.document.authors),
      organization: trimList(p.document.organization),
      publish_date: p.document.publish_date.trim() || "",
      url: p.document.url.trim() || "",
      tags: trimList(p.document.tags),
    },
    research_note: {
      summary: p.research_note.summary.trim() || "",
      background: p.research_note.background.trim() || "",
      motivation: p.research_note.motivation.trim() || "",
      what_it_does: p.research_note.what_it_does.trim() || "",
      key_idea: trimList(p.research_note.key_idea),
      ml_tech: trimList(p.research_note.ml_tech),
      qf_tech: trimList(p.research_note.qf_tech),
      data: trimList(p.research_note.data),
      result: p.research_note.result.trim() || "",
      limitation: p.research_note.limitation.trim() || "",
      conclusion: p.research_note.conclusion.trim() || "",
    },
  };
}
