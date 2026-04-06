import {
  startTransition,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  CloudUpload,
  HeartHandshake,
  Maximize2,
  ScanSearch,
  Sparkles,
  Trash2,
  User,
  X,
} from 'lucide-react'
import StepHeader from '../components/StepHeader'
import { ApiError, apiRequest, type UploadResponse } from '../lib/api'
import {
  getWorkflowState,
  updateWorkflowState,
  type PersistedUploadFile,
  type WorkflowState,
} from '../lib/workflow'
import './Upload.css'

type UploadRole = 'couple' | 'groom' | 'bride'
type UploadSlotId =
  | 'couple_full'
  | 'groom_portrait'
  | 'groom_full'
  | 'bride_portrait'
  | 'bride_full'

interface UploadSelection {
  id: string
  previewUrl: string
  sizeLabel: string
  file?: File
  source: 'local' | 'remote'
}

interface UploadSlotConfig {
  id: UploadSlotId
  role: UploadRole
  roleLabel: string
  title: string
  shortTitle: string
  description: string
  hint: string
  referenceArtwork: string
  referenceCaption: string
  referenceClassName: string
  emptyHint: string
  emptyMeta: string
  hero?: boolean
}

interface SlotReviewState {
  tone: 'pass' | 'warning'
  message: string
}

interface SubmissionReviewState {
  userId: string
  warningCount: number
}

const SLOT_CONFIGS: UploadSlotConfig[] = [
  {
    id: 'couple_full',
    role: 'couple',
    roleLabel: '双人',
    title: '双人全身合照',
    shortTitle: '双人合照',
    description: '1 张。两人站立，头脚完整，用来稳住身高差、站姿和同框比例。',
    hint: '双人全身合照已经并入标准采集，系统会优先用它判断两人的比例关系。',
    referenceArtwork: '/images/generated-1774932787165.png',
    referenceCaption: '标准锚点',
    referenceClassName: 'upload-slot__reference--couple',
    emptyHint: '上传后这里展示你们的原图预览，支持点开查看完整比例。',
    emptyMeta: '原图预览支持全图查看',
    hero: true,
  },
  {
    id: 'groom_portrait',
    role: 'groom',
    roleLabel: '新郎',
    title: '正脸半身',
    shortTitle: '新郎半身',
    description: '1 张。正脸或微侧，重点是五官清楚、脸部不要被遮挡。',
    hint: '别戴墨镜口罩，脸部不要被头发或大面积阴影遮住。',
    referenceArtwork: '/images/generated-1774932803406.png',
    referenceCaption: '半身看脸',
    referenceClassName: 'upload-slot__reference--groom-portrait',
    emptyHint: '上传后这里显示你的原图预览，支持点开看全图。',
    emptyMeta: '提交前自动优化体积，减少上传失败',
  },
  {
    id: 'groom_full',
    role: 'groom',
    roleLabel: '新郎',
    title: '全身',
    shortTitle: '新郎全身',
    description: '1 张。自然站立，头脚完整，人物主体要足够明显。',
    hint: '不要坐着，也不要裁脚，站姿要完整，别让背景把人物吃掉。',
    referenceArtwork: '/images/generated-1774932894609.png',
    referenceCaption: '全身看头脚',
    referenceClassName: 'upload-slot__reference--groom-full',
    emptyHint: '上传后这里显示你的原图预览，支持点开看完整比例。',
    emptyMeta: '提交前自动优化体积，减少上传失败',
  },
  {
    id: 'bride_portrait',
    role: 'bride',
    roleLabel: '新娘',
    title: '正脸半身',
    shortTitle: '新娘半身',
    description: '1 张。正脸或微侧，重点是五官清楚、发型不要挡脸。',
    hint: '妆面越日常越好，别重美颜，发丝也不要把眼睛和轮廓盖住。',
    referenceArtwork: '/images/generated-1774932925343.png',
    referenceCaption: '半身看脸',
    referenceClassName: 'upload-slot__reference--bride-portrait',
    emptyHint: '上传后这里显示你的原图预览，支持点开看全图。',
    emptyMeta: '提交前自动优化体积，减少上传失败',
  },
  {
    id: 'bride_full',
    role: 'bride',
    roleLabel: '新娘',
    title: '全身',
    shortTitle: '新娘全身',
    description: '1 张。自然站立，头脚完整，裙摆和站姿都要看得清楚。',
    hint: '别裁脚，也不要被裙摆、栏杆或旁人遮住完整站姿。',
    referenceArtwork: '/images/generated-1774932954197.png',
    referenceCaption: '全身看头脚',
    referenceClassName: 'upload-slot__reference--bride-full',
    emptyHint: '上传后这里显示你的原图预览，支持点开看完整比例。',
    emptyMeta: '提交前自动优化体积，减少上传失败',
  },
]

const REQUIRED_SLOT_IDS = SLOT_CONFIGS.map(slot => slot.id)

const overviewMeta = [
  { label: '当前采集', value: '5 张标准采集' },
  { label: '比例锚点', value: '双人全身合照' },
  { label: '上传策略', value: '自动优化体积' },
]

const overviewPoints = [
  '示意图只看取景，不看示例人物与穿搭。',
  '上传后直接展示你们的原图预览，可点开看完整比例。',
  '提交前自动优化上传体积，避免大图卡在传输链路。',
]

const checklistItems = [
  '上传后直接显示你们的原图预览。',
  '半身看脸，全身看头脚，合照看同框比例。',
  '提交前会自动优化体积，不用手动压图。',
]

const MAX_UPLOAD_LONG_EDGE = 2200
const TARGET_UPLOAD_BYTES = 3 * 1024 * 1024
const INITIAL_JPEG_QUALITY = 0.88
const MIN_JPEG_QUALITY = 0.52
const MIN_UPLOAD_LONG_EDGE = 1280

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(1)}MB`
  }

  return `${Math.max(1, Math.round(bytes / 1024))}KB`
}

function replaceFileExtension(filename: string, ext: string): string {
  const dotIndex = filename.lastIndexOf('.')
  if (dotIndex === -1) {
    return `${filename}${ext}`
  }

  return `${filename.slice(0, dotIndex)}${ext}`
}

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file)
    const image = new Image()

    image.onload = () => {
      URL.revokeObjectURL(objectUrl)
      resolve(image)
    }
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      reject(new Error('照片读取失败，请换一张 JPG 或 PNG'))
    }

    image.src = objectUrl
  })
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  type: string,
  quality?: number,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(blob => {
      if (!blob) {
        reject(new Error('照片处理失败，请重试'))
        return
      }

      resolve(blob)
    }, type, quality)
  })
}

async function prepareUploadFile(file: File): Promise<File> {
  if (
    file.size <= TARGET_UPLOAD_BYTES &&
    file.type === 'image/jpeg'
  ) {
    return file
  }

  const image = await loadImage(file)
  let width = image.naturalWidth
  let height = image.naturalHeight
  let quality = INITIAL_JPEG_QUALITY

  const longEdge = Math.max(width, height)
  if (longEdge > MAX_UPLOAD_LONG_EDGE) {
    const scale = MAX_UPLOAD_LONG_EDGE / longEdge
    width = Math.max(1, Math.round(width * scale))
    height = Math.max(1, Math.round(height * scale))
  }

  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('浏览器暂时无法处理照片，请换个浏览器后重试')
  }

  while (true) {
    canvas.width = width
    canvas.height = height
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, width, height)
    context.drawImage(image, 0, 0, width, height)

    const blob = await canvasToBlob(canvas, 'image/jpeg', quality)
    if (blob.size <= TARGET_UPLOAD_BYTES) {
      return new File(
        [blob],
        replaceFileExtension(file.name || 'upload.jpg', '.jpg'),
        {
          type: 'image/jpeg',
          lastModified: file.lastModified,
        },
      )
    }

    if (quality > MIN_JPEG_QUALITY) {
      quality = Math.max(MIN_JPEG_QUALITY, quality - 0.08)
      continue
    }

    const currentLongEdge = Math.max(width, height)
    if (currentLongEdge <= MIN_UPLOAD_LONG_EDGE) {
      return new File(
        [blob],
        replaceFileExtension(file.name || 'upload.jpg', '.jpg'),
        {
          type: 'image/jpeg',
          lastModified: file.lastModified,
        },
      )
    }

    const scaledLongEdge = Math.max(MIN_UPLOAD_LONG_EDGE, Math.round(currentLongEdge * 0.85))
    const scale = scaledLongEdge / currentLongEdge
    width = Math.max(1, Math.round(width * scale))
    height = Math.max(1, Math.round(height * scale))
  }
}

function buildUploadFormData(
  selections: Array<{ slot: UploadSlotConfig; file: File }>,
  includeSlots = true,
): FormData {
  const formData = new FormData()

  selections.forEach(({ slot, file }) => {
    formData.append('files', file)
    formData.append('roles', slot.role)
    if (includeSlots) {
      formData.append('slots', slot.id)
    }
  })

  return formData
}

function revokeSelection(selection?: UploadSelection): void {
  if (selection?.source === 'local') {
    URL.revokeObjectURL(selection.previewUrl)
  }
}

function slotIcon(role: UploadRole) {
  return role === 'couple' ? HeartHandshake : User
}

function isUploadSlotId(value: string): value is UploadSlotId {
  return SLOT_CONFIGS.some(slot => slot.id === value)
}

function buildSelectionsFromWorkflow(
  workflow: WorkflowState,
): Partial<Record<UploadSlotId, UploadSelection>> {
  const nextSelections: Partial<Record<UploadSlotId, UploadSelection>> = {}

  ;(workflow.uploadedFiles || []).forEach(file => {
    if (!isUploadSlotId(file.slot)) {
      return
    }

    nextSelections[file.slot] = {
      id: file.id,
      previewUrl: file.url,
      sizeLabel: '已上传',
      source: 'remote',
    }
  })

  return nextSelections
}

function mergeUploadedFiles(
  existing: PersistedUploadFile[],
  incoming: PersistedUploadFile[],
): PersistedUploadFile[] {
  const bySlot = new Map(existing.map(file => [file.slot, file]))
  incoming.forEach(file => {
    bySlot.set(file.slot, file)
  })
  return Array.from(bySlot.values())
}

export default function Upload() {
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const [selections, setSelections] = useState<Partial<Record<UploadSlotId, UploadSelection>>>(() => buildSelectionsFromWorkflow(workflow))
  const [slotReviews, setSlotReviews] = useState<Partial<Record<UploadSlotId, SlotReviewState>>>({})
  const [submissionReview, setSubmissionReview] = useState<SubmissionReviewState | null>(null)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isPreparingUpload, setIsPreparingUpload] = useState(false)
  const [previewSlotId, setPreviewSlotId] = useState<UploadSlotId | null>(null)
  const selectionsRef = useRef<Partial<Record<UploadSlotId, UploadSelection>>>({})

  useEffect(() => {
    selectionsRef.current = selections
  }, [selections])

  useEffect(() => {
    return () => {
      Object.values(selectionsRef.current).forEach(selection => revokeSelection(selection))
    }
  }, [])

  useEffect(() => {
    if (!previewSlotId) {
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPreviewSlotId(null)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [previewSlotId])

  const completedCount = useMemo(
    () => SLOT_CONFIGS.filter(slot => selections[slot.id]).length,
    [selections],
  )

  const previewSelection = previewSlotId ? selections[previewSlotId] : undefined
  const previewSlot = previewSlotId ? SLOT_CONFIGS.find(slot => slot.id === previewSlotId) : undefined
  const coupleSlot = SLOT_CONFIGS.find(slot => slot.hero)
  const portraitSlots = SLOT_CONFIGS.filter(slot => !slot.hero)

  const resetServerReview = () => {
    setSlotReviews({})
    setSubmissionReview(null)
  }

  const proceedToMakeup = (userId: string, preserveDownstream = false) => {
    updateWorkflowState(
      preserveDownstream
        ? {
            userId,
            uploadsComplete: true,
          }
        : {
            userId,
            uploadsComplete: true,
            makeupOptions: undefined,
            selectedMakeup: undefined,
            selectedMakeupReferences: undefined,
            orderId: undefined,
            paymentId: undefined,
            orderPaymentStatus: undefined,
            orderFulfillmentStatus: undefined,
            batchId: undefined,
            taskId: undefined,
            taskStatus: undefined,
            taskMessage: undefined,
            qualityScore: undefined,
            progress: undefined,
            promisedPhotos: undefined,
            deliverableCount: undefined,
            remainingReruns: undefined,
            resultUrls: undefined,
          },
    )

    startTransition(() => {
      navigate('/makeup')
    })
  }

  const replaceSelection = async (slot: UploadSlotConfig, fileList: FileList | null) => {
    const file = fileList?.[0]
    if (!file) {
      return
    }

    if (!file.type.startsWith('image/')) {
      setError('只能上传图片文件，请重新选择 JPG 或 PNG。')
      return
    }

    setError('')
    resetServerReview()
    const selection: UploadSelection = {
      id: `${slot.id}-${crypto.randomUUID()}`,
      file,
      previewUrl: URL.createObjectURL(file),
      sizeLabel: formatFileSize(file.size),
      source: 'local',
    }

    setSelections(previous => {
      revokeSelection(previous[slot.id])
      return {
        ...previous,
        [slot.id]: selection,
      }
    })
  }

  const handleDrop = (slot: UploadSlotConfig) => (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    void replaceSelection(slot, event.dataTransfer.files)
  }

  const handleFileSelect = (slot: UploadSlotConfig) => (event: ChangeEvent<HTMLInputElement>) => {
    void replaceSelection(slot, event.target.files)
    event.target.value = ''
  }

  const handleRemove = (slotId: UploadSlotId) => {
    resetServerReview()
    setSelections(previous => {
      revokeSelection(previous[slotId])
      const next = { ...previous }
      delete next[slotId]
      return next
    })

    if (previewSlotId === slotId) {
      setPreviewSlotId(null)
    }

    updateWorkflowState({
      uploadedFiles: (getWorkflowState().uploadedFiles || []).filter(file => file.slot !== slotId),
      uploadsComplete: false,
      makeupOptions: undefined,
      selectedMakeup: undefined,
      selectedMakeupReferences: undefined,
      orderId: undefined,
      paymentId: undefined,
      orderPaymentStatus: undefined,
      orderFulfillmentStatus: undefined,
      batchId: undefined,
      taskId: undefined,
      taskStatus: undefined,
      taskMessage: undefined,
      qualityScore: undefined,
      progress: undefined,
      promisedPhotos: undefined,
      deliverableCount: undefined,
      remainingReruns: undefined,
      resultUrls: undefined,
    })
  }

  const submitUploads = async () => {
    const missingSlots = REQUIRED_SLOT_IDS.filter(slotId => !selections[slotId])
    if (missingSlots.length > 0) {
      const missingLabels = SLOT_CONFIGS.filter(slot => missingSlots.includes(slot.id)).map(slot => slot.shortTitle)
      setError(`还差 ${missingLabels.join('、')}，补齐后再继续。`)
      return
    }

    setError('')
    setIsSubmitting(true)
    setIsPreparingUpload(true)
    resetServerReview()

    try {
      const pendingSelections = SLOT_CONFIGS.flatMap(slot => {
        const selection = selections[slot.id]
        if (!selection?.file) {
          return []
        }

        return [{ slot, file: selection.file }]
      })

      if (pendingSelections.length === 0) {
        const persistedUserId = workflow.userId || submissionReview?.userId
        if (!persistedUserId) {
          throw new Error('未找到已上传档案，请重新提交照片')
        }

        proceedToMakeup(persistedUserId, true)
        return
      }

      const preparedSelections = await Promise.all(
        pendingSelections.map(async ({ slot, file }) => {
          return {
            slot,
            file: await prepareUploadFile(file),
          }
        }),
      )

      setIsPreparingUpload(false)
      let payload: UploadResponse
      try {
        payload = await apiRequest<UploadResponse>('/api/upload', {
          method: 'POST',
          body: buildUploadFormData(preparedSelections),
        })
      } catch (submitError) {
        if (!(submitError instanceof ApiError) || submitError.status !== 413) {
          throw submitError
        }

        const fallbackFiles = []
        let fallbackPayload: UploadResponse | null = null

        for (const preparedSelection of preparedSelections) {
          fallbackPayload = await apiRequest<UploadResponse>('/api/upload', {
            method: 'POST',
            body: buildUploadFormData([preparedSelection]),
          })
          fallbackFiles.push(...fallbackPayload.files)
        }

        if (!fallbackPayload) {
          throw submitError
        }

        payload = {
          user_id: fallbackPayload.user_id,
          session_token: fallbackPayload.session_token,
          files: fallbackFiles,
          validation: null,
        }
      }

      const nextSlotReviews: Partial<Record<UploadSlotId, SlotReviewState>> = {}
      const persistedFiles = mergeUploadedFiles(
        getWorkflowState().uploadedFiles || [],
        payload.files.map(file => ({
          id: file.id,
          filename: file.filename,
          url: file.url,
          role: file.role,
          slot: file.slot,
        })),
      )
      const persistedSlots = new Set(
        persistedFiles
          .map(file => file.slot)
          .filter((slot): slot is UploadSlotId => isUploadSlotId(slot)),
      )
      const uploadsComplete = REQUIRED_SLOT_IDS.every(slotId => persistedSlots.has(slotId))

      payload.files.forEach(file => {
        if (!isUploadSlotId(file.slot)) {
          return
        }

        nextSlotReviews[file.slot] = {
          tone: 'pass',
          message: 'AI 预检通过',
        }
      })

      const warningIssues = payload.validation?.issues.filter(issue => issue.level === 'warning') ?? []
      warningIssues.forEach(issue => {
        if (!isUploadSlotId(issue.slot)) {
          return
        }

        nextSlotReviews[issue.slot] = {
          tone: 'warning',
          message: issue.message,
        }
      })

      setSlotReviews(nextSlotReviews)
      updateWorkflowState({
        userId: payload.user_id,
        uploadedFiles: persistedFiles,
        uploadsComplete,
      })

      if (warningIssues.length > 0) {
        setSubmissionReview({
          userId: payload.user_id,
          warningCount: warningIssues.length,
        })
        return
      }

      proceedToMakeup(payload.user_id)
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '上传失败，请稍后重试')
    } finally {
      setIsPreparingUpload(false)
      setIsSubmitting(false)
    }
  }

  const renderReview = (slotId: UploadSlotId) => {
    const review = slotReviews[slotId]
    if (!review) {
      return null
    }

    return (
      <div className={`upload-slot__review upload-slot__review--${review.tone}`}>
        {review.tone === 'warning' ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
        <span>{review.message}</span>
      </div>
    )
  }

  const renderFilledDropzone = (slot: UploadSlotConfig, selection: UploadSelection) => (
    <div className={`upload-slot__filled ${slot.hero ? 'upload-slot__filled--hero' : ''}`}>
      <button
        type="button"
        className={`upload-slot__preview ${slot.hero ? 'upload-slot__preview--hero' : ''}`}
        onClick={() => setPreviewSlotId(slot.id)}
      >
        <img src={selection.previewUrl} alt={`${slot.title}预览`} />
        <span className="upload-slot__preview-cta">
          <Maximize2 size={14} />
          查看原图
        </span>
      </button>

      <div className="upload-slot__actions">
        <label className="upload-slot__button">
          替换照片
          <input type="file" accept="image/*" hidden onChange={handleFileSelect(slot)} />
        </label>
        <button type="button" className="upload-slot__button upload-slot__button--ghost" onClick={() => handleRemove(slot.id)}>
          <Trash2 size={14} />
          移除
        </button>
      </div>

      <span className="upload-slot__meta">已选择 {selection.sizeLabel}</span>
    </div>
  )

  return (
    <div className="upload-page">
      <StepHeader current={3} onClose={() => navigate('/')} />

      <main className="upload-main">
        <section className="upload-title">
          <span className="upload-title__badge">标准采集</span>
          <h1>先把你们的 5 张原图摆对</h1>
          <p>
            先上传 5 张原图：新郎半身 / 全身、新娘半身 / 全身、双人全身合照。示意图只看取景与比例，正式流程支持点开看原图。
          </p>
        </section>

        <section className="upload-brief">
          <div className="upload-brief__copy">
            <span className="upload-brief__eyebrow">当前标准</span>
            <h2>5 张标准采集，双人合照并入必传</h2>
            <p>
              两人各 2 张负责保五官与体态，双人全身合照负责稳住身高差、站姿和同框比例；前后端都按 5 张标准采集执行。
            </p>
          </div>

          <div className="upload-brief__meta">
            {overviewMeta.map(item => (
              <div key={item.label} className="upload-brief__meta-card">
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>

          <div className="upload-brief__points">
            <div className="upload-brief__point">
              <Sparkles size={18} />
              <span>{overviewPoints[0]}</span>
            </div>
            <div className="upload-brief__point">
              <ScanSearch size={18} />
              <span>{overviewPoints[1]}</span>
            </div>
            <div className="upload-brief__point">
              <CheckCircle2 size={18} />
              <span>{overviewPoints[2]}</span>
            </div>
          </div>

          <div className="upload-brief__footer">
            <span>半身看脸，全身看头脚，合照看两人比例。</span>
            <span>{completedCount} / {SLOT_CONFIGS.length} 坑位已放入</span>
          </div>
        </section>

        {coupleSlot ? (
          <section className="upload-slot upload-slot--hero">
            <div className="upload-slot__hero-header">
              <div className="upload-slot__hero-title">
                <span className="upload-slot__role">{coupleSlot.roleLabel}</span>
                {(() => {
                  const Icon = slotIcon(coupleSlot.role)
                  return <Icon size={18} color="var(--accent-gold)" />
                })()}
                <h2>{coupleSlot.title}</h2>
              </div>
              <span className="upload-slot__badge">标准锚点</span>
            </div>

            <div className="upload-slot__hero-grid">
              <div className={`upload-slot__reference upload-slot__reference--hero ${coupleSlot.referenceClassName}`}>
                <img src={coupleSlot.referenceArtwork} alt={coupleSlot.title} loading="lazy" decoding="async" />
                <span className="upload-slot__reference-chip">{coupleSlot.referenceCaption}</span>
              </div>

              <div
                className="upload-slot__dropzone upload-slot__dropzone--hero"
                onDragOver={event => event.preventDefault()}
                onDrop={handleDrop(coupleSlot)}
              >
                {selections[coupleSlot.id]
                  ? renderFilledDropzone(coupleSlot, selections[coupleSlot.id] as UploadSelection)
                  : (
            <>
              <CloudUpload size={34} color="var(--text-muted)" />
              <p>{coupleSlot.emptyHint}</p>
                      <label className="upload-slot__button">
                        上传双人合照
                        <input type="file" accept="image/*" hidden onChange={handleFileSelect(coupleSlot)} />
                      </label>
                      <span className="upload-slot__meta">{coupleSlot.emptyMeta}</span>
                    </>
                    )}
              </div>
            </div>

            <p className="upload-slot__description upload-slot__description--hero">{coupleSlot.description}</p>
            {renderReview(coupleSlot.id)}
            <p className="upload-slot__hint">{coupleSlot.hint}</p>
          </section>
        ) : null}

        <section className="upload-required">
          <div className="upload-required__head">
            <h2>另外 4 张单人位</h2>
            <p>半身看脸，全身看头脚；上传后可点开你们的原图看完整比例。</p>
          </div>

          <div className="upload-grid">
            {portraitSlots.map(slot => (
              <article key={slot.id} className="upload-slot">
                <div className="upload-slot__card-header">
                  <div className="upload-slot__card-title">
                    <span className="upload-slot__role">{slot.roleLabel}</span>
                    <h3>{slot.title}</h3>
                  </div>
                  <span className="upload-slot__badge">必传</span>
                </div>

                <div className={`upload-slot__reference ${slot.referenceClassName}`}>
                  <img src={slot.referenceArtwork} alt={slot.title} loading="lazy" decoding="async" />
                  <span className="upload-slot__reference-chip">{slot.referenceCaption}</span>
                </div>

                <p className="upload-slot__description">{slot.description}</p>

                <div
                  className="upload-slot__dropzone upload-slot__dropzone--compact"
                  onDragOver={event => event.preventDefault()}
                  onDrop={handleDrop(slot)}
                >
                  {selections[slot.id]
                    ? renderFilledDropzone(slot, selections[slot.id] as UploadSelection)
                    : (
                      <>
                        <CloudUpload size={28} color="var(--text-muted)" />
                        <p>{slot.emptyHint}</p>
                        <label className="upload-slot__button">
                          上传照片
                          <input type="file" accept="image/*" hidden onChange={handleFileSelect(slot)} />
                        </label>
                        <span className="upload-slot__meta">{slot.emptyMeta}</span>
                      </>
                    )}
                </div>

                {renderReview(slot.id)}
                <p className="upload-slot__hint">{slot.hint}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="upload-checklist">
          {checklistItems.map(item => (
            <div key={item} className="upload-checklist__item">
              <CheckCircle2 size={18} color="var(--accent-gold)" />
              <span>{item}</span>
            </div>
          ))}
        </section>

        {submissionReview ? (
          <section className="upload-review upload-review--warning">
            <div className="upload-review__icon">
              <AlertTriangle size={18} />
            </div>
            <div className="upload-review__body">
              <h2>AI 预检完成，有 {submissionReview.warningCount} 处建议再看一眼</h2>
              <p>这批照片已经可以继续试妆，也可以先替换后再检查。</p>
            </div>
          </section>
        ) : null}

        {error ? <div className="upload-feedback upload-feedback--error">{error}</div> : null}

        <div className="upload-bottom">
          <button
            className="btn btn--gold"
            onClick={submissionReview ? () => proceedToMakeup(submissionReview.userId) : submitUploads}
            disabled={isSubmitting}
          >
            {isSubmitting
              ? isPreparingUpload
                ? '正在优化照片...'
                : '正在建立档案...'
              : submissionReview
                ? '接受提示，继续 AI 试妆'
                : '下一步：AI 试妆'}
          </button>
        </div>
      </main>

      {previewSelection && previewSlot ? (
        <div className="upload-lightbox" role="dialog" aria-modal="true" aria-label={`${previewSlot.title}原图预览`} onClick={() => setPreviewSlotId(null)}>
          <div className="upload-lightbox__dialog" onClick={event => event.stopPropagation()}>
            <button type="button" className="upload-lightbox__close" onClick={() => setPreviewSlotId(null)} aria-label="关闭预览">
              <X size={18} />
            </button>
            <div className="upload-lightbox__head">
              <div>
                <span>{previewSlot.roleLabel}</span>
                <h2>{previewSlot.title}</h2>
              </div>
              <strong>{previewSelection.sizeLabel}</strong>
            </div>
            <img src={previewSelection.previewUrl} alt={`${previewSlot.title}原图`} />
          </div>
        </div>
      ) : null}
    </div>
  )
}
