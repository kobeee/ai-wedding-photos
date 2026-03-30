import { startTransition, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, User } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import { apiRequest, type MakeupResponse } from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './Makeup.css'

const groomStyles = [
  { id: 'natural', name: '素颜质感', desc: '保留自然状态\n真实清透' },
  { id: 'refined', name: '精致新郎妆', desc: '轻度修饰提亮\n干净利落' },
  { id: 'sculpt', name: '骨相微调', desc: '面部轮廓优化\n杂志封面感' },
]

const brideStyles = [
  { id: 'natural', name: '素颜质感', desc: '清透自然\n原生美感' },
  { id: 'refined', name: '精致新娘妆', desc: '柔光美肌\n优雅端庄' },
  { id: 'sculpt', name: '骨相微调', desc: '面部轮廓精修\n高级感拉满' },
]

const FALLBACK_IMAGES: StyleImageState = {
  groom: [
    '/images/generated-1773759812646.png',
    '/images/generated-1773759932888.png',
    '/images/generated-1773759970779.png',
  ],
  bride: [
    '/images/generated-1773760053899.png',
    '/images/generated-1773760091146.png',
    '/images/generated-1773760190993.png',
  ],
}

interface StyleImageState {
  groom: string[]
  bride: string[]
}

const EMPTY_IMAGES: StyleImageState = {
  groom: [],
  bride: [],
}

async function requestMakeupPreview(
  userId: string,
  gender: 'male' | 'female',
): Promise<MakeupResponse> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), 20000)

  try {
    return await apiRequest<MakeupResponse>('/api/makeup/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_id: userId,
        gender,
        style: 'natural',
      }),
      signal: controller.signal,
    })
  } finally {
    window.clearTimeout(timeoutId)
  }
}

export default function Makeup() {
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const [groomStyle, setGroomStyle] = useState(workflow.selectedMakeup?.groom || 'natural')
  const [brideStyle, setBrideStyle] = useState(workflow.selectedMakeup?.bride || 'refined')
  const [images, setImages] = useState<StyleImageState>(workflow.makeupOptions || EMPTY_IMAGES)
  const [isLoading, setIsLoading] = useState(!workflow.makeupOptions)
  const [error, setError] = useState('')
  const [retryNonce, setRetryNonce] = useState(0)

  useEffect(() => {
    if (!workflow.userId || !workflow.uploadsComplete) {
      startTransition(() => {
        navigate('/upload')
      })
      return
    }

    if (workflow.makeupOptions) {
      return
    }

    let cancelled = false
    const userId = workflow.userId
    async function loadMakeupPreviews() {
      setIsLoading(true)
      setError('')

      try {
        const [groomResult, brideResult] = await Promise.allSettled([
          requestMakeupPreview(userId, 'male'),
          requestMakeupPreview(userId, 'female'),
        ])

        if (cancelled) {
          return
        }

        const nextImages = {
          groom: groomResult.status === 'fulfilled' ? groomResult.value.images : FALLBACK_IMAGES.groom,
          bride: brideResult.status === 'fulfilled' ? brideResult.value.images : FALLBACK_IMAGES.bride,
        }
        setImages(nextImages)
        updateWorkflowState({
          makeupOptions: nextImages,
        })
        if (groomResult.status === 'rejected' || brideResult.status === 'rejected') {
          setError('AI 试妆当前响应较慢，已切换为样片预览，不影响正式生成。')
        }
      } catch (loadError) {
        if (cancelled) {
          return
        }
        setImages(FALLBACK_IMAGES)
        setError(loadError instanceof Error ? `${loadError.message}，已切换为样片预览。` : '试妆生成失败，已切换为样片预览。')
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadMakeupPreviews()

    return () => {
      cancelled = true
    }
  }, [navigate, retryNonce, workflow.makeupOptions, workflow.uploadsComplete, workflow.userId])

  const isReady = images.groom.length === groomStyles.length && images.bride.length === brideStyles.length

  const handleContinue = () => {
    updateWorkflowState({
      selectedMakeup: {
        groom: groomStyle,
        bride: brideStyle,
      },
    })

    startTransition(() => {
      navigate('/package')
    })
  }

  const handleRetry = () => {
    updateWorkflowState({
      makeupOptions: undefined,
    })
    setImages(EMPTY_IMAGES)
    setIsLoading(true)
    setError('')
    setRetryNonce(previous => previous + 1)
  }

  return (
    <div className="makeup-page">
      <StepHeader current={2} onClose={() => navigate('/')} />
      <main className="makeup-main">
        <div className="makeup-title">
          <h1>哪一个是您今天想要的状态？</h1>
          <p>系统会基于已上传照片，分别生成新郎与新娘的三组 AI 试妆预览。</p>
        </div>

        {error ? (
          <div className="makeup-feedback makeup-feedback--error">
            <span>{error}</span>
            <button type="button" onClick={handleRetry}>
              <RefreshCw size={14} />
              重新生成
            </button>
          </div>
        ) : null}

        <div className="makeup-section">
          <div className="makeup-section__header">
            <User size={18} color="var(--accent-gold)" />
            <span>新郎妆造</span>
          </div>
          <div className="makeup-cards">
            {groomStyles.map((style, index) => {
              const imageUrl = images.groom[index]
              const isSelected = groomStyle === style.id

              return (
                <button
                  key={style.id}
                  type="button"
                  className={`makeup-card ${isSelected ? 'makeup-card--selected' : ''} ${!imageUrl ? 'makeup-card--loading' : ''}`}
                  onClick={() => setGroomStyle(style.id)}
                  disabled={!imageUrl}
                >
                  <div
                    className="makeup-card__img"
                    style={imageUrl ? { backgroundImage: `url(${imageUrl})` } : undefined}
                  >
                    {!imageUrl ? <span>正在生成预览...</span> : null}
                  </div>
                  <div className="makeup-card__info">
                    <h3>{style.name}</h3>
                    <p>{style.desc}</p>
                    {isSelected && imageUrl ? <span className="makeup-card__badge">已选择</span> : null}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        <div className="makeup-section">
          <div className="makeup-section__header">
            <User size={18} color="var(--accent-gold)" />
            <span>新娘妆造</span>
          </div>
          <div className="makeup-cards">
            {brideStyles.map((style, index) => {
              const imageUrl = images.bride[index]
              const isSelected = brideStyle === style.id

              return (
                <button
                  key={style.id}
                  type="button"
                  className={`makeup-card ${isSelected ? 'makeup-card--selected' : ''} ${!imageUrl ? 'makeup-card--loading' : ''}`}
                  onClick={() => setBrideStyle(style.id)}
                  disabled={!imageUrl}
                >
                  <div
                    className="makeup-card__img"
                    style={imageUrl ? { backgroundImage: `url(${imageUrl})` } : undefined}
                  >
                    {!imageUrl ? <span>正在生成预览...</span> : null}
                  </div>
                  <div className="makeup-card__info">
                    <h3>{style.name}</h3>
                    <p>{style.desc}</p>
                    {isSelected && imageUrl ? <span className="makeup-card__badge">已选择</span> : null}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        <div className="makeup-bottom">
          <button className="btn btn--outline-light" onClick={() => navigate('/upload')}>上一步</button>
          <button className="btn btn--gold" onClick={handleContinue} disabled={isLoading || !isReady}>
            {isLoading ? '正在生成试妆...' : '下一步：选择套餐'}
          </button>
        </div>
      </main>
    </div>
  )
}
