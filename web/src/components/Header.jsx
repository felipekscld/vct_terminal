function Header({ warning }) {
  if (!warning) return null
  return (
    <header className="panel p-3">
      <p className="text-sm text-red-600">{warning}</p>
    </header>
  )
}

export default Header
