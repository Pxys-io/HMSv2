import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import App from './App'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

describe('staff placeholder', () => {
  it('renders the workspace title', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )
    expect(screen.getByText('HMSv2 Staff')).toBeInTheDocument()
  })
})
