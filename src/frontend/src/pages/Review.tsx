import { startTransition, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Aperture, Download, Paintbrush, Printer, RefreshCw, Shirt, Sparkles, X } from 'lucide-react'
import { apiRequest, fetchLatestOrder, type DeliverableListResponse, type OrderInfo } from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './Review.css'

const groomPreferenceMap: Record<string, string> = {
  natural: 'natural clean grooming',
  refined: 'polished refined grooming',
  sculpt: 'editorial sculpted grooming',
}

const bridePreferenceMap: Record<string, string> = {
  natural: 'natural translucent bridal makeup',
  refined: 'refined elegant bridal makeup',
  sculpt: 'high-fashion sculpted bridal makeup',
}

export default function Review() {
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const [resolvedOrderId, setResolvedOrderId] = useState(workflow.orderId || '')
  const [order, setOrder] = useState<OrderInfo | null>(null)
  const [resultUrls, setResultUrls] = useState<string[]>(workflow.resultUrls || [])
  const [activeIndex, setActiveIndex] = useState(0)
  const [error, setError] = useState('')
  const [rerunning, setRerunning] = useState(false)

  useEffect(() => {
    if (resolvedOrderId) {
      return
    }

    let cancelled = false
    async function resolveLatestOrder() {
      try {
        const latestOrder = await fetchLatestOrder()
        if (cancelled) {
          return
        }
        if (!latestOrder) {
          startTransition(() => {
            navigate('/waiting')
          })
          return
        }
        setResolvedOrderId(latestOrder.order_id)
        setOrder(latestOrder)
        updateWorkflowState({
          orderId: latestOrder.order_id,
          orderPaymentStatus: latestOrder.payment_status,
          orderFulfillmentStatus: latestOrder.fulfillment_status,
          promisedPhotos: latestOrder.entitlement_snapshot.promised_photos,
          deliverableCount: latestOrder.deliverable_count,
          remainingReruns: latestOrder.remaining_reruns,
        })
      } catch {
        if (!cancelled) {
          startTransition(() => {
            navigate('/waiting')
          })
        }
      }
    }

    void resolveLatestOrder()

    return () => {
      cancelled = true
    }
  }, [navigate, resolvedOrderId])

  useEffect(() => {
    if (!resolvedOrderId) {
      return
    }

    let cancelled = false
    async function loadDelivery() {
      try {
        const [orderPayload, deliverables] = await Promise.all([
          apiRequest<OrderInfo>(`/api/orders/${resolvedOrderId}`),
          apiRequest<DeliverableListResponse>(`/api/orders/${resolvedOrderId}/deliverables`),
        ])
        if (cancelled) {
          return
        }
        const urls = deliverables.items.map(item => item.url)
        setOrder(orderPayload)
        setResultUrls(urls)
        updateWorkflowState({
          orderPaymentStatus: orderPayload.payment_status,
          orderFulfillmentStatus: orderPayload.fulfillment_status,
          promisedPhotos: orderPayload.entitlement_snapshot.promised_photos,
          deliverableCount: orderPayload.deliverable_count,
          remainingReruns: orderPayload.remaining_reruns,
          qualityScore: orderPayload.latest_batch?.quality_score,
          resultUrls: urls,
        })
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : '交付信息加载失败')
        }
      }
    }

    void loadDelivery()
    return () => {
      cancelled = true
    }
  }, [navigate, resolvedOrderId])

  useEffect(() => {
    if (order && !resultUrls.length && resolvedOrderId) {
      startTransition(() => {
        navigate('/waiting')
      })
    }
  }, [navigate, order, resolvedOrderId, resultUrls.length])

  const previewImage = resultUrls[activeIndex] || ''

  const handleRerun = async () => {
    if (!resolvedOrderId || !order) {
      return
    }
    if (order.remaining_reruns <= 0) {
      setError('当前订单已无剩余重拍额度。')
      return
    }

    setRerunning(true)
    setError('')
    try {
      await apiRequest(`/api/orders/${resolvedOrderId}/reruns`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          groom_style: groomPreferenceMap[workflow.selectedMakeup?.groom || 'natural'],
          bride_style: bridePreferenceMap[workflow.selectedMakeup?.bride || 'refined'],
        }),
      })
      updateWorkflowState({
        batchId: undefined,
        taskStatus: undefined,
        taskMessage: undefined,
        progress: 0,
      })
      startTransition(() => {
        navigate('/waiting')
      })
    } catch (rerunError) {
      setError(rerunError instanceof Error ? rerunError.message : '重拍发起失败')
    } finally {
      setRerunning(false)
    }
  }

  if (!previewImage) {
    return null
  }

  return (
    <div className="review-page">
      <header className="review-header">
        <Link to="/" className="review-header__logo">
          <Aperture size={22} color="var(--accent-gold)" />
          <span>LUMIÈRE STUDIO</span>
        </Link>
        <span className="review-header__title">订单交付</span>
        <button onClick={() => navigate('/')} aria-label="关闭">
          <X size={24} color="var(--text-muted)" />
        </button>
      </header>

      <main className="review-main">
        <div className="review-preview" style={{ backgroundImage: `url(${previewImage})` }}>
          <div className="review-preview__label">
            <Sparkles size={12} color="var(--text-muted)" />
            <span>订单已完成一轮 AI 履约</span>
          </div>
        </div>

        <aside className="review-panel">
          <div className="review-panel__top">
            <div className="review-info">
              <h2>{order?.package_name || workflow.selectedPackage?.name || '定制婚纱大片'} · 第 {activeIndex + 1} 张</h2>
              <span>
                订单 {resolvedOrderId}
                {order ? ` · 已交付 ${order.deliverable_count}/${order.entitlement_snapshot.promised_photos} 张` : ''}
                {(order?.latest_batch?.quality_score ?? workflow.qualityScore)
                  ? ` · 综合评分 ${(order?.latest_batch?.quality_score ?? workflow.qualityScore ?? 0).toFixed(2)}`
                  : ''}
              </span>
            </div>

            <div className="review-thumbs">
              <span className="review-thumbs__label">本单已交付 {resultUrls.length} 张</span>
              <div className="review-thumbs__row">
                {resultUrls.map((imageUrl, index) => (
                  <button
                    key={imageUrl}
                    type="button"
                    className={`review-thumb ${index === activeIndex ? 'review-thumb--active' : ''}`}
                    style={{ backgroundImage: `url(${imageUrl})` }}
                    onClick={() => setActiveIndex(index)}
                  />
                ))}
              </div>
            </div>

            <div className="review-magic">
              <span className="review-magic__label">订单权益</span>
              <div className="review-magic__btns">
                <button disabled><Shirt size={14} />换装</button>
                <button disabled><Paintbrush size={14} />重绘</button>
                <button disabled>{`重拍剩余 ${order?.remaining_reruns ?? workflow.remainingReruns ?? 0} 次`}</button>
              </div>
            </div>

            {error ? <div className="review-error">{error}</div> : null}
          </div>

          <div className="review-actions">
            <a className="btn btn--gold btn--full" href={previewImage} download target="_blank" rel="noreferrer">
              <Download size={16} />下载当前 4K 大图
            </a>
            <button className="btn btn--outline-light btn--full" onClick={handleRerun} disabled={rerunning || (order?.remaining_reruns ?? 0) <= 0}>
              <RefreshCw size={16} />{rerunning ? '正在发起重拍...' : '再拍一组'}
            </button>
            <button className="btn btn--outline-light btn--full" disabled>
              <Printer size={16} />去冲印
            </button>
          </div>
        </aside>
      </main>
    </div>
  )
}
