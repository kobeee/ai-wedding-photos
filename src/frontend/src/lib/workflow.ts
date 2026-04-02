export interface PackageSelection {
  id: string
  name: string
  tag: string
}

export interface SkuSelection {
  id: string
  name: string
  price: number
  description: string
  tag: string
}

export interface MakeupOptions {
  groom: string[]
  bride: string[]
}

export interface MakeupSelection {
  groom: string
  bride: string
}

export interface PersistedUploadFile {
  id: string
  filename: string
  url: string
  role: string
  slot: string
}

export interface WorkflowState {
  userId?: string
  uploadedFiles?: PersistedUploadFile[]
  uploadsComplete?: boolean
  makeupOptions?: MakeupOptions
  selectedMakeup?: MakeupSelection
  selectedPackage?: PackageSelection
  selectedSku?: SkuSelection
  orderId?: string
  paymentId?: string
  orderPaymentStatus?: string
  orderFulfillmentStatus?: string
  batchId?: string
  taskId?: string
  taskStatus?: string
  taskMessage?: string
  qualityScore?: number
  progress?: number
  promisedPhotos?: number
  deliverableCount?: number
  remainingReruns?: number
  resultUrls?: string[]
}

const STORAGE_KEY = 'lumiere.workflow.v2'

function hasWindow(): boolean {
  return typeof window !== 'undefined'
}

export function getWorkflowState(): WorkflowState {
  if (!hasWindow()) {
    return {}
  }

  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    return {}
  }

  try {
    return JSON.parse(raw) as WorkflowState
  } catch {
    window.localStorage.removeItem(STORAGE_KEY)
    return {}
  }
}

export function updateWorkflowState(patch: Partial<WorkflowState>): WorkflowState {
  const nextState = {
    ...getWorkflowState(),
    ...patch,
  }

  if (hasWindow()) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState))
  }

  return nextState
}

export function clearWorkflowState(): void {
  if (hasWindow()) {
    window.localStorage.removeItem(STORAGE_KEY)
  }
}
