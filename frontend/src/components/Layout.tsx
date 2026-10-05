import { NavLink, Outlet } from 'react-router-dom'
import { WalletButton } from './WalletButton'

export function Layout() {
  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="header-inner">
          <NavLink className="brand" to="/submit" aria-label="ClearCredit home">
            <span className="brand-mark" aria-hidden="true">C</span>
            <span><strong>Clear</strong>Credit</span>
          </NavLink>
          <nav className="main-nav" aria-label="Main navigation">
            <NavLink to="/submit">Submit</NavLink>
            <NavLink to="/verify">Verify</NavLink>
            <NavLink to="/registry">Registry</NavLink>
            <NavLink to="/about">About</NavLink>
          </nav>
          <WalletButton />
        </div>
      </header>
      <main className="page-shell"><Outlet /></main>
      <footer className="site-footer">
        <span>ClearCredit · IEEE ClimateChain</span>
        <span>Integrity evidence, not certification.</span>
      </footer>
    </div>
  )
}
