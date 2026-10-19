// Typed client for the FastAPI backend (backend/app/api/statements.py).

// Empty in development (Vite proxies /api); set VITE_API_BASE when the API is hosted elsewhere.
const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

export type Statement = {
  id: number
  filename: string
  bank: string | null
  account_number: string | null
  period: string | null
  header_mapping: string | null
  balance_check: string
  uploaded_at: string
  transaction_count: number
  categorised_count: number
  categorising: boolean
}

// Amounts arrive as decimal strings ("450.00") so no precision is lost.
export type Transaction = {
  id: number
  row_index: number
  date: string
  particulars: string
  particulars_masked: string | null // what Jev would see
  debit: string
  credit: string
  balance: string | null
  extra: Record<string, string>
  category: string | null
  category_source: 'laya' | 'jev' | 'rule' | 'manual' | null
  category_rule_id: number | null // the rule that set it, when the source is 'rule'
  category_confidence: number | null
}

export type Direction = 'out' | 'in'
export type Category = { name: string; description: string }
export type Categories = Record<Direction, Category[]>

export type MonthlyFlow = { month: string; money_in: string; money_out: string; net: string }
export type CategoryTotal = { category: string; total: string; count: number }
export type TrendPoint = { month: string; total: string }

/** Period and filters for the money-flow views; months are "YYYY-MM". */
export type FlowFilters = { from?: string; to?: string; excludeSelf: boolean }

export type Health = { database: 'ok'; server_jev_key: boolean }

export type UploadErrorCode =
  | 'password_required'
  | 'wrong_password'
  | 'not_a_pdf'
  | 'no_text_layer'
  | 'no_transactions'
  | 'duplicate'
  | 'too_large'

export class ApiError extends Error {
  readonly status: number
  readonly code: UploadErrorCode | null
  readonly condition: number | null // a rule error: which condition (1-based, in reading order)

  constructor(status: number, message: string, code: UploadErrorCode | null = null, condition: number | null = null) {
    super(message)
    this.status = status
    this.code = code
    this.condition = condition
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the backend running?")
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    if (detail && typeof detail === 'object' && 'code' in detail) {
      throw new ApiError(response.status, detail.message, detail.code)
    }
    if (detail && typeof detail === 'object' && 'message' in detail) {
      throw new ApiError(response.status, detail.message, null, detail.condition ?? null)
    }
    if (Array.isArray(detail) && detail[0]?.msg) {
      throw new ApiError(response.status, detail[0].msg) // FastAPI's request validation
    }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : `Request failed (${response.status})`)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

export function getHealth(): Promise<Health> {
  return request('/api/health')
}

export function uploadStatement(file: File, options: { password?: string; apiKey?: string } = {}): Promise<Statement> {
  const form = new FormData()
  form.append('file', file)
  if (options.password) form.append('password', options.password)
  const headers: Record<string, string> = {}
  if (options.apiKey) headers['X-TypeSafe-Key'] = options.apiKey
  return request('/api/statements', { method: 'POST', body: form, headers })
}

export function listStatements(): Promise<Statement[]> {
  return request('/api/statements')
}

export function listTransactions(statementId: number): Promise<Transaction[]> {
  return request(`/api/statements/${statementId}/transactions`)
}

export function deleteStatement(statementId: number): Promise<void> {
  return request(`/api/statements/${statementId}`, { method: 'DELETE' })
}

export type Categoriser = 'laya' | 'jev'

export function categoriseStatement(
  statementId: number,
  options: { categoriser: Categoriser; redo?: boolean; apiKey?: string },
): Promise<{ started: boolean }> {
  const headers: Record<string, string> = {}
  if (options.categoriser === 'jev' && options.apiKey) headers['X-TypeSafe-Key'] = options.apiKey
  const params = `categoriser=${options.categoriser}&redo=${options.redo ?? false}`
  return request(`/api/statements/${statementId}/categorise?${params}`, { method: 'POST', headers })
}

export function getCategories(): Promise<Categories> {
  return request('/api/categories')
}

export function setCategory(transactionId: number, category: string): Promise<Transaction> {
  return request(`/api/transactions/${transactionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category }),
  })
}

function query(params: Record<string, string | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') search.set(key, String(value))
  return search.toString()
}

export function getMonthlyFlow(filters: FlowFilters): Promise<MonthlyFlow[]> {
  return request(`/api/analytics/monthly?${query({ from: filters.from, to: filters.to, exclude_self: filters.excludeSelf })}`)
}

export function getCategoryTotals(direction: Direction, filters: FlowFilters): Promise<CategoryTotal[]> {
  const params = { direction, from: filters.from, to: filters.to, exclude_self: filters.excludeSelf }
  return request(`/api/analytics/categories?${query(params)}`)
}

export function getTrend(category: string, filters: FlowFilters): Promise<TrendPoint[]> {
  return request(`/api/analytics/trend?${query({ category, from: filters.from, to: filters.to })}`)
}

// ---------------------------------------------------------------- search & bulk categories

export type SearchRow = Transaction & { statement_id: number; bank: string | null; account_last4: string | null }
export type SearchResult = { total: number; transactions: SearchRow[] }
export type SearchFilters = { q: string; direction?: Direction; category?: string; statementId?: number }

export function searchTransactions(filters: SearchFilters): Promise<SearchResult> {
  const params = new URLSearchParams()
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.direction) params.set('direction', filters.direction)
  if (filters.category) params.set('category', filters.category)
  if (filters.statementId !== undefined) params.set('statement_id', String(filters.statementId))
  return request(`/api/transactions?${params}`)
}

export function setCategoryForMany(ids: number[], category: string): Promise<{ updated: number }> {
  return request('/api/transactions/bulk', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, category }),
  })
}

// ---------------------------------------------------------------- rules (backend/app/rules)
// The builder's vocabulary (columns, operators, connectors, input kinds, limits) comes only from
// GET /api/rules/config, so these types are generic: nothing here names a column or an operator.

export type RuleOption = { id: string; label: string; hint?: string | null }
export type RuleField = { id: string; label: string; type: string }
export type RuleType = { input: string; operators: RuleOption[] }
export type RuleLimits = { max_conditions: number; max_value_length: number; max_depth: number }
export type RuleConfig = {
  fields: RuleField[]
  types: Record<string, RuleType>
  connectors: RuleOption[] // tightest-binding first (AND before OR)
  categories: Categories
  limits: RuleLimits
}

export type Condition = { field: string; operator: string; value: string }
export type ConditionGroup = { match: string; items: (Condition | ConditionGroup)[] }
export type RuleDraft = { conditions: ConditionGroup; category: string }
export type Rule = RuleDraft & { id: number; name: string; position: number; applied_count: number }
export type RulePreview = {
  total: number
  will_set: number
  manual: number
  wrong_direction: number
  other_rule: number
  transactions: SearchRow[]
}
export type RuleApplied = { set: number; cleared: number }

const JSON_HEADERS = { 'Content-Type': 'application/json' }

export function getRuleConfig(): Promise<RuleConfig> {
  return request('/api/rules/config')
}

export function listRules(): Promise<Rule[]> {
  return request('/api/rules')
}

export function createRule(rule: RuleDraft & { name: string }): Promise<Rule> {
  return request('/api/rules', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(rule) })
}

export function updateRule(id: number, rule: RuleDraft & { name: string }): Promise<Rule> {
  return request(`/api/rules/${id}`, { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify(rule) })
}

export function deleteRule(id: number): Promise<void> {
  return request(`/api/rules/${id}`, { method: 'DELETE' })
}

export function previewRule(draft: RuleDraft, ruleId?: number): Promise<RulePreview> {
  const params = ruleId === undefined ? '' : `?rule_id=${ruleId}`
  return request(`/api/rules/preview${params}`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(draft) })
}

export function applyRule(id: number): Promise<RuleApplied> {
  return request(`/api/rules/${id}/apply`, { method: 'POST' })
}

export function applyAllRules(): Promise<RuleApplied> {
  return request('/api/rules/apply', { method: 'POST' })
}
