import { Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import PlanSelect from './pages/PlanSelect'
import SceneSelect from './pages/SceneSelect'
import Upload from './pages/Upload'
import Makeup from './pages/Makeup'
import Waiting from './pages/Waiting'
import Delivery from './pages/Delivery'
import Orders from './pages/Orders'
import PayResult from './pages/PayResult'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/plan" element={<PlanSelect />} />
      <Route path="/scenes" element={<SceneSelect />} />
      <Route path="/upload" element={<Upload />} />
      <Route path="/makeup" element={<Makeup />} />
      <Route path="/waiting/:orderId?" element={<Waiting />} />
      <Route path="/delivery/:orderId" element={<Delivery />} />
      <Route path="/orders" element={<Orders />} />
      <Route path="/pay/result" element={<PayResult />} />
    </Routes>
  )
}
