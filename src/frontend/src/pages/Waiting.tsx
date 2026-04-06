import { startTransition, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Aperture, Circle, CircleAlert, CircleCheck, Loader, RefreshCw } from 'lucide-react'
import {
  apiRequest,
  createOrder,
  fetchLatestOrder,
  type BatchListResponse,
  type DeliverableListResponse,
  type GenerationBatchInfo,
  type OrderInfo,
  type PaymentSessionResponse,
  type StartOrderResponse,
} from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './Waiting.css'

const steps = [
  '订单权益已锁定',
  '视觉语境与妆造偏好已编译',
  '正在分批渲染本单交付',
  '质检完成，准备进入交付页',
]

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

function getCurrentStep(progress: number, status: GenerationBatchInfo['status'] | ''): number {
  if (status === 'completed') {
    return 3
  }
  if (progress < 25) {
    return 0
  }
  if (progress < 55) {
    return 1
  }
  if (progress < 85) {
    return 2
  }
  return 3
}

export default function Waiting() {
  const { orderId: urlOrderId } = useParams<{ orderId: string }>()
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const [resolvedOrderId, setResolvedOrderId] = useState(urlOrderId || workflow.orderId || '')
  const [order, setOrder] = useState<OrderInfo | null>(null)
  const [progress, setProgress] = useState(workflow.progress || 0)
  const [message, setMessage] = useState(workflow.taskMessage || '正在准备订单履约...')
  const [status, setStatus] = useState<GenerationBatchInfo['status'] | ''>((workflow.taskStatus as GenerationBatchInfo['status']) || '')
  const [error, setError] = useState('')

  useEffect(() => {
    if (resolvedOrderId) {
      return
    }

    let cancelled = false

    async function resolveLatestOrder() {
      try {
        const wf = getWorkflowState()
        const hasCurrentSelection = wf.selectedSku?.id && wf.selectedSceneIds?.length

        if (!hasCurrentSelection) {
          const latestOrder = await fetchLatestOrder()
          if (cancelled) {
            return
          }
          if (latestOrder) {
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
            return
          }
        }
        if (wf.selectedSku?.id && wf.selectedSceneIds?.length) {
          const newOrder = await createOrder({
            sku_id: wf.selectedSku.id,
            email: wf.email || '',
            scene_ids: wf.selectedSceneIds,
            experience_code: wf.experienceCode,
          })
          if (cancelled) {
            return
          }

          updateWorkflowState({
            orderId: newOrder.order_id,
            orderPaymentStatus: newOrder.payment_status,
            orderFulfillmentStatus: newOrder.fulfillment_status,
            promisedPhotos: newOrder.entitlement_snapshot.promised_photos,
            deliverableCount: newOrder.deliverable_count,
            remainingReruns: newOrder.remaining_reruns,
          })

          if (newOrder.amount > 0 && newOrder.payment_status === 'unpaid') {
            const paySession = await apiRequest<PaymentSessionResponse>(
              '/api/pay/mock/create',
              {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order_id: newOrder.order_id }),
              },
            )
            updateWorkflowState({ paymentId: paySession.payment_id })
            startTransition(() => {
              navigate(`/pay/result?order_id=${newOrder.order_id}&payment_id=${paySession.payment_id}`)
            })
            return
          }

          setResolvedOrderId(newOrder.order_id)
          setOrder(newOrder)
          return
        }

        startTransition(() => {
          navigate('/plan')
        })
      } catch {
        if (!cancelled) {
          startTransition(() => {
            navigate('/plan')
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

    const syncOrder = async () => {
      const [orderPayload, batches, deliverables] = await Promise.all([
        apiRequest<OrderInfo>(`/api/orders/${resolvedOrderId}`),
        apiRequest<BatchListResponse>(`/api/orders/${resolvedOrderId}/batches`),
        apiRequest<DeliverableListResponse>(`/api/orders/${resolvedOrderId}/deliverables`),
      ])

      if (cancelled) {
        return
      }

      setOrder(orderPayload)
      const latestBatch = batches.items[0]
      const resultUrls = deliverables.items.map(item => item.url)
      const currentMessage = latestBatch?.message || '正在准备订单履约...'
      const currentStatus = latestBatch?.status || ''
      const currentProgress = latestBatch?.progress || 0

      setProgress(currentProgress)
      setMessage(currentMessage)
      setStatus(currentStatus)
      updateWorkflowState({
        orderId: orderPayload.order_id,
        orderPaymentStatus: orderPayload.payment_status,
        orderFulfillmentStatus: orderPayload.fulfillment_status,
        batchId: latestBatch?.batch_id,
        taskStatus: currentStatus,
        taskMessage: currentMessage,
        progress: currentProgress,
        qualityScore: latestBatch?.quality_score,
        promisedPhotos: orderPayload.entitlement_snapshot.promised_photos,
        deliverableCount: orderPayload.deliverable_count,
        remainingReruns: orderPayload.remaining_reruns,
        resultUrls,
      })

      if (orderPayload.payment_status !== 'paid' && orderPayload.payment_status !== 'free_granted') {
        startTransition(() => {
          navigate(`/pay/result?order_id=${orderPayload.order_id}`)
        })
        return
      }

      if ((orderPayload.fulfillment_status === 'delivered' || orderPayload.fulfillment_status === 'partially_delivered') && resultUrls.length > 0) {
        startTransition(() => {
          navigate(`/delivery/${orderPayload.order_id}`)
        })
        return
      }

      if (latestBatch?.status === 'failed') {
        setError(latestBatch.failure_reason || latestBatch.message || '本次履约失败，请重试')
        return
      }

      timer = window.setTimeout(() => {
        void syncOrder()
      }, 4000)
    }

    const ensureBatchStarted = async () => {
      try {
        setError('')
        setMessage('正在校验订单状态...')

        const orderPayload = await apiRequest<OrderInfo>(`/api/orders/${resolvedOrderId}`)
        if (cancelled) {
          return
        }
        setOrder(orderPayload)

        if (orderPayload.payment_status !== 'paid' && orderPayload.payment_status !== 'free_granted') {
          startTransition(() => {
            navigate(`/pay/result?order_id=${orderPayload.order_id}`)
          })
          return
        }

        if (!orderPayload.latest_batch || !['pending', 'processing', 'completed'].includes(orderPayload.latest_batch.status)) {
          const payload = await apiRequest<StartOrderResponse>(`/api/orders/${resolvedOrderId}/start`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              groom_makeup_style: workflow.selectedMakeup?.groom || 'natural',
              bride_makeup_style: workflow.selectedMakeup?.bride || 'refined',
              groom_makeup_reference_url: workflow.selectedMakeupReferences?.groom,
              bride_makeup_reference_url: workflow.selectedMakeupReferences?.bride,
              groom_style: groomPreferenceMap[workflow.selectedMakeup?.groom || 'natural'],
              bride_style: bridePreferenceMap[workflow.selectedMakeup?.bride || 'refined'],
            }),
          })
          if (cancelled) {
            return
          }
          updateWorkflowState({
            batchId: payload.batch_id,
            orderFulfillmentStatus: payload.fulfillment_status,
          })
        }

        await syncOrder()
      } catch (syncError) {
        if (!cancelled) {
          setError(syncError instanceof Error ? syncError.message : '订单履约启动失败')
        }
      }
    }

    void ensureBatchStarted()

    return () => {
      cancelled = true
      if (timer) {
        window.clearTimeout(timer)
      }
    }
  }, [navigate, resolvedOrderId, workflow.selectedMakeup?.bride, workflow.selectedMakeup?.groom])

  const currentStep = getCurrentStep(progress, status)

  const handleRetry = () => {
    setError('')
    updateWorkflowState({
      batchId: undefined,
      taskStatus: undefined,
      taskMessage: undefined,
      progress: undefined,
      qualityScore: undefined,
    })
    window.location.reload()
  }

  if (!resolvedOrderId) {
    return null
  }

  return (
    <div className="waiting-page">
      <div className="waiting-center">
        <div className="waiting-ring">
          <Aperture size={60} color="var(--accent-gold)" />
        </div>

        <div className="waiting-texts">
          <h1>{error || message}</h1>
          <p>
            {error
              ? '这笔订单尚未完成履约，你可以重试当前订单批次。'
              : `订单 ${resolvedOrderId} · ${order?.package_name || workflow.selectedPackage?.name || '定制方案'} · 已承诺 ${order?.entitlement_snapshot.promised_photos || workflow.promisedPhotos || 0} 张`}
          </p>
        </div>

        {error ? (
          <div className="waiting-error">
            <CircleAlert size={18} />
            <span>{error}</span>
          </div>
        ) : (
          <div className="waiting-progress">
            <div className="waiting-bar">
              <div className="waiting-bar__fill" style={{ width: `${progress}%` }} />
            </div>
            <span>{progress}%</span>
          </div>
        )}

        <div className="waiting-steps">
          {steps.map((step, index) => (
            <div key={step} className="waiting-step">
              {index < currentStep ? (
                <CircleCheck size={16} color="var(--accent-gold)" />
              ) : index === currentStep && !error ? (
                <Loader size={16} color="var(--accent-gold)" className="waiting-spin" />
              ) : (
                <Circle size={16} color="var(--text-muted)" />
              )}
              <span className={index <= currentStep && !error ? 'waiting-step--active' : ''}>{step}</span>
            </div>
          ))}
        </div>

        {error ? (
          <div className="waiting-actions">
            <button className="btn btn--outline-light" onClick={() => navigate(`/pay/result?order_id=${resolvedOrderId}`)}>
              返回订单
            </button>
            <button className="btn btn--gold" onClick={handleRetry}>
              <RefreshCw size={16} />
              重新发起履约
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
