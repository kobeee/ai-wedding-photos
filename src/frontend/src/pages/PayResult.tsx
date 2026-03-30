import { startTransition, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { CheckCircle2, Clock3, CreditCard, LoaderCircle, Sparkles } from 'lucide-react'
import {
  apiRequest,
  fetchLatestOrder,
  formatPrice,
  type OrderInfo,
  type PaymentConfirmResponse,
  type PaymentSessionResponse,
} from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './PayResult.css'

export default function PayResult() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const workflow = getWorkflowState()
  const [order, setOrder] = useState<OrderInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [resolvedOrderId, setResolvedOrderId] = useState(searchParams.get('order_id') || workflow.orderId || '')

  const isReadyToStart = useMemo(
    () => order?.payment_status === 'paid' || order?.payment_status === 'free_granted',
    [order?.payment_status],
  )

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
            navigate('/checkout')
          })
          return
        }
        setResolvedOrderId(latestOrder.order_id)
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
            navigate('/checkout')
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
    let timer: number | undefined

    async function loadOrder() {
      try {
        const payload = await apiRequest<OrderInfo>(`/api/orders/${resolvedOrderId}`)
        if (cancelled) {
          return
        }
        setOrder(payload)
        updateWorkflowState({
          orderId: payload.order_id,
          orderPaymentStatus: payload.payment_status,
          orderFulfillmentStatus: payload.fulfillment_status,
          promisedPhotos: payload.entitlement_snapshot.promised_photos,
          deliverableCount: payload.deliverable_count,
          remainingReruns: payload.remaining_reruns,
        })

        if (payload.amount > 0 && payload.payment_status === 'unpaid' && !workflow.paymentId) {
          const payment = await apiRequest<PaymentSessionResponse>('/api/pay/mock/create', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ order_id: payload.order_id }),
          })
          if (cancelled) {
            return
          }
          updateWorkflowState({
            paymentId: payment.payment_id,
            orderPaymentStatus: 'pending',
          })
        }

        if (payload.payment_status === 'pending' || payload.payment_status === 'unpaid') {
          timer = window.setTimeout(() => {
            void loadOrder()
          }, 3000)
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : '订单查询失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadOrder()
    return () => {
      cancelled = true
      if (timer) {
        window.clearTimeout(timer)
      }
    }
  }, [navigate, resolvedOrderId, workflow.paymentId])

  if (!resolvedOrderId) {
    return null
  }

  const handleConfirmMockPay = async () => {
    if (!workflow.paymentId) {
      setError('缺少支付会话，请返回重新创建订单。')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      const payment = await apiRequest<PaymentConfirmResponse>('/api/pay/mock/confirm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          payment_id: workflow.paymentId,
          succeed: true,
        }),
      })
      const payload = await apiRequest<OrderInfo>(`/api/orders/${payment.order_id}`)
      setOrder(payload)
      updateWorkflowState({
        orderPaymentStatus: payload.payment_status,
        orderFulfillmentStatus: payload.fulfillment_status,
      })
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : '支付确认失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRecreatePayment = async () => {
    if (!order) {
      return
    }
    setSubmitting(true)
    setError('')
    try {
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
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : '重新拉起支付失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="pay-result-page">
      <main className="pay-result-main">
        <div className="pay-result-card">
          <div className="pay-result-card__status">
            {loading ? (
              <LoaderCircle size={54} className="pay-result-spin" />
            ) : isReadyToStart ? (
              <CheckCircle2 size={54} color="var(--accent-gold)" />
            ) : (
              <Clock3 size={54} color="var(--accent-gold)" />
            )}
          </div>

          <span className="pay-result-card__eyebrow">支付结果</span>
          <h1>
            {loading ? '正在同步订单状态...' : isReadyToStart ? '权益已生效，可以开始拍摄' : '订单已创建，等待支付确认'}
          </h1>
          <p>
            {order
              ? `订单号 ${order.order_id} · ${order.package_name} · ${order.sku_name}`
              : '正在加载订单详情'}
          </p>

          {order ? (
            <div className="pay-result-summary">
              <div>
                <span>应付金额</span>
                <strong>{formatPrice(order.amount, order.currency)}</strong>
              </div>
              <div>
                <span>当前状态</span>
                <strong>{order.payment_status}</strong>
              </div>
              <div>
                <span>交付承诺</span>
                <strong>{order.entitlement_snapshot.promised_photos} 张 4K</strong>
              </div>
            </div>
          ) : null}

          {error ? <div className="pay-result-error">{error}</div> : null}

          <div className="pay-result-actions">
            {isReadyToStart ? (
              <button className="btn btn--gold btn--full" onClick={() => navigate('/waiting')}>
                <Sparkles size={16} />
                开始生成本单
              </button>
            ) : order?.amount === 0 ? (
              <button className="btn btn--gold btn--full" onClick={() => navigate('/waiting')}>
                <Sparkles size={16} />
                领取体验并开始生成
              </button>
            ) : (
              <button className="btn btn--gold btn--full" onClick={handleConfirmMockPay} disabled={submitting || !workflow.paymentId}>
                <CreditCard size={16} />
                {submitting ? '支付确认中...' : '模拟支付成功'}
              </button>
            )}

            {!isReadyToStart && order?.amount ? (
              <button className="btn btn--outline-light btn--full" onClick={handleRecreatePayment} disabled={submitting}>
                重新拉起支付
              </button>
            ) : (
              <button className="btn btn--outline-light btn--full" onClick={() => navigate('/checkout')}>
                返回订单确认
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
