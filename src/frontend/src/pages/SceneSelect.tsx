import { startTransition, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, Map } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import { fetchScenes, type SceneInfo } from '../lib/api'
import { getWorkflowState, updateWorkflowState } from '../lib/workflow'
import './SceneSelect.css'

const categoryLabels: Record<string, string> = {
  western: '西式',
  chinese: '中式',
  travel: '旅拍',
  studio: '影棚',
  night: '夜景',
  fantasy: '幻想',
}

export default function SceneSelect() {
  const navigate = useNavigate()
  const workflow = getWorkflowState()
  const [scenes, setScenes] = useState<SceneInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set(workflow.selectedSceneIds || []))
  const [error, setError] = useState('')

  const maxScenes = workflow.selectedSku?.sceneCount
    ?? (workflow.selectedSku?.price === 0 ? 1 : 5)

  useEffect(() => {
    if (!workflow.selectedSku) {
      startTransition(() => {
        navigate('/plan')
      })
      return
    }

    let cancelled = false

    async function load() {
      try {
        const payload = await fetchScenes()
        if (cancelled) {
          return
        }
        setScenes(payload.items.filter(s => s.active))
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : '场景加载失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [navigate, workflow.selectedSku])

  const toggleScene = (sceneId: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(sceneId)) {
        next.delete(sceneId)
      } else {
        if (next.size >= maxScenes) {
          return prev
        }
        next.add(sceneId)
      }
      return next
    })
    setError('')
  }

  const handleContinue = () => {
    if (selected.size === 0) {
      setError('请至少选择一个场景')
      return
    }

    updateWorkflowState({
      selectedSceneIds: Array.from(selected),
    })

    startTransition(() => {
      navigate('/upload')
    })
  }

  const grouped = scenes.reduce<Record<string, SceneInfo[]>>((acc, scene) => {
    const cat = scene.category
    if (!acc[cat]) {
      acc[cat] = []
    }
    acc[cat].push(scene)
    return acc
  }, {})

  if (loading) {
    return (
      <div className="scene-page">
        <StepHeader current={2} onClose={() => navigate('/')} />
        <main className="scene-main">
          <div className="scene-loading">正在加载场景...</div>
        </main>
      </div>
    )
  }

  return (
    <div className="scene-page">
      <StepHeader current={2} onClose={() => navigate('/')} />

      <main className="scene-main">
        <section className="scene-hero">
          <div className="scene-hero__eyebrow">
            <Map size={14} />
            <span>选择拍摄场景</span>
          </div>
          <h1>找到属于你们的视觉故事</h1>
          <p>
            当前方案「{workflow.selectedSku?.name}」最多可选 {maxScenes} 个场景，
            已选 {selected.size} / {maxScenes}
          </p>
        </section>

        {Object.entries(grouped).map(([category, items]) => (
          <section key={category} className="scene-group">
            <h2 className="scene-group__title">{categoryLabels[category] || category}</h2>
            <div className="scene-grid">
              {items.map(scene => {
                const isSelected = selected.has(scene.scene_id)
                const isDisabled = !isSelected && selected.size >= maxScenes
                return (
                  <button
                    key={scene.scene_id}
                    type="button"
                    className={`scene-card${isSelected ? ' scene-card--active' : ''}${isDisabled ? ' scene-card--disabled' : ''}`}
                    onClick={() => toggleScene(scene.scene_id)}
                    disabled={isDisabled}
                  >
                    <div
                      className="scene-card__img"
                      style={{
                        backgroundImage: scene.preview_url ? `url(${scene.preview_url})` : undefined,
                        background: scene.preview_url ? undefined : 'linear-gradient(135deg, #1a1816, #2a2622)',
                      }}
                    />
                    <div className="scene-card__body">
                      <h3>{scene.name}</h3>
                      <span className="scene-card__desc">{scene.description}</span>
                    </div>
                    {isSelected && (
                      <div className="scene-card__check">
                        <CheckCircle2 size={20} color="var(--accent-gold)" />
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          </section>
        ))}

        {error && <div className="scene-error">{error}</div>}

        <div className="scene-bottom">
          <button className="btn btn--outline-light" onClick={() => navigate('/plan')}>上一步</button>
          <button className="btn btn--gold" onClick={handleContinue} disabled={selected.size === 0}>
            下一步：上传照片（{selected.size}/{maxScenes}）
          </button>
        </div>
      </main>
    </div>
  )
}
