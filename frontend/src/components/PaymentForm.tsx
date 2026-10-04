import { useState } from 'react'
import type { Loan } from '../types'
import { createTransaction, errorMessage } from '../api/client'
import Tooltip from './Tooltip'

interface Props {
  loan: Loan
  onPaymentAdded: () => void
}

type Kind = 'payment' | 'draw'

export default function PaymentForm({ loan, onPaymentAdded }: Props) {
  // Default to recording a draw while the loan is still in its borrowing phase
  const [kind, setKind] = useState<Kind>(loan.in_borrowing_phase ? 'draw' : 'payment')
  const [date, setDate] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Blank amount uses the regular payment, or the planned draw for draws
  const defaultAmount = kind === 'payment' ? loan.regular_payment : loan.planned_draw_amount
  const effectiveAmount = amount !== '' ? parseFloat(amount) : defaultAmount

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!date) return
    if (!(effectiveAmount > 0)) {
      setError('Enter an amount greater than 0.')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await createTransaction({
        loan_id: loan.id,
        date,
        // negative = payment, positive = draw (disbursement)
        amount: kind === 'payment' ? -Math.abs(effectiveAmount) : Math.abs(effectiveAmount),
        description: description || undefined,
      })
      setAmount('')
      setDescription('')
      onPaymentAdded()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const formatCurrency = (n: number) =>
    new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(n)

  const kindButton = (value: Kind, label: string) => (
    <button
      type="button"
      onClick={() => { setKind(value); setAmount(''); setError(null) }}
      className={`px-3 py-1 text-sm ${kind === value ? 'bg-gray-800 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
    >
      {label}
    </button>
  )

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-lg border p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">{kind === 'payment' ? 'Record Payment' : 'Record Draw'}</h3>
        <div className="flex border rounded overflow-hidden">
          {kindButton('payment', 'Payment')}
          {kindButton('draw', 'Draw')}
        </div>
      </div>
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <Tooltip text={kind === 'payment' ? 'Select the date the money was deposited to your account' : 'Select the date the money was given out'}>
            <label className="block text-xs text-gray-500 mb-1">Date</label>
          </Tooltip>
          <input
            type="date"
            className="border rounded px-2 py-1.5 text-sm"
            value={date}
            min={loan.start_date}
            onChange={e => setDate(e.target.value)}
            required
          />
        </div>
        <div>
          <Tooltip text={kind === 'payment'
            ? `Regular payment: ${formatCurrency(loan.regular_payment)}. Leave blank to use this amount.`
            : `Planned draw: ${formatCurrency(loan.planned_draw_amount)}. Leave blank to use this amount.`}>
            <label className="block text-xs text-gray-500 mb-1">Amount ($)</label>
          </Tooltip>
          <input
            type="number"
            step="0.01"
            min="0"
            className="border rounded px-2 py-1.5 text-sm w-32"
            placeholder={defaultAmount > 0 ? defaultAmount.toFixed(2) : '0.00'}
            value={amount}
            onChange={e => setAmount(e.target.value)}
          />
          <p className="text-xs text-gray-400 mt-0.5">
            {defaultAmount > 0 ? `Blank = ${formatCurrency(defaultAmount)}` : 'Required'}
          </p>
        </div>
        <div className="flex-1 min-w-[150px]">
          <label className="block text-xs text-gray-500 mb-1">Description (optional)</label>
          <input
            type="text"
            className="w-full border rounded px-2 py-1.5 text-sm"
            placeholder={kind === 'payment' ? 'Biweekly payment' : 'Tuition, rent, ...'}
            value={description}
            onChange={e => setDescription(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className={`px-4 py-1.5 text-white rounded text-sm disabled:opacity-50 ${
            kind === 'payment' ? 'bg-green-600 hover:bg-green-700' : 'bg-teal-600 hover:bg-teal-700'
          }`}
        >
          {submitting ? 'Saving...' : kind === 'payment' ? 'Record Payment' : 'Record Draw'}
        </button>
      </div>
    </form>
  )
}
