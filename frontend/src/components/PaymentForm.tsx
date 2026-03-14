import { useState } from 'react'
import type { Loan } from '../types'
import { createTransaction } from '../api/client'
import Tooltip from './Tooltip'

interface Props {
  loan: Loan
  onPaymentAdded: () => void
}

export default function PaymentForm({ loan, onPaymentAdded }: Props) {
  const [date, setDate] = useState(new Date().toISOString().split('T')[0])
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const effectiveAmount = amount !== '' ? parseFloat(amount) : loan.regular_payment

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!effectiveAmount || !date) return

    setSubmitting(true)
    try {
      await createTransaction({
        loan_id: loan.id,
        date,
        amount: -Math.abs(effectiveAmount),
        description: description || undefined,
      })
      setAmount('')
      setDescription('')
      onPaymentAdded()
    } finally {
      setSubmitting(false)
    }
  }

  const formatCurrency = (n: number) =>
    new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(n)

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-lg border p-4 mb-6">
      <h3 className="font-semibold mb-3">Record Payment</h3>
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <Tooltip text="Select the date the money was deposited to your account">
            <label className="block text-xs text-gray-500 mb-1">Date</label>
          </Tooltip>
          <input
            type="date"
            className="border rounded px-2 py-1.5 text-sm"
            value={date}
            onChange={e => setDate(e.target.value)}
            required
          />
        </div>
        <div>
          <Tooltip text={`Regular payment: ${formatCurrency(loan.regular_payment)}. Leave blank to use this amount.`}>
            <label className="block text-xs text-gray-500 mb-1">Amount ($)</label>
          </Tooltip>
          <input
            type="number"
            step="0.01"
            min="0"
            className="border rounded px-2 py-1.5 text-sm w-32"
            placeholder={loan.regular_payment.toFixed(2)}
            value={amount}
            onChange={e => setAmount(e.target.value)}
          />
          <p className="text-xs text-gray-400 mt-0.5">
            Blank = {formatCurrency(loan.regular_payment)}
          </p>
        </div>
        <div className="flex-1 min-w-[150px]">
          <label className="block text-xs text-gray-500 mb-1">Description (optional)</label>
          <input
            type="text"
            className="w-full border rounded px-2 py-1.5 text-sm"
            placeholder="Biweekly payment"
            value={description}
            onChange={e => setDescription(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-1.5 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
        >
          {submitting ? 'Saving...' : 'Record Payment'}
        </button>
      </div>
    </form>
  )
}
