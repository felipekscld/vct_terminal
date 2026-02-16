import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import App from './App'

vi.mock('./api/client', () => ({
  api: {
    getConfig: vi.fn().mockResolvedValue({
      bankroll: { total: 1000 },
      data_filter: { description: 'all data (no filters)' }
    })
  }
}))

describe('App shell', () => {
  it('renders dashboard label', async () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>
    )

    expect(await screen.findByText(/Dashboard/i)).toBeInTheDocument()
  })
})
