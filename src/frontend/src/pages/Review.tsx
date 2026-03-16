import { useNavigate } from 'react-router-dom'
import { Aperture, Image, Download, RefreshCw, Printer, Shirt, Eraser, Paintbrush, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import './Review.css'

export default function Review() {
  const navigate = useNavigate()

  return (
    <div className="review-page">
      <header className="review-header">
        <Link to="/" className="review-header__logo">
          <Aperture size={22} color="var(--accent-gold)" />
          <span>LUMIÈRE STUDIO</span>
        </Link>
        <span className="review-header__title">审片与交付</span>
        <button onClick={() => navigate('/')} aria-label="关闭">
          <X size={24} color="var(--text-muted)" />
        </button>
      </header>

      <main className="review-main">
        <div className="review-preview">
          <Image size={80} color="var(--text-muted)" />
          <span>AI生成的婚纱大片</span>
        </div>

        <aside className="review-panel">
          <div className="review-panel__top">
            <div className="review-info">
              <h2>法式街角胶片 · 第 3 张</h2>
              <span>4K · 3840×2560 · 8.2MB</span>
            </div>

            <div className="review-thumbs">
              <span className="review-thumbs__label">本组共 6 张</span>
              <div className="review-thumbs__row">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className={`review-thumb ${i === 2 ? 'review-thumb--active' : ''}`} />
                ))}
              </div>
            </div>

            <div className="review-magic">
              <span className="review-magic__label">魔法笔刷</span>
              <div className="review-magic__btns">
                <button><Shirt size={14} />换装</button>
                <button><Eraser size={14} />消除</button>
                <button><Paintbrush size={14} />重绘</button>
              </div>
            </div>
          </div>

          <div className="review-actions">
            <button className="btn btn--gold btn--full">
              <Download size={16} />下载 8K 大图
            </button>
            <button className="btn btn--outline-light btn--full">
              <RefreshCw size={16} />再拍一张
            </button>
            <button className="btn btn--outline-light btn--full">
              <Printer size={16} />去冲印
            </button>
          </div>
        </aside>
      </main>
    </div>
  )
}
