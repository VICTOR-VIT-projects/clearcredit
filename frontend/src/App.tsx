import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { LoadingBlock } from './components/Inline'

const AboutPage = lazy(() => import('./pages/AboutPage').then((module) => ({ default: module.AboutPage })))
const RegistryPage = lazy(() => import('./pages/RegistryPage').then((module) => ({ default: module.RegistryPage })))
const RetirementPage = lazy(() => import('./pages/RetirementPage').then((module) => ({ default: module.RetirementPage })))
const SubmitPage = lazy(() => import('./pages/SubmitPage').then((module) => ({ default: module.SubmitPage })))
const VerifyPage = lazy(() => import('./pages/VerifyPage').then((module) => ({ default: module.VerifyPage })))

export default function App() {
  return (
    <Suspense fallback={<div className="page"><LoadingBlock>Loading page…</LoadingBlock></div>}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/submit" replace />} />
          <Route path="submit" element={<SubmitPage />} />
          <Route path="verify" element={<VerifyPage />} />
          <Route path="verify/:ref" element={<VerifyPage />} />
          <Route path="registry" element={<RegistryPage />} />
          <Route path="retirements" element={<RetirementPage />} />
          <Route path="retirements/:ref/:serial" element={<RetirementPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="*" element={<Navigate to="/submit" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
