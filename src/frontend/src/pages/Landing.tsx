import { Link } from 'react-router-dom'
import { Sparkles, Check, ChevronDown } from 'lucide-react'
import Header from '../components/Header'
import './Landing.css'

const processSteps = [
  { num: '01', title: '上传日常照', desc: '男女双方各上传5张清晰日常照片，系统自动提取面部特征' },
  { num: '02', title: 'AI试妆间', desc: '三种妆造风格供你选择，找到最理想的自己' },
  { num: '03', title: '选择视觉套餐', desc: '像刷小红书一样浏览精美套餐，点击即选，无需输入任何文字' },
  { num: '04', title: 'AI拍摄中', desc: '沉浸式等待约30-60秒，AI正在为你布光、调色、抓拍' },
  { num: '05', title: '审片与交付', desc: '大图震撼呈现，支持换装重拍，一键下载8K无损大图' },
]

const featuredPackages = [
  { name: '极简高定棚拍', tag: '纯净光影 · 高级质感 · 20张精修', img: '/images/generated-1773678492426.png' },
  { name: '冰岛黑沙滩史诗', tag: '极地风光 · 史诗叙事 · 20张精修', img: '/images/generated-1773678527070.png' },
]

const allPackages = [
  [
    { name: '极简高定棚拍', tag: '纯净光影 · 高级质感 · 20张精修', img: '/images/generated-1773678545362.png' },
    { name: '冰岛黑沙滩史诗', tag: '极地风光 · 史诗叙事 · 20张精修', img: '/images/generated-1773678585370.png' },
    { name: '日系温泉旅拍', tag: '温泉和风 · 清新治愈 · 20张精修', img: '/images/generated-1773761406546.png' },
  ],
  [
    { name: '中式赛博朋克', tag: '霓虹国潮 · 未来东方 · 20张精修', img: '/images/generated-1773678610353.png' },
    { name: '法式街角胶片', tag: '复古胶片 · 浪漫街拍 · 20张精修', img: '/images/generated-1773678632534.png' },
    { name: '星空露营婚纱', tag: '星河璀璨 · 浪漫野奢 · 20张精修', img: '/images/generated-1773761362241.png' },
  ],
]

const plans = [
  {
    name: '免费体验', price: '¥0', period: '',
    desc: '1张带水印标清图\n体验AI婚纱摄影的魔力',
    features: ['1张标清带水印成片', '体验完整AI拍摄流程', '3种妆造风格试妆'],
    cta: '免费开始', primary: false,
  },
  {
    name: '基础套餐', price: '¥99', period: '/ ¥199',
    desc: '20张4K精修成片\n+ 2张8K海报级输出',
    features: ['20张4K精修无水印成片', '2张8K海报级超清输出', '解锁指定主题套餐', 'AI试妆 + 魔法笔刷微调'],
    cta: '立即购买', primary: true, highlight: true,
  },
  {
    name: 'SVIP 无限畅拍', price: '¥599', period: '/ 季度',
    desc: '全站解锁 + 无限重绘\n极端场景全部畅享',
    features: ['全站所有视觉套餐解锁', '无限次局部重绘修改', '星空/水下/特效等极端场景', '8K超清输出 + 实体冲印折扣'],
    cta: '开通 SVIP', primary: true, badge: '最受欢迎',
  },
]

const faqs = [
  { q: '生成的照片和真人像吗？', a: '我们采用Face-ID特征提取技术，确保生成的照片100%忠于您的五官特征。同时提供三档美化选择，您可以自由决定理想状态。' },
  { q: '生成一套照片需要多长时间？', a: '单张照片生成约30-60秒。我们的AI管线会自动进行质检和修复，确保每一张都是精品，无需您反复挑选废片。' },
  { q: '我的照片数据安全吗？', a: '绝对安全。您上传的照片和生成的面部特征数据将在24小时内自动销毁，我们承诺不会用于任何其他用途。' },
  { q: '可以用于实体冲印吗？', a: '当然可以。我们提供8K超分辨率输出，完全满足大幅面冲印需求。还可直接在平台一键下单相册、挂画、迎宾海报等实体产品。' },
]

export default function Landing() {
  return (
    <div className="landing">
      <Header />

      <section className="hero">
        <div className="hero__overlay" />
        <div className="hero__content">
          <div className="hero__badge">
            <Sparkles size={14} />
            <span>AI驱动 · 影楼级品质</span>
          </div>
          <h1>把最完美的数字记忆<br />留给最重要的人</h1>
          <p className="hero__sub">
            零门槛 AI 婚纱摄影，一杯咖啡的时间，获取影楼级4K/8K画质大片。<br />
            无需摆拍，无需修图，AI为你定制专属视觉记忆。
          </p>
          <div className="hero__buttons">
            <Link to="/upload" className="btn btn--gold">免费体验一张</Link>
            <a href="#gallery" className="btn btn--outline">查看作品集</a>
          </div>
        </div>
      </section>

      <section className="process" id="process">
        <span className="section-label">像点外卖一样简单</span>
        <h2 className="section-title">五步，从日常照到婚纱大片</h2>
        <p className="section-sub">全流程隐藏技术参数，你只需要做选择</p>
        <div className="process__steps">
          {processSteps.map((s) => (
            <div key={s.num} className="process__card">
              <div className="process__num">{s.num}</div>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="featured" id="gallery">
        <span className="section-label">精选推荐</span>
        <h2 className="section-title">最受欢迎的两组视觉方案</h2>
        <p className="section-sub">超过 80% 的用户选择了这两套方案</p>
        <div className="featured__grid">
          {featuredPackages.map((p) => (
            <div key={p.name} className="featured__card">
              <div className="featured__img" style={{ backgroundImage: `url(${p.img})` }} />
              <div className="featured__info">
                <h3>{p.name}</h3>
                <span>{p.tag}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="gallery">
        <span className="section-label">全部套餐</span>
        <h2 className="section-title">找到属于你们的视觉故事</h2>
        <p className="section-sub">8 种风格，从极简棚拍到冰岛史诗，总有一款属于你们</p>
        {allPackages.map((row, ri) => (
          <div key={ri} className="gallery__row">
            {row.map((p) => (
              <div key={p.name} className="gallery__card">
                <div className="gallery__img" style={{ backgroundImage: `url(${p.img})` }} />
                <div className="gallery__info">
                  <h3>{p.name}</h3>
                  <span>{p.tag}</span>
                </div>
              </div>
            ))}
          </div>
        ))}
      </section>

      <section className="pricing" id="pricing">
        <span className="section-label">选择你的方案</span>
        <h2 className="section-title">从免费体验到无限畅拍</h2>
        <div className="pricing__cards">
          {plans.map((p) => (
            <div key={p.name} className={`pricing__card${p.highlight ? ' pricing__card--highlight' : ''}${p.badge ? ' pricing__card--svip' : ''}`}>
              <div className="pricing__top">
                <span className={`pricing__name${p.highlight || p.badge ? ' pricing__name--gold' : ''}`}>{p.name}</span>
                {p.badge && <span className="pricing__badge">{p.badge}</span>}
              </div>
              <div className="pricing__price">
                <span className={`pricing__amount${p.highlight || p.badge ? ' pricing__amount--gold' : ''}`}>{p.price}</span>
                {p.period && <span className="pricing__period">{p.period}</span>}
              </div>
              <p className="pricing__desc">{p.desc}</p>
              <ul className="pricing__features">
                {p.features.map((f) => (
                  <li key={f}><Check size={16} color="var(--accent-gold)" />{f}</li>
                ))}
              </ul>
              <button className={`btn ${p.primary ? 'btn--gold' : 'btn--outline'} btn--full`}>
                {p.cta}
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="faq" id="faq">
        <h2 className="section-title faq__title">常见问题</h2>
        <p className="section-sub">关于AI婚纱摄影，你可能想知道的</p>
        <div className="faq__list">
          {faqs.map((f, i) => (
            <details key={i} className="faq__item">
              <summary>
                <span>{f.q}</span>
                <ChevronDown size={20} color="var(--text-muted)" />
              </summary>
              <p>{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="final-cta">
        <h2>准备好拥有你们的<br />专属数字婚纱大片了吗？</h2>
        <p>上传日常照，30秒后见证奇迹</p>
        <div className="final-cta__buttons">
          <Link to="/upload" className="btn btn--gold btn--lg">免费体验一张</Link>
          <a href="#faq" className="btn btn--outline btn--lg">了解更多</a>
        </div>
        <span className="final-cta__trust">无需注册  ·  免费体验  ·  24小时数据自动销毁</span>
      </section>

      <footer className="footer">
        <div className="footer__top">
          <div className="footer__brand">
            <span className="footer__logo">LUMIÈRE STUDIO</span>
            <span>把最完美的数字记忆，留给最重要的人</span>
          </div>
          <div className="footer__nav">
            <h4>产品</h4>
            <a href="#gallery">视觉套餐</a>
            <a href="#pricing">价格方案</a>
            <a href="#gallery">作品展示</a>
          </div>
          <div className="footer__nav">
            <h4>支持</h4>
            <a href="#faq">常见问题</a>
            <a href="#">联系我们</a>
            <a href="#">实体冲印</a>
          </div>
          <div className="footer__nav">
            <h4>法律</h4>
            <a href="#">隐私协议</a>
            <a href="#">用户条款</a>
            <a href="#">数据安全</a>
          </div>
        </div>
        <div className="footer__divider" />
        <p className="footer__copy">© 2026 Lumière Studio. All rights reserved.</p>
      </footer>
    </div>
  )
}
