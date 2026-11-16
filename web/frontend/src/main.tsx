import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, RequireUser } from './auth'
import Shell from './components/Shell'
import Accounts from './pages/Accounts'
import ChangePassword from './pages/ChangePassword'
import Keys from './pages/Keys'
import Overview from './pages/Overview'
import Sensors from './pages/Sensors'
import Setup from './pages/Setup'
import SignIn from './pages/SignIn'
import './styles.css'

function Inside({ children, admin = false }: { children: React.ReactNode; admin?: boolean }) {
  return <RequireUser admin={admin}><Shell>{children}</Shell></RequireUser>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/setup" element={<Setup />} />
          <Route path="/" element={<Inside><Overview /></Inside>} />
          <Route path="/sensors" element={<Inside><Sensors /></Inside>} />
          <Route path="/account/password" element={<Inside><ChangePassword /></Inside>} />
          <Route path="/admin/accounts" element={<Inside admin><Accounts /></Inside>} />
          <Route path="/admin/keys" element={<Inside admin><Keys /></Inside>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
