import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bot,
  Cloud,
  Cpu,
  KeyRound,
  Layers,
  MessageSquare,
  Mic,
  Plus,
  Search,
  Sparkles,
  Trash2,
  Volume2,
  Wand2,
  Image as ImageIcon,
} from "lucide-react";
import {
  deleteProvider,
  getDefaultModels,
  listProviders,
  setDefaultModels,
  upsertProvider,
  type ModelProvider,
} from "@/lib/api";
import { ConfirmModal } from "@/components/Modals";

type CatalogItem = {
  key: string;
  name: string;
  hint: string;
  tags: string[];
  defaultBaseUrl: string;
  accent: string;
  icon: typeof Bot;
};

const CATALOG: CatalogItem[] = [
  {
    key: "openai-compatible",
    name: "OpenAI 兼容",
    hint: "百炼 / DeepSeek / Xinference 等",
    tags: ["LLM", "TEXT EMBEDDING", "TEXT RE-RANK"],
    defaultBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    accent: "bg-emerald-500",
    icon: Cloud,
  },
  {
    key: "tongyi",
    name: "通义千问 / 百炼",
    hint: "DashScope OpenAI 兼容接口",
    tags: ["LLM", "TEXT EMBEDDING"],
    defaultBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    accent: "bg-violet-500",
    icon: Sparkles,
  },
  {
    key: "deepseek",
    name: "DeepSeek",
    hint: "填 API Key + Base URL",
    tags: ["LLM"],
    defaultBaseUrl: "https://api.deepseek.com/v1",
    accent: "bg-slate-800",
    icon: Bot,
  },
  {
    key: "zhipu",
    name: "智谱 AI",
    hint: "GLM 系列",
    tags: ["LLM", "TEXT EMBEDDING"],
    defaultBaseUrl: "https://open.bigmodel.cn/api/paas/v4",
    accent: "bg-blue-600",
    icon: Wand2,
  },
  {
    key: "moonshot",
    name: "Moonshot / Kimi",
    hint: "月之暗面",
    tags: ["LLM"],
    defaultBaseUrl: "https://api.moonshot.cn/v1",
    accent: "bg-indigo-500",
    icon: Bot,
  },
  {
    key: "siliconflow",
    name: "SiliconFlow",
    hint: "硅基流动 · 多模型聚合",
    tags: ["LLM", "TEXT EMBEDDING", "TEXT RE-RANK"],
    defaultBaseUrl: "https://api.siliconflow.cn/v1",
    accent: "bg-cyan-600",
    icon: Layers,
  },
  {
    key: "volcengine",
    name: "火山引擎 / 方舟",
    hint: "Agent Plan · 模型名如 ark-code-latest",
    tags: ["LLM"],
    defaultBaseUrl: "https://ark.cn-beijing.volces.com/api/plan/v3",
    accent: "bg-orange-500",
    icon: Cloud,
  },
  {
    key: "xinference",
    name: "Xinference",
    hint: "本地 / 内网部署",
    tags: ["LLM", "TEXT EMBEDDING", "TEXT RE-RANK"],
    defaultBaseUrl: "http://127.0.0.1:9997/v1",
    accent: "bg-fuchsia-600",
    icon: Cpu,
  },
  {
    key: "ollama",
    name: "Ollama",
    hint: "本地 OpenAI 兼容桥",
    tags: ["LLM", "TEXT EMBEDDING"],
    defaultBaseUrl: "http://127.0.0.1:11434/v1",
    accent: "bg-stone-700",
    icon: Cpu,
  },
];

const FILTERS = [
  "All",
  "LLM",
  "TEXT EMBEDDING",
  "TEXT RE-RANK",
  "IMAGE2TEXT",
  "SPEECH2TEXT",
  "TTS",
] as const;

const ROLES: {
  key: string;
  label: string;
  required?: boolean;
  modelType: string;
  icon: typeof Bot;
}[] = [
  { key: "llm", label: "LLM", required: true, modelType: "llm", icon: Bot },
  {
    key: "embedding",
    label: "Embedding",
    required: true,
    modelType: "embedding",
    icon: Layers,
  },
  { key: "rerank", label: "Rerank", modelType: "rerank", icon: Wand2 },
  { key: "vlm", label: "VLM", modelType: "vlm", icon: ImageIcon },
  { key: "asr", label: "ASR", modelType: "asr", icon: Mic },
  { key: "tts", label: "TTS", modelType: "tts", icon: Volume2 },
];

function typeMeta(type?: string) {
  const t = (type || "llm").toLowerCase();
  if (t === "embedding") {
    return {
      label: "EMBEDDING",
      Icon: Layers,
      chip: "bg-cyan-50 text-cyan-700 ring-cyan-200",
      row: "from-cyan-50/80 to-white border-cyan-100",
      iconBg: "bg-cyan-500",
    };
  }
  if (t === "rerank") {
    return {
      label: "RERANK",
      Icon: Wand2,
      chip: "bg-amber-50 text-amber-800 ring-amber-200",
      row: "from-amber-50/80 to-white border-amber-100",
      iconBg: "bg-amber-500",
    };
  }
  if (t === "vlm") {
    return {
      label: "VLM",
      Icon: ImageIcon,
      chip: "bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-200",
      row: "from-fuchsia-50/80 to-white border-fuchsia-100",
      iconBg: "bg-fuchsia-500",
    };
  }
  return {
    label: "LLM",
    Icon: Bot,
    chip: "bg-violet-50 text-violet-700 ring-violet-200",
    row: "from-violet-50/80 to-white border-violet-100",
    iconBg: "bg-violet-500",
  };
}

function catalogOf(key: string) {
  return CATALOG.find((c) => c.key === key);
}

function encodeChoice(providerKey: string, modelName: string) {
  return `${providerKey}|||${modelName}`;
}

function decodeChoice(v: string): { providerKey: string; modelName: string } | null {
  if (!v) return null;
  const i = v.indexOf("|||");
  if (i < 0) return null;
  return { providerKey: v.slice(0, i), modelName: v.slice(i + 3) };
}

export function ModelProvidersPage() {
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [defaults, setDefaults] = useState<
    Record<string, { providerKey: string; modelName: string; enabled: boolean }>
  >({});
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const [search, setSearch] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [providerKey, setProviderKey] = useState("openai-compatible");
  const [displayName, setDisplayName] = useState("OpenAI 兼容");
  const [baseUrl, setBaseUrl] = useState(CATALOG[0].defaultBaseUrl);
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("");
  const [modelType, setModelType] = useState("llm");
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ModelProvider | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const reload = async () => {
    const [p, d] = await Promise.all([listProviders(), getDefaultModels()]);
    setProviders(p);
    setDefaults(d.defaults || {});
  };

  useEffect(() => {
    void reload().catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const choicesByType = useMemo(() => {
    const map: Record<string, Array<{ value: string; label: string }>> = {};
    for (const p of providers) {
      for (const m of p.models || []) {
        const t = (m.type || "llm").toLowerCase();
        if (!map[t]) map[t] = [];
        map[t].push({
          value: encodeChoice(p.providerKey, m.name),
          label: `${m.name} · ${p.displayName}`,
        });
      }
    }
    return map;
  }, [providers]);

  const filteredCatalog = useMemo(() => {
    const q = search.trim().toLowerCase();
    return CATALOG.filter((c) => {
      if (filter !== "All" && !c.tags.includes(filter)) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.hint.toLowerCase().includes(q) ||
        c.key.includes(q)
      );
    });
  }, [filter, search]);

  const openCatalog = (c: CatalogItem) => {
    const existing = providers.find((p) => p.providerKey === c.key);
    setProviderKey(c.key);
    setDisplayName(existing?.displayName || c.name);
    setBaseUrl(existing?.baseUrl || c.defaultBaseUrl);
    setApiKey("");
    setModelName("");
    setModelType(
      c.tags.includes("TEXT EMBEDDING") && !c.tags.includes("LLM")
        ? "embedding"
        : "llm",
    );
    setFormOpen(true);
    setErr(null);
  };

  const openEdit = (p: ModelProvider, preferType?: string) => {
    const cat = catalogOf(p.providerKey);
    setProviderKey(p.providerKey);
    setDisplayName(p.displayName);
    setBaseUrl(p.baseUrl || cat?.defaultBaseUrl || "");
    setApiKey("");
    setModelType(preferType || "llm");
    setModelName("");
    setFormOpen(true);
    setErr(null);
  };

  const onSaveProvider = async () => {
    try {
      const existing = providers.find((p) => p.providerKey === providerKey);
      const merged = [...(existing?.models || [])];
      if (modelName.trim()) {
        const name = modelName.trim();
        const idx = merged.findIndex((m) => m.name === name);
        if (idx >= 0) merged[idx] = { name, type: modelType };
        else merged.push({ name, type: modelType });
      }
      await upsertProvider({
        providerKey,
        displayName,
        baseUrl,
        apiKey: apiKey || undefined,
        models: merged,
      });
      setFormOpen(false);
      setApiKey("");
      setOkMsg("供应商已保存");
      window.setTimeout(() => setOkMsg(null), 2000);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const onSaveDefaults = async () => {
    try {
      await setDefaultModels(defaults);
      setOkMsg("默认模型已保存");
      window.setTimeout(() => setOkMsg(null), 2000);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const onRemoveModel = async (p: ModelProvider, modelName: string) => {
    try {
      const nextModels = (p.models || []).filter((m) => m.name !== modelName);
      await upsertProvider({
        providerKey: p.providerKey,
        displayName: p.displayName,
        baseUrl: p.baseUrl,
        models: nextModels,
      });
      const nextDefaults = { ...defaults };
      let changed = false;
      for (const [role, d] of Object.entries(nextDefaults)) {
        if (d.providerKey === p.providerKey && d.modelName === modelName) {
          nextDefaults[role] = {
            providerKey: "",
            modelName: "",
            enabled: d.enabled,
          };
          changed = true;
        }
      }
      if (changed) {
        setDefaults(nextDefaults);
        await setDefaultModels(nextDefaults);
      }
      setOkMsg(`已删除模型 ${modelName}`);
      window.setTimeout(() => setOkMsg(null), 2000);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const setRoleChoice = (roleKey: string, _modelType: string, value: string) => {
    const enabled =
      defaults[roleKey]?.enabled !== false &&
      ["llm", "embedding", "rerank"].includes(roleKey);
    const decoded = decodeChoice(value);
    setDefaults({
      ...defaults,
      [roleKey]: {
        providerKey: decoded?.providerKey || "",
        modelName: decoded?.modelName || "",
        enabled: enabled || roleKey === "llm" || roleKey === "embedding",
      },
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-900">模型供应商</h1>
        <p className="mt-1 text-sm text-slate-500">
          右侧选择模型商，填写 Base URL / API Key，并添加模型名。
        </p>
      </div>

      {err ? (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {err}
        </p>
      ) : null}
      {okMsg ? (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {okMsg}
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-base font-semibold text-slate-900">
              设置默认模型
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              问答 / 向量化等角色使用的默认条目
            </p>
            <div className="mt-4 space-y-3">
              {ROLES.map((r) => {
                const Icon = r.icon;
                const required = Boolean(r.required);
                const cur = defaults[r.key];
                const opts = choicesByType[r.modelType] || [];
                const value =
                  cur?.providerKey && cur?.modelName
                    ? encodeChoice(cur.providerKey, cur.modelName)
                    : "";
                const selected = Boolean(value);
                const provider = selected
                  ? providers.find((p) => p.providerKey === cur?.providerKey)
                  : null;
                const cat = provider ? catalogOf(provider.providerKey) : null;
                const ProviderIcon = cat?.icon || Cloud;
                return (
                  <div
                    key={r.key}
                    className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-100 bg-slate-50/60 px-3 py-2.5"
                  >
                    <div className="flex w-28 items-center gap-2 text-sm font-medium text-slate-700">
                      <span
                        className={`flex h-7 w-7 items-center justify-center rounded-lg ${
                          selected
                            ? "bg-violet-600 text-white"
                            : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                      <span>
                        {required ? (
                          <span className="text-rose-500">*</span>
                        ) : null}
                        {r.label}
                      </span>
                    </div>
                    <div className="relative min-w-[16rem] flex-1">
                      {selected ? (
                        <span
                          className={`pointer-events-none absolute left-2.5 top-1/2 z-[1] flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-white ${cat?.accent || "bg-violet-500"}`}
                        >
                          <ProviderIcon className="h-3.5 w-3.5" />
                        </span>
                      ) : null}
                      <select
                        className={`w-full appearance-none rounded-xl py-2.5 pr-10 text-sm outline-none transition ${
                          selected
                            ? "border-2 border-violet-500 bg-violet-50/70 pl-11 font-medium text-slate-900 shadow-sm shadow-violet-500/10"
                            : required
                              ? "border border-dashed border-amber-300 bg-amber-50/40 pl-3 text-slate-400"
                              : "border border-slate-200 bg-slate-50/80 pl-3 text-slate-400"
                        }`}
                        value={value}
                        onChange={(e) =>
                          setRoleChoice(r.key, r.modelType, e.target.value)
                        }
                      >
                        <option value="">
                          {opts.length
                            ? "请选择模型"
                            : "暂无该类型模型，请先添加"}
                        </option>
                        {opts.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                      {selected ? (
                        <button
                          type="button"
                          title="清除选择"
                          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full px-1.5 text-sm leading-none text-slate-400 hover:bg-white hover:text-slate-700"
                          onClick={() => setRoleChoice(r.key, r.modelType, "")}
                        >
                          ×
                        </button>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
            <button
              type="button"
              className="mt-4 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              onClick={() => void onSaveDefaults()}
            >
              保存默认模型
            </button>
          </section>

          <section>
            <div className="flex items-end justify-between gap-2">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  已添加的模型
                </h2>
                <p className="mt-0.5 text-xs text-slate-400">
                  同一供应商可挂多个模型；打「默认」标记的已用于上方角色
                </p>
              </div>
            </div>
            <div className="mt-3 space-y-3">
              {providers.length === 0 ? (
                <p className="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-400">
                  尚未添加供应商，请从右侧选择。
                </p>
              ) : null}
              {providers.map((p) => {
                const cat = catalogOf(p.providerKey);
                const Icon = cat?.icon || Cloud;
                const models = p.models || [];
                const open = expanded[p.providerKey] ?? models.length > 0;
                const defaultNames = new Set(
                  Object.values(defaults)
                    .filter((d) => d.providerKey === p.providerKey && d.modelName)
                    .map((d) => d.modelName),
                );
                return (
                  <div
                    key={p.providerKey}
                    className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
                  >
                    <div className="flex flex-wrap items-center gap-3 bg-gradient-to-r from-slate-50/80 to-white px-4 py-3.5">
                      <span
                        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-white shadow-sm ${cat?.accent || "bg-slate-600"}`}
                      >
                        <Icon className="h-5 w-5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-slate-900">
                          {p.displayName}
                        </p>
                        <p className="mt-0.5 truncate font-mono text-[11px] text-slate-400">
                          {p.baseUrl || "—"}
                        </p>
                      </div>
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ${
                          p.apiKeySet
                            ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100"
                            : "bg-amber-50 text-amber-700 ring-1 ring-amber-100"
                        }`}
                      >
                        <KeyRound className="h-3 w-3" />
                        {p.apiKeySet ? "Key 已配置" : "Key 未配置"}
                      </span>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:border-violet-300 hover:text-violet-700"
                          onClick={() => openEdit(p)}
                        >
                          <Plus className="h-3.5 w-3.5" />
                          添加
                        </button>
                        <button
                          type="button"
                          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                          onClick={() =>
                            setExpanded((s) => ({
                              ...s,
                              [p.providerKey]: !open,
                            }))
                          }
                        >
                          {open ? "收起" : `模型 ${models.length}`}
                        </button>
                        <button
                          type="button"
                          className="rounded-lg p-1.5 text-rose-500 hover:bg-rose-50"
                          onClick={() => setPendingDelete(p)}
                          title="删除"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                    {open ? (
                      <ul className="space-y-2 border-t border-slate-100 bg-slate-50/40 px-4 py-3">
                        {models.length === 0 ? (
                          <li className="rounded-xl border border-dashed border-slate-200 bg-white px-3 py-4 text-center text-xs text-slate-400">
                            暂无模型条目，点击「添加」挂上 llm / embedding
                          </li>
                        ) : (
                          models.map((m) => {
                            const meta = typeMeta(m.type);
                            const TypeIcon = meta.Icon;
                            const isDefault = defaultNames.has(m.name);
                            return (
                              <li
                                key={`${m.name}-${m.type}`}
                                className={`flex items-center gap-3 rounded-xl border bg-gradient-to-r px-3 py-2.5 ${meta.row}`}
                              >
                                <span
                                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white ${meta.iconBg}`}
                                >
                                  <TypeIcon className="h-4 w-4" />
                                </span>
                                <div className="min-w-0 flex-1">
                                  <p className="truncate font-mono text-sm font-medium text-slate-800">
                                    {m.name}
                                  </p>
                                  {isDefault ? (
                                    <p className="mt-0.5 text-[10px] font-medium text-violet-600">
                                      已设为默认角色
                                    </p>
                                  ) : null}
                                </div>
                                {isDefault ? (
                                  <span className="rounded-full bg-violet-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                                    默认
                                  </span>
                                ) : null}
                                <span
                                  className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset ${meta.chip}`}
                                >
                                  {meta.label}
                                </span>
                                {(m.type || "llm").toLowerCase() === "llm" ||
                                (m.type || "llm").toLowerCase() === "vlm" ? (
                                  <Link
                                    to={`/settings/models/test?provider=${encodeURIComponent(p.providerKey)}&model=${encodeURIComponent(m.name)}`}
                                    className="inline-flex items-center gap-1 rounded-lg border border-violet-200 bg-white px-2 py-1 text-[11px] font-medium text-violet-700 hover:bg-violet-50"
                                    title="跳转对话测试"
                                  >
                                    <MessageSquare className="h-3.5 w-3.5" />
                                    对话测试
                                  </Link>
                                ) : null}
                                <button
                                  type="button"
                                  className="rounded-lg p-1.5 text-rose-500 hover:bg-rose-50"
                                  title="删除此模型"
                                  onClick={() =>
                                    void onRemoveModel(p, m.name)
                                  }
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </li>
                            );
                          })
                        )}
                      </ul>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </section>
        </div>

        <aside className="h-fit rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:sticky lg:top-20">
          <h2 className="font-semibold text-slate-900">可选模型商</h2>
          <div className="relative mt-3">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2 pl-8 pr-3 text-sm outline-none focus:border-violet-400 focus:bg-white"
            />
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  filter === f
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <ul className="mt-3 max-h-[70vh] space-y-2 overflow-y-auto pr-0.5">
            {filteredCatalog.map((c) => {
              const Icon = c.icon;
              return (
                <li key={c.key}>
                  <button
                    type="button"
                    className="flex w-full items-start gap-3 rounded-xl border border-slate-200 px-3 py-2.5 text-left transition hover:border-violet-300 hover:bg-violet-50/40"
                    onClick={() => openCatalog(c)}
                  >
                    <span
                      className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white ${c.accent}`}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-slate-900">
                        {c.name}
                      </span>
                      <span className="mt-0.5 block text-[11px] text-slate-400">
                        {c.hint}
                      </span>
                      <span className="mt-1.5 flex flex-wrap gap-1">
                        {c.tags.map((t) => (
                          <span
                            key={t}
                            className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-500"
                          >
                            {t}
                          </span>
                        ))}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
            {filteredCatalog.length === 0 ? (
              <li className="py-6 text-center text-xs text-slate-400">无匹配项</li>
            ) : null}
          </ul>
        </aside>
      </div>

      {formOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
            <h3 className="text-lg font-semibold">配置模型</h3>
            <p className="mt-1 text-xs text-slate-400">
              同一供应商可多次打开，分别添加 llm / embedding 等模型条目
            </p>
            <label className="mt-3 block text-xs text-slate-500">显示名</label>
            <input
              className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
            <label className="mt-3 block text-xs text-slate-500">
              Provider Key（内部代号，一般不用改）
            </label>
            <input
              className="mt-1 w-full rounded-lg border bg-slate-50 px-3 py-2 text-sm"
              value={providerKey}
              onChange={(e) => setProviderKey(e.target.value)}
            />
            <label className="mt-3 block text-xs text-slate-500">基础 Url</label>
            <input
              className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://.../compatible-mode/v1"
            />
            <label className="mt-3 block text-xs text-slate-500">* API-Key</label>
            <input
              className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                providers.some((p) => p.providerKey === providerKey && p.apiKeySet)
                  ? "留空则保留已有 Key"
                  : "粘贴百炼 / 供应商 Key"
              }
            />
            <label className="mt-3 block text-xs text-slate-500">模型类型</label>
            <select
              className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
              value={modelType}
              onChange={(e) => setModelType(e.target.value)}
            >
              <option value="llm">llm</option>
              <option value="embedding">embedding</option>
              <option value="rerank">rerank</option>
              <option value="vlm">vlm</option>
              <option value="asr">asr</option>
              <option value="tts">tts</option>
            </select>
            <label className="mt-3 block text-xs text-slate-500">模型名</label>
            <input
              className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="如 qwen3.8 / qwen3.7-flash"
            />
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border px-3 py-2 text-sm"
                onClick={() => setFormOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white"
                onClick={() => void onSaveProvider()}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {pendingDelete ? (
        <ConfirmModal
          title="删除供应商"
          message={`确定删除「${pendingDelete.displayName}」？`}
          confirmText="删除"
          danger
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            const key = pendingDelete.providerKey;
            setPendingDelete(null);
            void deleteProvider(key).then(reload);
          }}
        />
      ) : null}
    </div>
  );
}
