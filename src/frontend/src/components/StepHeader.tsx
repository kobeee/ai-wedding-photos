import { Check, X, Aperture } from 'lucide-react'
import { Link } from 'react-router-dom'
import './StepHeader.css'

const steps = ['选套餐', '选景', '上传', '妆造', '等待', '交付']

interface Props {
  current: number // 1-based
  onClose?: () => void
}

export default function StepHeader({ current, onClose }: Props) {
  return (
    <header className="step-header">
      <Link to="/" className="step-header__logo">
        <Aperture size={22} color="var(--accent-gold)" />
        <span>LUMIÈRE STUDIO</span>
      </Link>
      <div className="step-header__steps">
        {steps.map((label, i) => {
          const stepNum = i + 1
          const done = stepNum < current
          const active = stepNum === current
          const upcoming = stepNum > current
          return (
            <div
              key={i}
              className={`step-header__step-group ${i === steps.length - 1 ? 'step-header__step-group--last' : ''}`}
            >
              <div className="step-header__step">
                <div
                  className={[
                    'step-header__num',
                    done || active ? 'step-header__num--active' : '',
                    upcoming ? 'step-header__num--upcoming' : '',
                  ].join(' ').trim()}
                >
                  {done ? <Check size={12} /> : stepNum}
                </div>
                <span className={done || active ? 'step-header__label--active' : ''}>{label}</span>
              </div>
              {i < steps.length - 1 && (
                <div className={`step-header__line ${stepNum < current ? 'step-header__line--active' : ''}`} />
              )}
            </div>
          )
        })}
      </div>
      <button className="step-header__close" onClick={onClose} aria-label="关闭">
        <X size={24} color="var(--text-muted)" />
      </button>
    </header>
  )
}
