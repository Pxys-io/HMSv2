import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/client', () => ({
  get: vi.fn(async (path: string) => {
    if (path.startsWith('/api/icd10?q=diabet')) {
      return {
        items: [
          { code: 'E11', label_en: 'Type 2 diabetes', label_ar: 'سكري النوع الثاني' },
          { code: 'I10', label_en: 'Essential hypertension', label_ar: null },
        ],
      }
    }
    return { items: [] }
  }),
}))

import { Icd10Picker } from './ExamPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

function renderPicker(onPick: (label: string, kind: 'dd' | 'final') => void) {
  return render(
    <QueryClientProvider client={queryClient}>
      <Icd10Picker onPick={onPick} />
    </QueryClientProvider>,
  )
}

describe('Icd10Picker', () => {
  beforeEach(() => {
    queryClient.clear()
  })

  it('offers DD and Final directly on each result row', async () => {
    const onPick = vi.fn()
    renderPicker(onPick)

    const input = screen.getByPlaceholderText('ICD-10 search…')
    await userEvent.type(input, 'diabet')

    await waitFor(() => {
      expect(screen.getByText(/Type 2 diabetes/)).toBeInTheDocument()
    })

    // One click per action — no second step (first row = E11)
    await userEvent.click(screen.getAllByRole('button', { name: 'DD' })[0])
    // the picker closes after a pick; type again to reopen and pick Final
    await userEvent.type(input, 'diabet')
    await userEvent.click(screen.getAllByRole('button', { name: 'Final' })[0])

    expect(onPick).toHaveBeenCalledTimes(2)
    expect(onPick).toHaveBeenNthCalledWith(1, 'Type 2 diabetes (E11)', 'dd')
    expect(onPick).toHaveBeenNthCalledWith(2, 'Type 2 diabetes (E11)', 'final')
  })

  it('shows the empty state when nothing matches', async () => {
    const onPick = vi.fn()
    renderPicker(onPick)
    const input = screen.getByPlaceholderText('ICD-10 search…')
    await userEvent.type(input, 'xyzzz')
    await waitFor(() => {
      expect(screen.getByText('No ICD-10 matches')).toBeInTheDocument()
    })
  })
})
