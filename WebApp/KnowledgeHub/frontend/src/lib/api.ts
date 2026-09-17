import { authHeaders } from "./auth";

export type Pipeline = {
  id: string;
  labelZh: string;
  defaultChunk: string;
};

export type ChunkStrategy = {
  id: string;
  labelZh: string;
  description: string;
};

export type KhCollection = {
  id: number;
  name: string;
  description: string;
  pipeline: string;
  chunkStrategy: string;
  documentCount: number;
  updatedAt?: string;
};

export type KhDocument = {
  id: number;
  collectionId: number;
  title: string;
  status: string;
  /** 停用后不进 search/ask */
  enabled?: boolean;
  parseError?: string;
  chunkStrategy?: string;
  chunkCount?: number;
  /** ready | none | error */
  embedStatus?: string;
  bodyPreview?: string;
  body?: string;
  sourceType?: string;
  ingestMode?: string;
  domain?: string;
  payload?: Record<string, unknown>;
  hasAttachment?: boolean;
  attachmentFileId?: number | null;
  fileName?: string;
  fileSize?: number;
  createdAt?: string;
  updatedAt?: string;
};

export type KhChunk = {
  id: number;
  documentId: number;
  ordinal: number;
  text: string;
  meta?: Record<string, unknown>;
  createdAt?: string;
};

export type KhChat = {
  id: number;
  name: string;
  description: string;
  opener: string;
  systemPrompt: string;
  emptyResponse: string;
  collectionIds: number[];
  modelName: string;
  temperature?: number | null;
  topP?: number | null;
  maxTokens?: number | null;
  updatedAt?: string;
};

export type KhFile = {
  id: number;
  title: string;
  fileName: string;
  fileSize: number;
  collectionId?: number | null;
  collectionName?: string;
  createdAt?: string;
};

export type ModelProvider = {
  id: number;
  providerKey: string;
  displayName: string;
  baseUrl: string;
  apiKeySet: boolean;
  models: Array<{ name: string; type?: string }>;
};

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  const data = (await res.json().catch(() => ({}))) as T & {
    error?: string;
    detail?: string | Array<{ msg?: string }>;
  };
  if (!res.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((x) => x.msg || JSON.stringify(x)).join("; ")
          : "";
    throw new Error(data.error || detail || `HTTP ${res.status}`);
  }
  return data as T;
}

export async function fetchMeta() {
  return apiJson<{
    pipelines: Pipeline[];
    chunkStrategies: ChunkStrategy[];
    structuredDomains?: Array<{ id: string; labelZh: string }>;
    docTypes?: string[];
    structuredFieldLabels?: Record<string, string>;
  }>("/api/kh/meta");
}

export async function listCollections() {
  const d = await apiJson<{ collections: KhCollection[] }>("/api/kh/collections");
  return d.collections || [];
}

export async function createCollection(body: {
  name: string;
  description?: string;
  pipeline?: string;
  chunkStrategy?: string;
}) {
  const d = await apiJson<{ collection: KhCollection }>("/api/kh/collections", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return d.collection;
}

export async function deleteCollection(id: number) {
  return apiJson(`/api/kh/collections/${id}`, { method: "DELETE" });
}

export async function updateCollection(
  id: number,
  body: { name?: string; description?: string; pipeline?: string; chunkStrategy?: string },
) {
  const d = await apiJson<{ collection: KhCollection }>(`/api/kh/collections/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return d.collection;
}

export async function updateDocument(
  docId: number,
  body: { title?: string; fileName?: string; enabled?: boolean },
) {
  const d = await apiJson<{ document: KhDocument }>(`/api/kh/documents/${docId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return d.document;
}

export async function listDocuments(collectionId: number) {
  const d = await apiJson<{ documents: KhDocument[] }>(
    `/api/kh/collections/${collectionId}/documents`,
  );
  return d.documents || [];
}

export async function createDocument(body: {
  collectionId: number;
  title: string;
  body?: string;
  chunkStrategy?: string;
  sourceType?: string;
  fileName?: string;
  fileSize?: number;
  ingest?: boolean;
  /** .docx / .pdf：浏览器读成 base64，由服务端抽文本 */
  contentBase64?: string;
}) {
  const d = await apiJson<{ document: KhDocument }>("/api/kh/documents", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return d.document;
}

export async function createStructuredDocument(body: {
  collectionId: number;
  domain?: string;
  payload: Record<string, unknown>;
  chunkStrategy?: string;
  ingest?: boolean;
  attachmentBase64?: string;
  attachmentFileName?: string;
}) {
  const d = await apiJson<{ document: KhDocument }>("/api/kh/documents/structured", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return d.document;
}

export async function downloadDocumentAttachment(docId: number) {
  const d = await apiJson<{
    fileName: string;
    mimeType: string;
    contentBase64: string;
  }>(`/api/kh/documents/${docId}/attachment`);
  const raw = atob(d.contentBase64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  const blob = new Blob([bytes], { type: d.mimeType || "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = d.fileName || "attachment";
  a.click();
  URL.revokeObjectURL(url);
}

export async function deleteDocument(docId: number) {
  return apiJson(`/api/kh/documents/${docId}`, { method: "DELETE" });
}

export async function ingestDocument(docId: number) {
  return apiJson<{
    documentId: number;
    status: string;
    chunkCount: number;
    embeddedCount?: number;
    embedError?: string | null;
  }>(`/api/kh/documents/${docId}/ingest`, {
    method: "POST",
    body: "{}",
  });
}

export type IngestProgress = {
  documentId: number;
  phase: string;
  done: number;
  total: number;
  percent: number;
  title?: string;
  message?: string;
};

export async function getIngestProgress(docId: number) {
  const d = await apiJson<{ progress: IngestProgress }>(
    `/api/kh/documents/${docId}/progress`,
  );
  return d.progress;
}

export async function getDocument(docId: number) {
  const d = await apiJson<{ document: KhDocument }>(`/api/kh/documents/${docId}`);
  return d.document;
}

export async function listChunks(docId: number) {
  const d = await apiJson<{ chunks: KhChunk[]; documentId: number }>(
    `/api/kh/documents/${docId}/chunks`,
  );
  return d.chunks || [];
}

export type KhSearchHit = {
  chunkId: number;
  documentId: number;
  collectionId: number;
  collectionName: string;
  documentTitle: string;
  ordinal: number;
  text: string;
  meta?: Record<string, unknown>;
  score: number;
  attachment?: {
    available?: boolean;
    fileName?: string;
    downloadUrl?: string;
  };
};

export type KhReferencedDocument = {
  documentId: number;
  documentTitle: string;
  collectionId?: number;
  attachment?: {
    available?: boolean;
    fileName?: string;
    downloadUrl?: string;
  };
};

export async function searchChunks(body: {
  query: string;
  collectionIds?: number[];
  collectionId?: number;
  topK?: number;
}) {
  return apiJson<{
    query: string;
    mode: string;
    topK: number;
    collectionIds: number[];
    totalCandidates: number;
    hits: KhSearchHit[];
    referencedDocuments?: KhReferencedDocument[];
  }>("/api/kh/search", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type KhAskResult = {
  query: string;
  answer: string;
  grounded: boolean;
  mode?: string;
  topK?: number;
  collectionIds?: number[];
  totalCandidates?: number;
  hits: KhSearchHit[];
  referencedDocuments?: KhReferencedDocument[];
  llmConfigured?: boolean;
  model?: string | null;
  providerKey?: string | null;
  tokensIn?: number;
  tokensOut?: number;
};

export async function askKh(body: {
  query: string;
  collectionIds?: number[];
  collectionId?: number;
  chatId?: number;
  topK?: number;
}) {
  return apiJson<KhAskResult>("/api/kh/ask", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listChats() {
  const d = await apiJson<{ chats: KhChat[] }>("/api/kh/chats");
  return d.chats || [];
}

export async function createChat(name: string) {
  const d = await apiJson<{ chat: KhChat }>("/api/kh/chats", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  return d.chat;
}

export async function updateChat(id: number, body: Partial<KhChat>) {
  const d = await apiJson<{ chat: KhChat }>(`/api/kh/chats/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return d.chat;
}

export type KhChatMessage = {
  id: number;
  chatId: number;
  conversationId?: number | null;
  role: "user" | "assistant" | "system" | string;
  content: string;
  meta?: {
    kind?: string;
    mode?: string;
    totalCandidates?: number;
    hits?: KhSearchHit[];
    error?: string;
    [key: string]: unknown;
  };
  createdAt?: string;
};

export type KhConversation = {
  id: number;
  chatId: number;
  title: string;
  messageCount?: number;
  createdAt?: string;
  updatedAt?: string;
};

export async function listConversations(chatId: number) {
  const d = await apiJson<{ conversations: KhConversation[]; chatId: number }>(
    `/api/kh/chats/${chatId}/conversations`,
  );
  return d.conversations || [];
}

export async function createConversation(chatId: number, title = "新会话") {
  const d = await apiJson<{ conversation: KhConversation }>(
    `/api/kh/chats/${chatId}/conversations`,
    {
      method: "POST",
      body: JSON.stringify({ title }),
    },
  );
  return d.conversation;
}

export async function updateConversation(
  conversationId: number,
  body: { title: string },
) {
  const d = await apiJson<{ conversation: KhConversation }>(
    `/api/kh/conversations/${conversationId}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
  return d.conversation;
}

export async function deleteConversation(conversationId: number) {
  return apiJson(`/api/kh/conversations/${conversationId}`, { method: "DELETE" });
}

export async function listChatMessages(chatId: number) {
  const d = await apiJson<{ messages: KhChatMessage[]; chatId: number }>(
    `/api/kh/chats/${chatId}/messages`,
  );
  return d.messages || [];
}

export async function listConversationMessages(conversationId: number) {
  const d = await apiJson<{
    messages: KhChatMessage[];
    conversationId: number;
    chatId: number;
  }>(`/api/kh/conversations/${conversationId}/messages`);
  return d.messages || [];
}

export async function appendChatMessage(
  chatId: number,
  body: { role: string; content?: string; meta?: Record<string, unknown> },
) {
  const d = await apiJson<{ message: KhChatMessage }>(
    `/api/kh/chats/${chatId}/messages`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
  return d.message;
}

export async function appendConversationMessage(
  conversationId: number,
  body: { role: string; content?: string; meta?: Record<string, unknown> },
) {
  const d = await apiJson<{ message: KhChatMessage }>(
    `/api/kh/conversations/${conversationId}/messages`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
  return d.message;
}

export async function clearChatMessages(chatId: number) {
  return apiJson<{ ok: boolean; deleted: number }>(
    `/api/kh/chats/${chatId}/messages`,
    { method: "DELETE" },
  );
}

export async function clearConversationMessages(conversationId: number) {
  return apiJson<{ ok: boolean; deleted: number }>(
    `/api/kh/conversations/${conversationId}/messages`,
    { method: "DELETE" },
  );
}

export async function deleteChat(id: number) {
  return apiJson(`/api/kh/chats/${id}`, { method: "DELETE" });
}

export async function listFiles() {
  const d = await apiJson<{ files: KhFile[] }>("/api/kh/files");
  return d.files || [];
}

export async function createFile(body: {
  title: string;
  body?: string;
  fileName?: string;
  collectionId?: number | null;
}) {
  const d = await apiJson<{ file: KhFile }>("/api/kh/files", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return d.file;
}

export async function deleteFile(id: number) {
  return apiJson(`/api/kh/files/${id}`, { method: "DELETE" });
}

export async function listProviders() {
  const d = await apiJson<{ providers: ModelProvider[] }>(
    "/api/kh/model-providers",
  );
  return d.providers || [];
}

export async function upsertProvider(body: Record<string, unknown>) {
  const d = await apiJson<{ provider: ModelProvider }>(
    "/api/kh/model-providers",
    { method: "POST", body: JSON.stringify(body) },
  );
  return d.provider;
}

export async function deleteProvider(key: string) {
  return apiJson(`/api/kh/model-providers/${encodeURIComponent(key)}`, {
    method: "DELETE",
  });
}

export async function testProviderChat(body: {
  providerKey: string;
  modelName: string;
  message: string;
}) {
  return apiJson<{
    ok: boolean;
    answer: string;
    model?: string;
    providerKey?: string;
    tokensIn?: number;
    tokensOut?: number;
  }>("/api/kh/model-providers/test", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getDefaultModels() {
  return apiJson<{
    defaults: Record<
      string,
      { roleKey: string; providerKey: string; modelName: string; enabled: boolean }
    >;
  }>("/api/kh/default-models");
}

export async function setDefaultModels(defaults: Record<string, unknown>) {
  return apiJson("/api/kh/default-models", {
    method: "POST",
    body: JSON.stringify({ defaults }),
  });
}

export type ApiEndpointDoc = {
  id: string;
  method: string;
  path: string;
  summary: string;
  status: string;
  request?: unknown;
  responseExample?: unknown;
};

export type ApiCatalog = {
  title: string;
  version: string;
  baseUrl: string;
  auth: string;
  note?: string;
  endpoints: ApiEndpointDoc[];
};

export async function fetchApiOutline() {
  return apiJson<ApiCatalog>("/api/kh/docs/outline");
}
