import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { getSession } from './api/client'
import Layout from './components/Layout'
import Analytics from './pages/Analytics'
import ControlTower from './pages/ControlTower'
import DemoGuide from './pages/DemoGuide'
import Documents from './pages/Documents'
import GateSlots from './pages/GateSlots'
import CustomerPortal from './pages/CustomerPortal'
import Login from './pages/Login'
import ShipmentDetail from './pages/ShipmentDetail'
import TransporterPortal from './pages/TransporterPortal'
import WarRoom from './pages/WarRoom'

const HOME: Record<string, string> = { COORDINATOR: '/tower', CUSTOMER: '/customer', TRANSPORTER: '/driver' }

// The UI hides pages by role, but the real access control is enforced by the API on every request.
function Guard({ role, children }: { role: string; children: ReactNode }) {
  const s = getSession()
  if (!s) return <Navigate to="/login" replace />
  if (s.user.role !== role) return <Navigate to={HOME[s.user.role]} replace />
  return <Layout>{children}</Layout>
}

function Home() {
  const s = getSession()
  return <Navigate to={s ? HOME[s.user.role] : '/login'} replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/tower" element={<Guard role="COORDINATOR"><ControlTower /></Guard>} />
        <Route path="/shipments/:id" element={<Guard role="COORDINATOR"><ShipmentDetail /></Guard>} />
        <Route path="/shipments/:id/war-room" element={<Guard role="COORDINATOR"><WarRoom /></Guard>} />
        <Route path="/gate" element={<Guard role="COORDINATOR"><GateSlots /></Guard>} />
        <Route path="/documents" element={<Guard role="COORDINATOR"><Documents /></Guard>} />
        <Route path="/demo" element={<Guard role="COORDINATOR"><DemoGuide /></Guard>} />
        <Route path="/analytics" element={<Guard role="COORDINATOR"><Analytics /></Guard>} />
        <Route path="/customer" element={<Guard role="CUSTOMER"><CustomerPortal /></Guard>} />
        <Route path="/driver" element={<Guard role="TRANSPORTER"><TransporterPortal /></Guard>} />
        <Route path="*" element={<Home />} />
      </Routes>
    </BrowserRouter>
  )
}
