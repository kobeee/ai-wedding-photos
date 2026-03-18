import { Aperture } from 'lucide-react'
import { Link } from 'react-router-dom'
import './Header.css'

export default function Header({ variant = 'landing' }: { variant?: 'landing' | 'app' }) {
  if (variant === 'app') {
    return (
      <header className="header header--app">
        <Link to="/" className="header__logo">
          <Aperture size={22} color="var(--accent-gold)" />
          <span>LUMIÈRE STUDIO</span>
        </Link>
      </header>
    )
  }

  return (
    <header className="header">
      <Link to="/" className="header__logo">
        <Aperture size={22} color="var(--accent-gold)" />
        <span>LUMIÈRE STUDIO</span>
      </Link>
      <nav className="header__nav">
        <a href="#process">关于我们</a>
        <a href="#gallery">作品集</a>
        <a href="#pricing">套餐</a>
        <a href="#faq">常见问题</a>
      </nav>
      <Link to="/upload" className="header__cta">开始创作</Link>
    </header>
  )
}
