import { useState } from 'react'
import Login from './components/Login'
import Dashboard from './components/Dashboard'

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('psx_token'))

  function handleLogin(newToken) {
    localStorage.setItem('psx_token', newToken)  // sync — must happen before re-render
    setToken(newToken)
  }

  function handleLogout() {
    localStorage.removeItem('psx_token')
    setToken(null)
  }

  if (!token) return <Login onLogin={handleLogin} />
  return <Dashboard onLogout={handleLogout} />
}
