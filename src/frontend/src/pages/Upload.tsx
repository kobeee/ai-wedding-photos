import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CloudUpload, User } from 'lucide-react'
import StepHeader from '../components/StepHeader'
import './Upload.css'

export default function Upload() {
  const navigate = useNavigate()
  const [maleFiles, setMaleFiles] = useState<File[]>([])
  const [femaleFiles, setFemaleFiles] = useState<File[]>([])

  const handleDrop = (setter: typeof setMaleFiles) => (e: React.DragEvent) => {
    e.preventDefault()
    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'))
    setter(prev => [...prev, ...files])
  }

  const handleFileSelect = (setter: typeof setMaleFiles) => (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setter(prev => [...prev, ...Array.from(e.target.files!)])
    }
  }

  return (
    <div className="upload-page">
      <StepHeader current={1} onClose={() => navigate('/')} />
      <main className="upload-main">
        <div className="upload-title">
          <h1>欢迎来到您的私人数字影棚</h1>
          <p>请分别上传男女双方各5-10张高清日常照片</p>
        </div>
        <div className="upload-cards">
          {[
            { label: '新郎', files: maleFiles, setter: setMaleFiles },
            { label: '新娘', files: femaleFiles, setter: setFemaleFiles },
          ].map(({ label, files, setter }) => (
            <div key={label} className="upload-card">
              <div className="upload-card__label">
                <User size={20} color="var(--accent-gold)" />
                <span>{label}</span>
              </div>
              <div
                className="upload-card__dropzone"
                onDragOver={e => e.preventDefault()}
                onDrop={handleDrop(setter)}
              >
                {files.length > 0 ? (
                  <div className="upload-card__previews">
                    {files.map((f, i) => (
                      <div key={i} className="upload-card__thumb">
                        <img src={URL.createObjectURL(f)} alt="" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <>
                    <CloudUpload size={48} color="var(--text-muted)" />
                    <p>拖拽照片到这里<br />或点击上传</p>
                    <label className="upload-card__btn">
                      选择文件
                      <input type="file" accept="image/*" multiple hidden onChange={handleFileSelect(setter)} />
                    </label>
                  </>
                )}
              </div>
              <span className="upload-card__hint">
                支持 JPG/PNG，单张不超过 10MB<br />建议上传正面、侧面、全身等不同角度
              </span>
            </div>
          ))}
        </div>
        <div className="upload-bottom">
          <button className="btn btn--gold" onClick={() => navigate('/makeup')}>
            下一步：AI试妆
          </button>
        </div>
      </main>
    </div>
  )
}
