import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Camera, Image } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import './PackageSelect.css'

const tabs = ['全部', '棚拍', '旅拍', '奇幻', '中式', '胶片']

const packages = [
  { name: '极简高定棚拍', tag: '棚拍 · 极简 · 高级感', cat: '棚拍' },
  { name: '冰岛黑沙滩史诗', tag: '旅拍 · 史诗 · 大片感', cat: '旅拍', hot: true },
  { name: '中式赛博朋克', tag: '中式 · 赛博 · 未来感', cat: '中式' },
  { name: '法式街角胶片', tag: '胶片 · 法式 · 浪漫', cat: '胶片' },
  { name: '极光星空梦境', tag: '奇幻 · 星空 · 梦幻', cat: '奇幻', svip: true },
  { name: '王家卫港风', tag: '胶片 · 港风 · 情绪感', cat: '胶片' },
]

export default function PackageSelect() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('全部')
  const [selected, setSelected] = useState<string | null>(null)

  const filtered = activeTab === '全部' ? packages : packages.filter(p => p.cat === activeTab)

  return (
    <div className="pkg-page">
      <StepHeader current={3} onClose={() => navigate('/')} />
      <main className="pkg-main">
        <div className="pkg-title">
          <h1>选择您的视觉套餐</h1>
          <p>像刷小红书一样，找到属于你们的风格</p>
        </div>

        <div className="pkg-tabs">
          {tabs.map(t => (
            <button
              key={t}
              className={`pkg-tab ${activeTab === t ? 'pkg-tab--active' : ''}`}
              onClick={() => setActiveTab(t)}
            >{t}</button>
          ))}
        </div>

        <div className="pkg-grid">
          {filtered.map(p => (
            <div
              key={p.name}
              className={`pkg-card ${selected === p.name ? 'pkg-card--selected' : ''}`}
              onClick={() => setSelected(p.name)}
            >
              <div className="pkg-card__img">
                <Image size={40} color="var(--text-muted)" />
              </div>
              <div className="pkg-card__info">
                <h3>{p.name}</h3>
                <span>{p.tag}</span>
                {p.hot && <span className="pkg-card__badge pkg-card__badge--hot">热门</span>}
                {p.svip && <span className="pkg-card__badge pkg-card__badge--svip">SVIP</span>}
              </div>
            </div>
          ))}
        </div>

        <div className="pkg-bottom">
          <button className="btn btn--outline-light" onClick={() => navigate('/makeup')}>上一步</button>
          <button
            className="btn btn--gold"
            disabled={!selected}
            onClick={() => navigate('/waiting')}
          >
            <Camera size={18} />
            开始拍摄
          </button>
        </div>
      </main>
    </div>
  )
}
