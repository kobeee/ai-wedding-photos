import { Link } from 'react-router-dom'
import { Sparkles, Check, ChevronDown } from 'lucide-react'
import Header from '../components/Header'
import { clearWorkflowState } from '../lib/workflow'
import './Landing.css'

const processSteps = [
  { num: '01', title: '上传日常照', desc: '男女双方各上传5张清晰日常照片，系统自动提取面部特征' },
  { num: '02', title: 'AI试妆间', desc: '三种妆造风格供你选择，找到最理想的自己' },
  { num: '03', title: '选主题 + 选 SKU', desc: '先定视觉故事，再确认本单承诺的张数、保留期和重拍额度' },
  { num: '04', title: '支付并启动履约', desc: '订单支付成功后再进入生成，等待的是正式交付而不是试玩任务' },
  { num: '05', title: '订单交付页', desc: '按订单查看已交付张数、下载 4K 成片，并继续发起重拍或售后' },
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
    desc: '3张体验样片\n先确认风格与质感',
    features: ['3 张体验样片', '完整试妆与下单流程', '1 天结果保留期'],
    cta: '免费开始', primary: false,
  },
  {
    name: '记忆典藏', price: '¥699', period: '',
    desc: '5 景 / 40 张 4K\n当前唯一主推款',
    features: ['40 张 4K 成片交付', '5 组场景叙事', '2 次重拍额度', '30 天结果保留期'],
    cta: '立即购买', primary: true, highlight: true,
  },
  {
    name: '档案珍藏', price: '¥999', period: '',
    desc: '7 景 / 56 张 4K\n完整档案级交付',
    features: ['56 张 4K 成片交付', '7 组场景叙事', '3 次重拍额度', '适合完整婚礼档案'],
    cta: '查看方案', primary: true, badge: '高阶',
  },
]

const faqs = [
  { q: '生成的照片和真人像吗？', a: '我们采用Face-ID特征提取技术，确保生成的照片100%忠于您的五官特征。同时提供三档美化选择，您可以自由决定理想状态。' },
  { q: '支付后多久能看到结果？', a: '订单支付成功后才会进入正式履约。系统会按批次生成与质检，体验单通常在几分钟内完成，正式套餐会根据承诺张数持续交付。' },
  { q: '我的照片数据安全吗？', a: '绝对安全。您上传的照片和生成的面部特征数据将在24小时内自动销毁，我们承诺不会用于任何其他用途。' },
  { q: '可以用于实体冲印吗？', a: '当前首版对外交付口径统一为 4K 成片，已经足够覆盖大多数线上展示与常规冲印场景。更高规格与实体冲印会在后续版本继续补齐。' },
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
            <Link to="/upload" className="btn btn--gold" onClick={clearWorkflowState}>免费体验一张</Link>
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
          <Link to="/upload" className="btn btn--gold btn--lg final-cta__primary" onClick={clearWorkflowState}>免费试拍</Link>
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
