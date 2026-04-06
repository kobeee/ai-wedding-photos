import { startTransition, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Aperture, Download, Paintbrush, Printer, RefreshCw, Shirt, Sparkles, X } from 'lucide-react'
import { apiRequest, type DeliverableListResponse, type OrderInfo } from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './Delivery.css'

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

export default function Delivery() {
  const { orderId } = useParams<{ orderId: string }>()
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const [order, setOrder] = useState<OrderInfo | null>(null)
  const [resultUrls, setResultUrls] = useState<string[]>(workflow.resultUrls || [])
  const [activeIndex, setActiveIndex] = useState(0)
  const [error, setError] = useState('')
  const [rerunning, setRerunning] = useState(false)

  useEffect(() => {
    if (!orderId) {
      startTransition(() => {
        navigate('/waiting')
      })
      return
    }

    let cancelled = false

    async function loadDelivery() {
      try {
        const [orderPayload, deliverables] = await Promise.all([
          apiRequest<OrderInfo>(`/api/orders/${orderId}`),
          apiRequest<DeliverableListResponse>(`/api/orders/${orderId}/deliverables`),
        ])
        if (cancelled) {
          return
        }
        const urls = deliverables.items.map(item => item.url)
        setOrder(orderPayload)
        setResultUrls(urls)
        updateWorkflowState({
          orderId: orderPayload.order_id,
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
  }, [navigate, orderId])

  useEffect(() => {
    if (order && !resultUrls.length && orderId) {
      startTransition(() => {
        navigate(`/waiting/${orderId}`)
      })
    }
  }, [navigate, order, orderId, resultUrls.length])

  const previewImage = resultUrls[activeIndex] || ''

  const handleRerun = async () => {
    if (!orderId || !order) {
      return
    }
    if (order.remaining_reruns <= 0) {
      setError('当前订单已无剩余重拍额度。')
      return
    }

    setRerunning(true)
    setError('')
    try {
      await apiRequest(`/api/orders/${orderId}/reruns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          groom_makeup_style: workflow.selectedMakeup?.groom || 'natural',
          bride_makeup_style: workflow.selectedMakeup?.bride || 'refined',
          groom_makeup_reference_url: workflow.selectedMakeupReferences?.groom,
          bride_makeup_reference_url: workflow.selectedMakeupReferences?.bride,
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
        navigate(`/waiting/${orderId}`)
      })
    } catch (rerunError) {
      setError(rerunError instanceof Error ? rerunError.message : '重拍发起失败')
    } finally {
      setRerunning(false)
    }
  }

  if (error && !previewImage) {
    return (
      <div className="delivery-page">
        <header className="delivery-header">
          <Link to="/" className="delivery-header__logo">
            <Aperture size={22} color="var(--accent-gold)" />
            <span>LUMIÈRE STUDIO</span>
          </Link>
          <span className="delivery-header__title">订单交付</span>
          <button onClick={() => navigate('/')} aria-label="关闭">
            <X size={24} color="var(--text-muted)" />
          </button>
        </header>
        <main className="delivery-main" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="delivery-error">{error}</div>
        </main>
      </div>
    )
  }

  if (!previewImage) {
    return null
  }

  return (
    <div className="delivery-page">
      <header className="delivery-header">
        <Link to="/" className="delivery-header__logo">
          <Aperture size={22} color="var(--accent-gold)" />
          <span>LUMIÈRE STUDIO</span>
        </Link>
        <span className="delivery-header__title">订单交付</span>
        <button onClick={() => navigate('/')} aria-label="关闭">
          <X size={24} color="var(--text-muted)" />
        </button>
      </header>

      <main className="delivery-main">
        <div className="delivery-preview" style={{ backgroundImage: `url(${previewImage})` }}>
          <div className="delivery-preview__label">
            <Sparkles size={12} color="var(--text-muted)" />
            <span>订单已完成一轮 AI 履约</span>
          </div>
        </div>

        <aside className="delivery-panel">
          <div className="delivery-panel__top">
            <div className="delivery-info">
              <h2>{order?.package_name || '定制婚纱大片'} · 第 {activeIndex + 1} 张</h2>
              <span>
                订单 {orderId}
                {order ? ` · 已交付 ${order.deliverable_count}/${order.entitlement_snapshot.promised_photos} 张` : ''}
                {(order?.latest_batch?.quality_score ?? workflow.qualityScore)
                  ? ` · 综合评分 ${(order?.latest_batch?.quality_score ?? workflow.qualityScore ?? 0).toFixed(2)}`
                  : ''}
              </span>
            </div>

            <div className="delivery-thumbs">
              <span className="delivery-thumbs__label">本单已交付 {resultUrls.length} 张</span>
              <div className="delivery-thumbs__row">
                {resultUrls.map((imageUrl, index) => (
                  <button
                    key={imageUrl}
                    type="button"
                    className={`delivery-thumb ${index === activeIndex ? 'delivery-thumb--active' : ''}`}
                    style={{ backgroundImage: `url(${imageUrl})` }}
                    onClick={() => setActiveIndex(index)}
                  />
                ))}
              </div>
            </div>

            <div className="delivery-magic">
              <span className="delivery-magic__label">订单权益</span>
              <div className="delivery-magic__btns">
                <button disabled><Shirt size={14} />换装</button>
                <button disabled><Paintbrush size={14} />重绘</button>
                <button disabled>{`重拍剩余 ${order?.remaining_reruns ?? workflow.remainingReruns ?? 0} 次`}</button>
              </div>
            </div>

            {error ? <div className="delivery-error">{error}</div> : null}
          </div>

          <div className="delivery-actions">
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
