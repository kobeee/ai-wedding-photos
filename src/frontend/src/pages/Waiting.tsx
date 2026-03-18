import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Aperture, CircleCheck, Loader, Circle } from 'lucide-react'
import './Waiting.css'

const messages = [
  '正在为您布置法式街角的灯光...',
  '正在调整新娘的头纱质感...',
  '摄影师正在抓拍最完美的笑容...',
  '正在进行AI质检与修复...',
  '即将完成，请稍候...',
]

const steps = [
  '数字人特征提取完成',
  '摄影参数编译完成',
  '正在渲染4K底图...',
  'AI质检与修复',
]

export default function Waiting() {
  const navigate = useNavigate()
  const [progress, setProgress] = useState(62)
  const [msgIdx, setMsgIdx] = useState(0)
  const [currentStep, setCurrentStep] = useState(2)

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined
    const starter = setTimeout(() => {
      timer = setInterval(() => {
        setProgress(p => {
          if (p >= 100) {
            if (timer) {
              clearInterval(timer)
            }
            setTimeout(() => navigate('/review'), 500)
            return 100
          }
          return p + 2
        })
      }, 120)
    }, 1800)

    return () => {
      clearTimeout(starter)
      if (timer) {
        clearInterval(timer)
      }
    }
  }, [navigate])

  useEffect(() => {
    const timer = setInterval(() => {
      setMsgIdx(i => (i + 1) % messages.length)
    }, 3000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (progress < 25) setCurrentStep(0)
    else if (progress < 50) setCurrentStep(1)
    else if (progress < 80) setCurrentStep(2)
    else setCurrentStep(3)
  }, [progress])

  return (
    <div className="waiting-page">
      <div className="waiting-center">
        <div className="waiting-ring">
          <Aperture size={60} color="var(--accent-gold)" />
        </div>
        <div className="waiting-texts">
          <h1>{messages[msgIdx]}</h1>
          <p>AI摄影师正在全力创作，请稍候片刻</p>
        </div>
        <div className="waiting-progress">
          <div className="waiting-bar">
            <div className="waiting-bar__fill" style={{ width: `${progress}%` }} />
          </div>
          <span>{progress}%</span>
        </div>
        <div className="waiting-steps">
          {steps.map((s, i) => (
            <div key={i} className="waiting-step">
              {i < currentStep ? (
                <CircleCheck size={16} color="var(--accent-gold)" />
              ) : i === currentStep ? (
                <Loader size={16} color="var(--accent-gold)" className="waiting-spin" />
              ) : (
                <Circle size={16} color="var(--text-muted)" />
              )}
              <span className={i <= currentStep ? 'waiting-step--active' : ''}>{s}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
