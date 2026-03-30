import {
  startTransition,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { CloudUpload, HeartHandshake, Trash2, User } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import type { UploadResponse } from '../lib/api'
import { updateWorkflowState } from '../lib/workflow'
import './Upload.css'

type UploadRole = 'couple' | 'groom' | 'bride'

interface UploadSelection {
  id: string
  file: File
  previewUrl: string
}

function makeSelection(file: File): UploadSelection {
  return {
    id: `${file.name}-${crypto.randomUUID()}`,
    file,
    previewUrl: URL.createObjectURL(file),
  }
}

function revokeSelections(items: UploadSelection[]): void {
  items.forEach(item => {
    URL.revokeObjectURL(item.previewUrl)
  })
}

export default function Upload() {
  const navigate = useNavigate()
  const [coupleFiles, setCoupleFiles] = useState<UploadSelection[]>([])
  const [groomFiles, setGroomFiles] = useState<UploadSelection[]>([])
  const [brideFiles, setBrideFiles] = useState<UploadSelection[]>([])
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const selectionsRef = useRef<UploadSelection[]>([])

  useEffect(() => {
    selectionsRef.current = [...coupleFiles, ...groomFiles, ...brideFiles]
  }, [brideFiles, coupleFiles, groomFiles])

  useEffect(() => {
    return () => {
      revokeSelections(selectionsRef.current)
    }
  }, [])

  const appendFiles = (role: UploadRole, fileList: FileList | null) => {
    if (!fileList) {
      return
    }

    const imageFiles = Array.from(fileList).filter(file => file.type.startsWith('image/'))
    if (!imageFiles.length) {
      return
    }

    setError('')

    if (role === 'couple') {
      setCoupleFiles(previous => {
        revokeSelections(previous)
        return [makeSelection(imageFiles[0])]
      })
      return
    }

    const setter = role === 'groom' ? setGroomFiles : setBrideFiles
    setter(previous => {
      const remaining = Math.max(10 - previous.length, 0)
      if (!remaining) {
        return previous
      }
      return [...previous, ...imageFiles.slice(0, remaining).map(makeSelection)]
    })
  }

  const handleDrop = (role: UploadRole) => (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    appendFiles(role, event.dataTransfer.files)
  }

  const handleFileSelect = (role: UploadRole) => (event: ChangeEvent<HTMLInputElement>) => {
    appendFiles(role, event.target.files)
    event.target.value = ''
  }

  const handleRemove = (role: UploadRole, id: string) => {
    const setter = role === 'couple' ? setCoupleFiles : role === 'groom' ? setGroomFiles : setBrideFiles
    setter(previous => {
      const next = previous.filter(item => item.id !== id)
      const removed = previous.find(item => item.id === id)
      if (removed) {
        URL.revokeObjectURL(removed.previewUrl)
      }
      return next
    })
  }

  const submitUploads = async () => {
    if (!groomFiles.length || !brideFiles.length) {
      setError('请至少分别上传 1 张新郎与新娘照片，双人合照为强提示但非必填。')
      return
    }

    setError('')
    setIsSubmitting(true)

    try {
      const formData = new FormData()
      const orderedFiles = [
        ...coupleFiles.map(item => ({ ...item, role: 'couple' as const })),
        ...groomFiles.map(item => ({ ...item, role: 'groom' as const })),
        ...brideFiles.map(item => ({ ...item, role: 'bride' as const })),
      ]

      orderedFiles.forEach(item => {
        formData.append('files', item.file)
        formData.append('roles', item.role)
      })

      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
        credentials: 'include',
      })

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null
        throw new Error(payload?.detail || '上传失败，请稍后重试')
      }

      const payload = (await response.json()) as UploadResponse
      updateWorkflowState({
        userId: payload.user_id,
        uploadsComplete: true,
        makeupOptions: undefined,
        selectedMakeup: undefined,
        selectedPackage: undefined,
        selectedSku: undefined,
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

      startTransition(() => {
        navigate('/makeup')
      })
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '上传失败，请稍后重试')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="upload-page">
      <StepHeader current={1} onClose={() => navigate('/')} />
      <main className="upload-main">
        <div className="upload-title">
          <h1>欢迎来到您的私人数字影棚</h1>
          <p>先放一张双人全身日常合照，再分别上传新郎与新娘个人照，系统会优先把合照作为双人比例弱锚点。</p>
        </div>

        <div className="upload-highlight">
          <span className="upload-highlight__badge">比例增强</span>
          <p>建议上传 1 张双人全身日常合照，可显著提升双人照的身高差与体型对比还原度。没有合照也不会阻断后续流程。</p>
        </div>

        <section className="upload-cards upload-cards--single">
          <div className="upload-card upload-card--couple">
            <div className="upload-card__label">
              <HeartHandshake size={20} color="var(--accent-gold)" />
              <span>双人合照</span>
            </div>
            <div
              className="upload-card__dropzone upload-card__dropzone--compact"
              onDragOver={event => event.preventDefault()}
              onDrop={handleDrop('couple')}
            >
              {coupleFiles.length > 0 ? (
                <div className="upload-card__previews upload-card__previews--hero">
                  {coupleFiles.map(item => (
                    <div key={item.id} className="upload-card__thumb upload-card__thumb--hero">
                      <img src={item.previewUrl} alt="双人合照预览" />
                      <button type="button" onClick={() => handleRemove('couple', item.id)} aria-label="移除双人合照">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <CloudUpload size={44} color="var(--text-muted)" />
                  <p>拖拽双人全身日常照到这里<br />或点击上传 1 张合照</p>
                </>
              )}
              <label className="upload-card__btn">
                选择合照
                <input type="file" accept="image/*" hidden onChange={handleFileSelect('couple')} />
              </label>
            </div>
            <span className="upload-card__hint">
              最多 1 张，建议自然站姿、全身入镜、无遮挡
            </span>
          </div>
        </section>

        <div className="upload-cards">
          {[
            { role: 'groom' as const, label: '新郎', files: groomFiles },
            { role: 'bride' as const, label: '新娘', files: brideFiles },
          ].map(({ role, label, files }) => (
            <div key={label} className="upload-card">
              <div className="upload-card__label">
                <User size={20} color="var(--accent-gold)" />
                <span>{label}</span>
              </div>
              <div
                className="upload-card__dropzone"
                onDragOver={event => event.preventDefault()}
                onDrop={handleDrop(role)}
              >
                {files.length > 0 ? (
                  <div className="upload-card__previews">
                    {files.map(item => (
                      <div key={item.id} className="upload-card__thumb">
                        <img src={item.previewUrl} alt={`${label}照片预览`} />
                        <button type="button" onClick={() => handleRemove(role, item.id)} aria-label={`移除${label}照片`}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <>
                    <CloudUpload size={48} color="var(--text-muted)" />
                    <p>拖拽照片到这里<br />或点击上传</p>
                  </>
                )}
                <label className="upload-card__btn">
                  选择文件
                  <input type="file" accept="image/*" multiple hidden onChange={handleFileSelect(role)} />
                </label>
              </div>
              <span className="upload-card__hint">
                支持 JPG/PNG，单张不超过 10MB<br />建议 5-10 张，覆盖正面、侧面、半身与全身
              </span>
            </div>
          ))}
        </div>

        {error ? <div className="upload-feedback upload-feedback--error">{error}</div> : null}

        <div className="upload-bottom">
          <button className="btn btn--gold" onClick={submitUploads} disabled={isSubmitting}>
            {isSubmitting ? '正在建立档案...' : '下一步：AI试妆'}
          </button>
        </div>
      </main>
    </div>
  )
}
