import { Routes, Route } from 'react-router-dom'
import Nav     from './components/Nav'
import Catalog from './pages/Catalog'
import Advisor from './pages/Advisor'
import Evals   from './pages/Evals'
import Login   from './pages/Login'

export default function App() {
  return (
    <div className="app">
      <Nav />
      <main className="main-content">
        <Routes>
          <Route path="/"        element={<Catalog />} />
          <Route path="/advisor" element={<Advisor />} />
          <Route path="/evals"   element={<Evals />} />
          <Route path="/login"   element={<Login />} />
        </Routes>
      </main>
    </div>
  )
}
