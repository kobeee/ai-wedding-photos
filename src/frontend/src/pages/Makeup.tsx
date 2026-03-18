import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { User } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import './Makeup.css'

const styles = [
  { id: 'natural', name: '素颜质感', desc: '保留自然状态\n真实清透', img: '/images/generated-1773759812646.png' },
  { id: 'refined', name: '精致新郎妆', desc: '轻度修饰提亮\n干净利落', img: '/images/generated-1773759932888.png' },
  { id: 'sculpt', name: '骨相微调', desc: '面部轮廓优化\n杂志封面感', img: '/images/generated-1773759970779.png' },
]

const brideStyles = [
  { id: 'natural', name: '素颜质感', desc: '清透自然\n原生美感', img: '/images/generated-1773760053899.png' },
  { id: 'refined', name: '精致新娘妆', desc: '柔光美肌\n优雅端庄', img: '/images/generated-1773760091146.png' },
  { id: 'sculpt', name: '骨相微调', desc: '面部轮廓精修\n高级感拉满', img: '/images/generated-1773760190993.png' },
]

export default function Makeup() {
  const navigate = useNavigate()
  const [groomStyle, setGroomStyle] = useState('natural')
  const [brideStyle, setBrideStyle] = useState('refined')

  return (
    <div className="makeup-page">
      <StepHeader current={2} onClose={() => navigate('/')} />
      <main className="makeup-main">
        <div className="makeup-title">
          <h1>哪一个是您今天想要的状态？</h1>
          <p>AI已根据您的照片生成三种妆造风格，请分别为新郎和新娘选择</p>
        </div>

        <div className="makeup-section">
          <div className="makeup-section__header">
            <User size={18} color="var(--accent-gold)" />
            <span>新郎妆造</span>
          </div>
          <div className="makeup-cards">
            {styles.map(s => (
              <div
                key={s.id}
                className={`makeup-card ${groomStyle === s.id ? 'makeup-card--selected' : ''}`}
                onClick={() => setGroomStyle(s.id)}
              >
                <div className="makeup-card__img" style={{ backgroundImage: `url(${s.img})` }} />
                <div className="makeup-card__info">
                  <h3>{s.name}</h3>
                  <p>{s.desc}</p>
                  {groomStyle === s.id && <span className="makeup-card__badge">已选择</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="makeup-section">
          <div className="makeup-section__header">
            <User size={18} color="var(--accent-gold)" />
            <span>新娘妆造</span>
          </div>
          <div className="makeup-cards">
            {brideStyles.map(s => (
              <div
                key={s.id}
                className={`makeup-card ${brideStyle === s.id ? 'makeup-card--selected' : ''}`}
                onClick={() => setBrideStyle(s.id)}
              >
                <div className="makeup-card__img" style={{ backgroundImage: `url(${s.img})` }} />
                <div className="makeup-card__info">
                  <h3>{s.name}</h3>
                  <p>{s.desc}</p>
                  {brideStyle === s.id && <span className="makeup-card__badge">已选择</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="makeup-bottom">
          <button className="btn btn--outline-light" onClick={() => navigate('/upload')}>上一步</button>
          <button className="btn btn--gold" onClick={() => navigate('/package')}>下一步：选择套餐</button>
        </div>
      </main>
    </div>
  )
}
