import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import App from './App'
import { setLocale } from './i18n'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

describe('public placeholder', () => {
  it('renders the site title', async () => {
    await setLocale('en')
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getAllByText(/Book your appointment|احجز موعدك/).length).toBeGreaterThan(0)
  })
})
