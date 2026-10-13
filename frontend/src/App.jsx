import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from './ui.jsx'
import Home from './screens/Home.jsx'

const Customer = lazy(() => import('./screens/Customer.jsx'))
const Owner = lazy(() => import('./screens/Owner.jsx'))
const Mechanic = lazy(() => import('./screens/Mechanic.jsx'))
const Lab3D = import.meta.env.DEV || import.meta.env.VITE_DEMO === '1' ? lazy(() => import('./vehicle3d/Lab.jsx')) : null

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Suspense fallback={<div className="center" style={{ minHeight: '100dvh' }}><span className="spinner" /></div>}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/j/:token" element={<Customer />} />
            <Route path="/owner/*" element={<Owner />} />
            <Route path="/mechanic/*" element={<Mechanic />} />
            {Lab3D && <Route path="/preview/3d" element={<Lab3D />} />}
            <Route path="*" element={<Home />} />
          </Routes>
        </Suspense>
      </ToastProvider>
    </BrowserRouter>
  )
}
