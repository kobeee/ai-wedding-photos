export interface UploadFileInfo {
  id: string
  filename: string
  url: string
  role: string
  slot: string
}

export interface UploadValidationIssue {
  level: 'error' | 'warning'
  message: string
  slot: string
}

export interface UploadValidationSummary {
  ok: boolean
  issues: UploadValidationIssue[]
  summary: string
}

export interface UploadResponse {
  user_id: string
  session_token: string
  files: UploadFileInfo[]
  validation?: UploadValidationSummary | null
}

export interface MakeupResponse {
  user_id: string
  images: string[]
}

export interface GenerateResponse {
  task_id: string
  status: 'pending' | 'processing' | 'quality_check' | 'completed' | 'failed'
}

export interface TaskStatusResponse {
  task_id: string
  status: 'pending' | 'processing' | 'quality_check' | 'completed' | 'failed'
  progress: number
  message: string
  quality_score: number
  result_urls: string[]
}

export interface EntitlementSnapshot {
  promised_photos: number
  scene_count: number
  photo_mix: Record<string, number>
  rerun_quota: number
  repaint_quota: number
  retention_days: number
  delivery_specs: string[]
  preview_policy: string
}

export interface PackageInfo {
  id: string
  name: string
  tag: string
  category: 'chinese' | 'western' | 'artistic' | 'travel'
  preview_url: string
}

export interface SkuInfo {
  sku_id: string
  name: string
  description: string
  tag: string
  price: number
  currency: string
  active: boolean
  highlight: boolean
  entitlements: EntitlementSnapshot
}

export interface GenerationBatchInfo {
  batch_id: string
  order_id: string
  batch_type: 'preview' | 'initial' | 'rerun' | 'manual_retouch'
  initiated_by: 'system' | 'user' | 'support'
  status: 'pending' | 'processing' | 'completed' | 'failed'
  requested_photos: number
  delivered_photos: number
  progress: number
  message: string
  quality_score: number
  failure_reason: string
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface DeliverableInfo {
  deliverable_id: string
  order_id: string
  batch_id: string
  url: string
  photo_status: string
  quality_score: number
  delivery_tier: 'preview' | '4k'
  created_at: string
}

export interface OrderInfo {
  order_id: string
  identity_id: string
  sku_id: string
  package_id: string
  amount: number
  currency: string
  payment_status: 'unpaid' | 'pending' | 'paid' | 'free_granted' | 'failed' | 'refunded' | 'expired'
  fulfillment_status: 'not_started' | 'queued' | 'processing' | 'delivered' | 'partially_delivered' | 'failed'
  service_status: 'normal' | 'aftersale' | 'closed'
  entitlement_snapshot: EntitlementSnapshot
  rerun_used_count: number
  created_at: string
  paid_at: string | null
  expired_at: string | null
  closed_at: string | null
  latest_batch: GenerationBatchInfo | null
  deliverable_count: number
  remaining_reruns: number
  package_name: string
  sku_name: string
}

export interface OrderListResponse {
  items: OrderInfo[]
}

export interface BatchListResponse {
  items: GenerationBatchInfo[]
}

export interface DeliverableListResponse {
  items: DeliverableInfo[]
}

export interface PaymentSessionResponse {
  payment_id: string
  order_id: string
  provider: 'mock' | 'alipay'
  status: string
  amount: number
  currency: string
  checkout_url: string
}

export interface PaymentConfirmResponse {
  payment_id: string
  order_id: string
  payment_status: OrderInfo['payment_status']
  paid_at: string | null
}

export interface StartOrderResponse {
  order_id: string
  batch_id: string
  fulfillment_status: OrderInfo['fulfillment_status']
}

type ApiRequestOptions = RequestInit

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function readErrorMessage(response: Response): Promise<string> {
  if (response.status === 413) {
    return '上传内容过大：你这次一共上传了太大的原图，请压缩部分照片后重试。'
  }

  try {
    const payload = (await response.json()) as { detail?: string | string[] }
    if (typeof payload.detail === 'string' && payload.detail) {
      return payload.detail
    }
    if (Array.isArray(payload.detail) && payload.detail.length > 0) {
      return payload.detail.join('；')
    }
  } catch {
    // Ignore JSON parsing failures and fall back to the status line.
  }

  return `Request failed with status ${response.status}`
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers)

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  const response = await fetch(path, {
    credentials: 'include',
    ...options,
    headers,
  })

  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status)
  }

  return (await response.json()) as T
}

export async function fetchLatestOrder(): Promise<OrderInfo | null> {
  const payload = await apiRequest<OrderListResponse>('/api/orders')
  return payload.items[0] ?? null
}

export function formatPrice(amount: number, currency = 'CNY'): string {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount / 100)
}
