import { startTransition, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Aperture, Mail, Search } from 'lucide-react'
import { formatPrice, lookupOrdersByEmail, type OrderInfo } from '../lib/api'
import './Orders.css'

const statusLabels: Record<string, string> = {
  unpaid: '待支付',
  pending: '处理中',
  paid: '已支付',
  free_granted: '免费体验',
  failed: '支付失败',
  refunded: '已退款',
  expired: '已过期',
}

const fulfillmentLabels: Record<string, string> = {
  not_started: '未开始',
  queued: '排队中',
  processing: '生成中',
  delivered: '已交付',
  partially_delivered: '部分交付',
  failed: '生成失败',
}

export default function Orders() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [orders, setOrders] = useState<OrderInfo[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSearch = async () => {
    const trimmed = email.trim()
    if (!trimmed) {
      setError('请输入邮箱地址')
      return
    }

    setLoading(true)
    setError('')
    try {
      const result = await lookupOrdersByEmail(trimmed)
      setOrders(result.items)
      if (result.items.length === 0) {
        setError('未找到与该邮箱关联的订单')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '查询失败')
    } finally {
      setLoading(false)
    }
  }

  const handleOrderClick = (order: OrderInfo) => {
    const hasDelivery = order.fulfillment_status === 'delivered' || order.fulfillment_status === 'partially_delivered'
    if (hasDelivery) {
      startTransition(() => {
        navigate(`/delivery/${order.order_id}`)
      })
    } else if (order.payment_status === 'paid' || order.payment_status === 'free_granted') {
      startTransition(() => {
        navigate(`/waiting/${order.order_id}`)
      })
    }
  }

  return (
    <div className="orders-page">
      <header className="orders-header">
        <Link to="/" className="orders-header__logo">
          <Aperture size={22} color="var(--accent-gold)" />
          <span>LUMIÈRE STUDIO</span>
        </Link>
        <span className="orders-header__title">订单查询</span>
        <div />
      </header>

      <main className="orders-main">
        <section className="orders-search">
          <h1>查询你的订单</h1>
          <p>输入下单时使用的邮箱地址，查看所有关联订单和交付结果。</p>

          <div className="orders-search__row">
            <div className="orders-search__input">
              <Mail size={18} color="var(--text-muted)" />
              <input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    void handleSearch()
                  }
                }}
              />
            </div>
            <button className="btn btn--gold" onClick={handleSearch} disabled={loading}>
              <Search size={16} />
              {loading ? '查询中...' : '查询'}
            </button>
          </div>

          {error && <div className="orders-error">{error}</div>}
        </section>

        {orders && orders.length > 0 && (
          <section className="orders-list">
            {orders.map(order => {
              const hasDelivery = order.fulfillment_status === 'delivered' || order.fulfillment_status === 'partially_delivered'
              return (
                <button
                  key={order.order_id}
                  type="button"
                  className="orders-card"
                  onClick={() => handleOrderClick(order)}
                >
                  <div className="orders-card__top">
                    <span className="orders-card__id">#{order.order_id.slice(0, 8)}</span>
                    <span className="orders-card__status">{fulfillmentLabels[order.fulfillment_status] || order.fulfillment_status}</span>
                  </div>
                  <h3>{order.package_name || order.sku_name}</h3>
                  <div className="orders-card__meta">
                    <span>{formatPrice(order.amount)}</span>
                    <span>{statusLabels[order.payment_status] || order.payment_status}</span>
                    <span>交付 {order.deliverable_count}/{order.entitlement_snapshot.promised_photos}</span>
                  </div>
                  <span className="orders-card__date">{new Date(order.created_at).toLocaleDateString('zh-CN')}</span>
                  {hasDelivery && <span className="orders-card__action">查看交付 →</span>}
                </button>
              )
            })}
          </section>
        )}
      </main>
    </div>
  )
}
