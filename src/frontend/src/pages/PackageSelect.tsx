import { startTransition, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Camera, Sparkles } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import {
  getPackageCard,
  packageCards,
  packageTabs,
  sceneOptions,
  wardrobeOptions,
  type DirectionOption,
  type PackageCard,
  type PackageTab,
} from '../data/packages'
import { apiRequest, type PackageInfo } from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './PackageSelect.css'

const tabWeights: Record<PackageTab, string[]> = {
  中式: ['chinese-classic'],
  西式: ['minimal', 'western-romantic', 'iceland', 'french'],
  旅拍: ['iceland', 'french', 'travel-destination', 'western-romantic'],
  夜景: ['chinese-classic', 'french'],
  影棚: ['minimal'],
  幻境: ['iceland', 'western-romantic'],
}

function scoreCard(
  card: PackageCard,
  activeTab: PackageTab,
  wardrobe: DirectionOption | undefined,
  scene: DirectionOption | undefined,
): number {
  let score = 0

  if (tabWeights[activeTab].includes(card.id)) {
    score += 2
  }

  if (wardrobe?.matches.includes(card.id)) {
    score += 3
  }

  if (scene?.matches.includes(card.id)) {
    score += 3
  }

  return score
}

export default function PackageSelect() {
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const [remotePackages, setRemotePackages] = useState<PackageInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadNotice, setLoadNotice] = useState('')
  const [actionError, setActionError] = useState('')
  const [activeTab, setActiveTab] = useState<PackageTab>('西式')
  const [selectedWardrobeId, setSelectedWardrobeId] = useState(wardrobeOptions[0]?.id ?? '')
  const [selectedSceneId, setSelectedSceneId] = useState(sceneOptions[0]?.id ?? '')
  const [selected, setSelected] = useState<string | null>(workflow.selectedPackage?.id || null)

  useEffect(() => {
    let cancelled = false

    async function loadPackages() {
      try {
        const payload = await apiRequest<PackageInfo[]>('/api/packages')
        if (cancelled) {
          return
        }

        setRemotePackages(payload)
        setLoadNotice('')
      } catch (loadError) {
        if (cancelled) {
          return
        }

        const fallbackNotice = loadError instanceof Error && loadError.message.startsWith('Request failed with status')
          ? '样片目录暂时离线，已切换本地样片目录。'
          : loadError instanceof Error
            ? `${loadError.message}，已切换本地样片目录。`
            : '套餐目录加载失败，已切换本地样片目录。'

        setLoadNotice(fallbackNotice)
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadPackages()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!workflow.userId || !workflow.uploadsComplete) {
      startTransition(() => {
        navigate('/upload')
      })
    }
  }, [navigate, workflow.uploadsComplete, workflow.userId])

  const availableCards = useMemo(() => {
    if (remotePackages.length === 0) {
      return packageCards
    }

    const allowedIds = new Set(remotePackages.map(item => item.id))
    const nextCards = packageCards.filter(item => allowedIds.has(item.id))
    return nextCards.length > 0 ? nextCards : packageCards
  }, [remotePackages])

  const selectedWardrobe = useMemo(
    () => wardrobeOptions.find(item => item.id === selectedWardrobeId),
    [selectedWardrobeId],
  )

  const selectedScene = useMemo(
    () => sceneOptions.find(item => item.id === selectedSceneId),
    [selectedSceneId],
  )

  const rankedCards = useMemo(() => {
    const indexMap = new Map(packageCards.map((item, index) => [item.id, index]))

    return [...availableCards].sort((left, right) => {
      const scoreDelta = scoreCard(right, activeTab, selectedWardrobe, selectedScene)
        - scoreCard(left, activeTab, selectedWardrobe, selectedScene)

      if (scoreDelta !== 0) {
        return scoreDelta
      }

      return (indexMap.get(left.id) ?? 0) - (indexMap.get(right.id) ?? 0)
    })
  }, [activeTab, availableCards, selectedScene, selectedWardrobe])

  const recommendedCard = rankedCards[0] ?? null

  const selectedCard = useMemo(() => {
    if (!selected) {
      return null
    }

    return rankedCards.find(item => item.id === selected) ?? getPackageCard(selected)
  }, [rankedCards, selected])

  if (!workflow.userId || !workflow.uploadsComplete) {
    return null
  }

  const handleContinue = () => {
    if (!selectedCard) {
      setActionError('先选一套你们真正想拍的语境，再继续下单。')
      return
    }

    setActionError('')
    updateWorkflowState({
      selectedPackage: {
        id: selectedCard.id,
        name: selectedCard.name,
        tag: selectedCard.tag,
      },
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
      navigate('/checkout')
    })
  }

  return (
    <div className="pkg-page">
      <StepHeader current={3} onClose={() => navigate('/')} />
      <main className="pkg-main">
        <section className="pkg-title">
          <h1>先定体系，再定服饰与场景</h1>
          <p>先选婚礼语境，再筛服饰与取景，最后再看推荐样片。</p>
        </section>

        <section className="pkg-tabs" aria-label="体系偏好">
          {packageTabs.map(tab => (
            <button
              key={tab}
              type="button"
              className={`pkg-tab ${activeTab === tab ? 'pkg-tab--active' : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </section>

        <section className="pkg-panel">
          <div className="pkg-panel__top">
            <div>
              <span className="pkg-panel__eyebrow">产品结构</span>
              <p>体系偏好 → 服饰方向 → 场景取景</p>
            </div>
            <span className="pkg-panel__status">
              {isLoading ? '正在同步样片目录...' : loadNotice || `${availableCards.length} 套核心方案已就绪`}
            </span>
          </div>

          <div className="pkg-panel__stage">
            <span className="pkg-panel__label">服饰方向</span>
            <div className="pkg-panel__chips">
              {wardrobeOptions.map(option => (
                <button
                  key={option.id}
                  type="button"
                  className={`pkg-chip ${selectedWardrobeId === option.id ? 'pkg-chip--active' : ''}`}
                  onClick={() => setSelectedWardrobeId(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="pkg-panel__stage">
            <span className="pkg-panel__label">场景取景</span>
            <div className="pkg-panel__chips">
              {sceneOptions.map(option => (
                <button
                  key={option.id}
                  type="button"
                  className={`pkg-chip ${selectedSceneId === option.id ? 'pkg-chip--active' : ''}`}
                  onClick={() => setSelectedSceneId(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="pkg-panel__summary">
            <div className="pkg-panel__summary-title">
              <span>当前推荐组合</span>
              <strong>
                {activeTab} · {selectedWardrobe?.label || '待定'} · {selectedScene?.label || '待定'}
              </strong>
            </div>
            <p>{recommendedCard?.description || '先点一个方向，系统会把更贴近的样片排到前面。'}</p>
          </div>
        </section>

        <section className="pkg-grid" aria-label="推荐样片">
          {rankedCards.map(item => {
            const isSelected = selected === item.id
            const isRecommended = recommendedCard?.id === item.id

            return (
              <button
                key={item.id}
                type="button"
                className={[
                  'pkg-card',
                  isSelected ? 'pkg-card--selected' : '',
                  isRecommended ? 'pkg-card--recommended' : '',
                ].join(' ').trim()}
                onClick={() => {
                  setSelected(item.id)
                  setActionError('')
                }}
              >
                <div className="pkg-card__img">
                  <img src={item.img} alt={item.name} loading="lazy" decoding="async" />
                  <div className="pkg-card__badges">
                    {isRecommended ? <span className="pkg-card__badge pkg-card__badge--recommend"><Sparkles size={12} />当前推荐</span> : null}
                    {item.badge ? <span className={`pkg-card__badge ${item.badge === '热门' ? 'pkg-card__badge--hot' : 'pkg-card__badge--gold'}`}>{item.badge}</span> : null}
                  </div>
                </div>

                <div className="pkg-card__info">
                  <h2>{item.name}</h2>
                  <p>{item.tag}</p>
                  <span>{item.description}</span>
                </div>
              </button>
            )
          })}
        </section>

        {actionError ? <div className="pkg-feedback pkg-feedback--error">{actionError}</div> : null}

        <section className="pkg-bottom">
          <button className="btn btn--outline-light" onClick={() => navigate('/makeup')}>
            上一步
          </button>
          <button className="btn btn--gold" onClick={handleContinue} disabled={rankedCards.length === 0}>
            <Camera size={18} />
            开始拍摄
          </button>
        </section>
      </main>
    </div>
  )
}
