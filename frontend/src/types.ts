export type Role = 'user' | 'admin'

export type ChatMode = 'struct' | 'local' | 'global' | 'basic'

// --- Auth (FR-1.x) ---

export interface AuthResponse {
  token: string
  role: Role
  vk_user_id: string | null
  expires_at: string
}

export interface AdminRequest {
  api_key: string
}

export interface VkRequest {
  params: Record<string, string>
  sign: string
}

export interface MeResponse {
  role: Role
  vk_user_id: string | null
  expires_at: string
}

export interface LogoutResponse {
  ok: boolean
}

// --- Chat (FR-3.x) ---

export interface SourceInfo {
  title: string
  url: string
}

export interface ChatRequest {
  question: string
  history?: unknown[]
  // Панель «Рентген» (только admin): вернуть секции контекста дословно.
  include_context?: boolean
}

export interface ContextBlocks {
  graph?: string | null
  source_posts?: string | null
  posts?: string | null
  communities?: string | null
}

export interface TracePlanner {
  plan: Record<string, unknown>
  cypher: string | null
  params: Record<string, unknown>
}

export interface TraceInfo {
  router: { mode: ChatMode }
  planner: TracePlanner | null
  graph_rows: Record<string, unknown>[]
}

export interface ChatResponse {
  answer: string
  sources: SourceInfo[]
  media: string[]
  mode: ChatMode
  facts_count: number
  posts_used: number
  context?: ContextBlocks | null
  trace?: TraceInfo | null
}

// --- Status (FR-4.x) ---

export interface StatusResponse {
  status: string
  qdrant_points: number
  neo4j_nodes: number
  neo4j_relations: number
  documents_count: number
  ollama_available: boolean
  errors: string[]
}