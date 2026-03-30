import { startTransition, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, CreditCard, Sparkles } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import {
  apiRequest,
  formatPrice,
  type OrderInfo,
  type PaymentSessionResponse,
  type SkuInfo,
} from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './Checkout.css'

export default function Checkout() {
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const selectedPackage = workflow.selectedPackage
  const [skus, setSkus] = useState<SkuInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [selectedSkuId, setSelectedSkuId] = useState(workflow.selectedSku?.id || 'memory_699')

  useEffect(() => {
    if (!workflow.userId || !workflow.uploadsComplete || !selectedPackage) {
      startTransition(() => {
        navigate('/package')
      })
      return
    }

    let cancelled = false
    async function loadSkus() {
      try {
        const payload = await apiRequest<SkuInfo[]>('/api/skus')
        if (cancelled) {
          return
        }
        setSkus(payload)
        if (!workflow.selectedSku && payload.length > 0) {
          const recommended = payload.find(item => item.highlight) || payload[0]
          setSelectedSkuId(recommended.sku_id)
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'SKU 加载失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadSkus()
    return () => {
      cancelled = true
    }
  }, [navigate, selectedPackage, workflow.selectedSku, workflow.uploadsComplete, workflow.userId])

  const selectedSku = useMemo(
    () => skus.find(item => item.sku_id === selectedSkuId) || null,
    [selectedSkuId, skus],
  )

  if (!workflow.userId || !workflow.uploadsComplete || !selectedPackage) {
    return null
  }

  const handleSubmit = async () => {
    if (!selectedSku) {
      setError('请先选择一个商品方案。')
      return
    }

    setSubmitting(true)
    setError('')

    try {
      const order = await apiRequest<OrderInfo>('/api/orders', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          package_id: selectedPackage.id,
          sku_id: selectedSku.sku_id,
        }),
      })

      updateWorkflowState({
        selectedSku: {
          id: selectedSku.sku_id,
          name: selectedSku.name,
          price: selectedSku.price,
          description: selectedSku.description,
          tag: selectedSku.tag,
        },
        orderId: order.order_id,
        orderPaymentStatus: order.payment_status,
        orderFulfillmentStatus: order.fulfillment_status,
        promisedPhotos: order.entitlement_snapshot.promised_photos,
        deliverableCount: order.deliverable_count,
        remainingReruns: order.remaining_reruns,
        paymentId: undefined,
        batchId: undefined,
        taskStatus: undefined,
        taskMessage: undefined,
        progress: undefined,
        qualityScore: undefined,
        resultUrls: undefined,
      })

      if (order.amount > 0) {
        const payment = await apiRequest<PaymentSessionResponse>('/api/pay/mock/create', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ order_id: order.order_id }),
        })

        updateWorkflowState({
          paymentId: payment.payment_id,
          orderPaymentStatus: 'pending',
        })
      }

      startTransition(() => {
        navigate(`/pay/result?order_id=${order.order_id}`)
      })
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '创建订单失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="checkout-page">
      <StepHeader current={3} onClose={() => navigate('/')} />
      <main className="checkout-main">
        <section className="checkout-hero">
          <span className="checkout-hero__eyebrow">确认订单</span>
          <h1>{selectedPackage.name} 已加入本次拍摄</h1>
          <p>视觉主题负责你们要拍成什么样，SKU 负责这笔订单承诺交付多少张、保留多久、还能再拍几次。</p>
        </section>

        <section className="checkout-grid">
          <div className="checkout-cards">
            {loading ? (
              <div className="checkout-loading">正在加载商品方案...</div>
            ) : (
              skus.map(item => {
                const active = selectedSkuId === item.sku_id
                return (
                  <button
                    key={item.sku_id}
                    type="button"
                    className={`checkout-card ${active ? 'checkout-card--active' : ''} ${item.highlight ? 'checkout-card--highlight' : ''}`}
                    onClick={() => setSelectedSkuId(item.sku_id)}
                  >
                    <div className="checkout-card__top">
                      <div>
                        <span className="checkout-card__tag">{item.tag || '商品 SKU'}</span>
                        <h2>{item.name}</h2>
                      </div>
                      {item.highlight ? (
                        <span className="checkout-card__badge">
                          <Sparkles size={14} />
                          主推
                        </span>
                      ) : null}
                    </div>
                    <div className="checkout-card__price">{formatPrice(item.price, item.currency)}</div>
                    <p className="checkout-card__desc">{item.description}</p>
                    <ul className="checkout-card__features">
                      <li><Check size={14} />{item.entitlements.scene_count} 景主题组</li>
                      <li><Check size={14} />{item.entitlements.promised_photos} 张 4K 交付</li>
                      <li><Check size={14} />保留 {item.entitlements.retention_days} 天</li>
                      <li><Check size={14} />重拍额度 {item.entitlements.rerun_quota} 次</li>
                    </ul>
                  </button>
                )
              })
            )}
          </div>

          <aside className="checkout-summary">
            <span className="checkout-summary__label">本次确认</span>
            <h3>{selectedPackage.name}</h3>
            <p>{selectedPackage.tag}</p>

            <div className="checkout-summary__section">
              <span>商品</span>
              <strong>{selectedSku?.name || '请选择 SKU'}</strong>
            </div>
            <div className="checkout-summary__section">
              <span>交付承诺</span>
              <strong>{selectedSku ? `${selectedSku.entitlements.promised_photos} 张 4K` : '--'}</strong>
            </div>
            <div className="checkout-summary__section">
              <span>支付方式</span>
              <strong>Mock 支付联调</strong>
            </div>

            {error ? <div className="checkout-error">{error}</div> : null}

            <button className="btn btn--gold btn--full" disabled={!selectedSku || submitting || loading} onClick={handleSubmit}>
              <CreditCard size={16} />
              {submitting ? '正在创建订单...' : selectedSku?.price ? `去支付 ${formatPrice(selectedSku.price)}` : '领取免费体验'}
            </button>
            <button className="btn btn--outline-light btn--full" onClick={() => navigate('/package')}>
              返回重选视觉主题
            </button>
          </aside>
        </section>
      </main>
    </div>
  )
}
