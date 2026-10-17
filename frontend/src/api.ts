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
}

// Amounts arrive as decimal strings ("450.00") so no precision is lost.
export type Transaction = {
  row_index: number
  date: string
  particulars: string
  debit: string
  credit: string
  balance: string | null
  extra: Record<string, string>
}

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
