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
  debit: string
  credit: string
  balance: string | null
  extra: Record<string, string>
  category: string | null
  category_source: 'laya' | 'manual' | null
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

  constructor(status: number, message: string, code: UploadErrorCode | null = null) {
    super(message)
    this.status = status
    this.code = code
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

export function categoriseStatement(statementId: number, redo = false): Promise<{ started: boolean }> {
  return request(`/api/statements/${statementId}/categorise?redo=${redo}`, { method: 'POST' })
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
