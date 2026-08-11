import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App'
import { setLocale } from './i18n'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

describe('staff placeholder', () => {
  it('renders the login page', async () => {
    await setLocale('en')
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/login']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText('HMSv2')).toBeInTheDocument()
    expect(screen.getByText('Clinic staff workspace')).toBeInTheDocument()
  })
})
