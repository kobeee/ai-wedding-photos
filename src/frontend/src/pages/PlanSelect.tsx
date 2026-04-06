import { startTransition, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Mail, Sparkles, Tag } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import {
  fetchPlans,
  formatPrice,
  verifyExperienceCode,
  type SkuInfo,
} from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './PlanSelect.css'

export default function PlanSelect() {
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const [plans, setPlans] = useState<SkuInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedSkuId, setSelectedSkuId] = useState(workflow.selectedSku?.id || '')
  const [email, setEmail] = useState(workflow.email || '')
  const [expCode, setExpCode] = useState(workflow.experienceCode || '')
  const [expCodeVerified, setExpCodeVerified] = useState(false)
  const [expCodeMsg, setExpCodeMsg] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const items = await fetchPlans()
        if (cancelled) {
          return
        }
        setPlans(items)
        if (!selectedSkuId && items.length > 0) {
          const recommended = items.find(i => i.highlight) || items[0]
          setSelectedSkuId(recommended.sku_id)
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : '方案加载失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [selectedSkuId])

  const selectedPlan = plans.find(p => p.sku_id === selectedSkuId)
  const isFree = selectedPlan?.price === 0

  const handleVerifyCode = async () => {
    if (!expCode.trim()) {
      return
    }
    setExpCodeMsg('')
    try {
      const result = await verifyExperienceCode(expCode.trim())
      setExpCodeVerified(result.valid)
      setExpCodeMsg(result.message)
    } catch {
      setExpCodeMsg('验证失败，请稍后重试')
    }
  }

  const handleContinue = () => {
    if (!selectedPlan) {
      setError('请选择一个方案')
      return
    }

    const trimmedEmail = email.trim()
    if (!trimmedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setError('请输入有效的邮箱地址，用于接收订单和找回结果')
      return
    }

    if (isFree && !expCodeVerified) {
      setError('免费体验需要先验证体验码')
      return
    }

    setError('')

    updateWorkflowState({
      selectedSku: {
        id: selectedPlan.sku_id,
        name: selectedPlan.name,
        price: selectedPlan.price,
        description: selectedPlan.description,
        tag: selectedPlan.tag,
        sceneCount: selectedPlan.entitlements.scene_count,
      },
      email: trimmedEmail,
      experienceCode: isFree ? expCode.trim() : undefined,
    })

    startTransition(() => {
      navigate('/scenes')
    })
  }

  if (loading) {
    return (
      <div className="plan-page">
        <StepHeader current={1} onClose={() => navigate('/')} />
        <main className="plan-main">
          <div className="plan-loading">正在加载方案...</div>
        </main>
      </div>
    )
  }

  return (
    <div className="plan-page">
      <StepHeader current={1} onClose={() => navigate('/')} />

      <main className="plan-main">
        <section className="plan-hero">
          <div className="plan-hero__eyebrow">
            <Sparkles size={14} />
            <span>选择你的方案</span>
          </div>
          <h1>从免费体验到档案珍藏</h1>
          <p>先选定方案与承诺交付规格，再进入选景与拍摄流程。</p>
        </section>

        <section className="plan-cards">
          {plans.map(plan => {
            const isActive = plan.sku_id === selectedSkuId
            return (
              <button
                key={plan.sku_id}
                type="button"
                className={`plan-card${isActive ? ' plan-card--active' : ''}${plan.highlight ? ' plan-card--highlight' : ''}`}
                onClick={() => {
                  setSelectedSkuId(plan.sku_id)
                  setError('')
                }}
              >
                <div className="plan-card__top">
                  <span className="plan-card__tag">{plan.tag}</span>
                  {plan.highlight && <span className="plan-card__badge">推荐</span>}
                </div>
                <h2>{plan.name}</h2>
                <div className="plan-card__price">{formatPrice(plan.price)}</div>
                <p className="plan-card__desc">{plan.description}</p>
                <ul className="plan-card__features">
                  <li><Check size={14} color="var(--accent-gold)" />{plan.entitlements.promised_photos} 张 4K 成片</li>
                  <li><Check size={14} color="var(--accent-gold)" />{plan.entitlements.scene_count} 组场景叙事</li>
                  <li><Check size={14} color="var(--accent-gold)" />{plan.entitlements.rerun_quota} 次重拍额度</li>
                  <li><Check size={14} color="var(--accent-gold)" />{plan.entitlements.retention_days} 天结果保留</li>
                </ul>
              </button>
            )
          })}
        </section>

        <section className="plan-form">
          <div className="plan-form__field">
            <label>
              <Mail size={16} color="var(--accent-gold)" />
              邮箱地址
            </label>
            <input
              type="email"
              placeholder="用于接收订单确认和找回交付结果"
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
          </div>

          {isFree && (
            <div className="plan-form__field">
              <label>
                <Tag size={16} color="var(--accent-gold)" />
                体验码
              </label>
              <div className="plan-form__code-row">
                <input
                  type="text"
                  placeholder="输入体验码，免费体验 3 张样片"
                  value={expCode}
                  onChange={e => {
                    setExpCode(e.target.value)
                    setExpCodeVerified(false)
                    setExpCodeMsg('')
                  }}
                />
                <button
                  type="button"
                  className="btn btn--outline-light"
                  onClick={handleVerifyCode}
                  disabled={!expCode.trim()}
                >
                  验证
                </button>
              </div>
              {expCodeMsg && (
                <span className={`plan-form__msg ${expCodeVerified ? 'plan-form__msg--ok' : 'plan-form__msg--err'}`}>
                  {expCodeMsg}
                </span>
              )}
            </div>
          )}
        </section>

        {error && <div className="plan-error">{error}</div>}

        <div className="plan-bottom">
          <button className="btn btn--outline-light" onClick={() => navigate('/')}>返回首页</button>
          <button className="btn btn--gold" onClick={handleContinue}>
            下一步：选择场景
          </button>
        </div>
      </main>
    </div>
  )
}
