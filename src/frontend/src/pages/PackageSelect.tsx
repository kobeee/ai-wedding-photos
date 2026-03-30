import { startTransition, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Camera } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import { packageCards } from '../data/packages'
import { apiRequest, type PackageInfo } from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './PackageSelect.css'

const categoryLabels: Record<PackageInfo['category'], string> = {
  chinese: '中式',
  western: '西式',
  artistic: '艺术',
  travel: '旅拍',
}

const previewFallback = Object.fromEntries(
  packageCards.map(item => [item.id, item.img]),
) as Record<string, string>

const fallbackPackages: PackageInfo[] = packageCards.map(item => ({
  id: item.id,
  name: item.name,
  tag: item.tag,
  category: item.cat === '中式'
    ? 'chinese'
    : item.cat === '旅拍'
      ? 'travel'
      : item.cat === '奇幻'
        ? 'artistic'
        : 'western',
  preview_url: item.img,
}))

export default function PackageSelect() {
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const [packages, setPackages] = useState<PackageInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('全部')
  const [selected, setSelected] = useState<string | null>(workflow.selectedPackage?.id || null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadPackages() {
      try {
        const payload = await apiRequest<PackageInfo[]>('/api/packages')
        if (cancelled) {
          return
        }
        setPackages(payload)
      } catch (loadError) {
        if (cancelled) {
          return
        }
        setPackages(fallbackPackages)
        setError(loadError instanceof Error ? `${loadError.message}，已切换本地套餐目录。` : '套餐列表加载失败，已切换本地套餐目录。')
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadPackages()

    return () => {
      cancelled = true
    }
  }, [])

  const tabs = useMemo(() => {
    const dynamicTabs = packages.map(item => categoryLabels[item.category])
    return ['全部', ...Array.from(new Set(dynamicTabs))]
  }, [packages])

  const filtered = useMemo(
    () => activeTab === '全部'
      ? packages
      : packages.filter(item => categoryLabels[item.category] === activeTab),
    [activeTab, packages],
  )

  useEffect(() => {
    if (!workflow.userId || !workflow.uploadsComplete) {
      startTransition(() => {
        navigate('/upload')
      })
    }
  }, [navigate, workflow.uploadsComplete, workflow.userId])

  if (!workflow.userId || !workflow.uploadsComplete) {
    return null
  }

  const handleContinue = () => {
    const selectedPackage = packages.find(item => item.id === selected)
    if (!selectedPackage) {
      setError('请先选择一套视觉方案。')
      return
    }

    setError('')
    updateWorkflowState({
      selectedPackage: {
        id: selectedPackage.id,
        name: selectedPackage.name,
        tag: selectedPackage.tag,
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
        <div className="pkg-title">
          <h1>选择您的视觉套餐</h1>
          <p>像刷小红书一样，找到属于你们的风格</p>
        </div>

        <div className="pkg-tabs">
          {tabs.map(tab => (
            <button
              key={tab}
              className={`pkg-tab ${activeTab === tab ? 'pkg-tab--active' : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="pkg-grid">
          {loading ? (
            <div className="pkg-feedback">正在加载视觉套餐...</div>
          ) : (
            filtered.map(item => {
              const previewUrl = item.preview_url || previewFallback[item.id] || ''
              const isSelected = selected === item.id
              const isPopular = item.tag.includes('热门')
              const isFeatured = item.tag.includes('新品')

              return (
                <button
                  key={item.id}
                  type="button"
                  className={`pkg-card ${isSelected ? 'pkg-card--selected' : ''}`}
                  onClick={() => {
                    setSelected(item.id)
                    setError('')
                  }}
                >
                  <div
                    className="pkg-card__img"
                    style={previewUrl ? { backgroundImage: `url(${previewUrl})` } : undefined}
                  />
                  <div className="pkg-card__info">
                    <h3>{item.name}</h3>
                    <span>{item.tag || categoryLabels[item.category]}</span>
                    {isPopular ? <span className="pkg-card__badge pkg-card__badge--hot">热门</span> : null}
                    {isFeatured ? <span className="pkg-card__badge pkg-card__badge--svip">推荐</span> : null}
                  </div>
                </button>
              )
            })
          )}
        </div>

        {error ? <div className="pkg-feedback pkg-feedback--error">{error}</div> : null}

        <div className="pkg-bottom">
          <button className="btn btn--outline-light" onClick={() => navigate('/makeup')}>上一步</button>
          <button className="btn btn--gold" onClick={handleContinue} disabled={loading || packages.length === 0}>
            <Camera size={18} />
            继续确认订单
          </button>
        </div>
      </main>
    </div>
  )
}
