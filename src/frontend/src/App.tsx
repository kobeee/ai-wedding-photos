import { Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import Upload from './pages/Upload'
import Makeup from './pages/Makeup'
import PackageSelect from './pages/PackageSelect'
import Waiting from './pages/Waiting'
import Review from './pages/Review'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/upload" element={<Upload />} />
      <Route path="/makeup" element={<Makeup />} />
      <Route path="/package" element={<PackageSelect />} />
      <Route path="/waiting" element={<Waiting />} />
      <Route path="/review" element={<Review />} />
    </Routes>
  )
}
