import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/parlays', label: 'Parlays entre jogos' },
  { to: '/stats', label: 'Estatísticas' },
  { to: '/settings', label: 'Configurações' }
]

function Sidebar() {
  return (
    <aside className="panel sticky top-4 hidden h-fit w-64 flex-col p-4 md:flex">
      <nav className="space-y-2">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `block rounded-xl px-3 py-2 text-sm font-semibold transition ${
                isActive ? 'bg-ocean text-white' : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`
            }
            end
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

export default Sidebar
