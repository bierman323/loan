import { useState } from 'react'
import type { Loan } from '../types'
import { updateLoan } from '../api/client'

interface Props {
  loan: Loan
  onRefresh: () => void
}

const freqLabels: Record<string, string> = {
  weekly: 'Weekly',
  biweekly: 'Biweekly',
  monthly: 'Monthly',
}

function formatTerm(months: number): string {
  const years = Math.floor(months / 12)
  const rem = months % 12
  if (years === 0) return `${rem} mo`
  if (rem === 0) return `${years} yr`
  return `${years} yr ${rem} mo`
}

function formatCurrency(n: number): string {
  return new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(n)
}

export default function Dashboard({ loan, onRefresh }: Props) {
  const [editing, setEditing] = useState<'payment' | 'term' | 'frequency' | null>(null)
  const [editPayment, setEditPayment] = useState('')
  const [editTerm, setEditTerm] = useState('')
  const [editFrequency, setEditFrequency] = useState('')
  const [saving, setSaving] = useState(false)

  const balance = loan.current_balance ?? loan.initial_amount
  const dailyInterest = loan.daily_interest ?? 0
  const effectiveRate = loan.effective_rate ?? loan.spread
  const monthlyInterest = dailyInterest * 30.44
  const principalPaid = loan.initial_amount - balance
  const freqLabel = freqLabels[loan.payment_frequency] || loan.payment_frequency

  // Maturity date formatting
  const maturityLabel = loan.maturity_date
    ? new Date(loan.maturity_date + 'T00:00:00').toLocaleDateString('en-CA', { year: 'numeric', month: 'short', day: 'numeric' })
    : 'N/A'

  // Time saved vs original term
  let timeSavedLabel = 'N/A'
  let timeSavedSub = ''
  if (loan.maturity_date && loan.term_months && loan.start_date) {
    const start = new Date(loan.start_date + 'T00:00:00')
    const originalEnd = new Date(start)
    originalEnd.setMonth(originalEnd.getMonth() + loan.term_months)
    const projectedEnd = new Date(loan.maturity_date + 'T00:00:00')
    const diffDays = Math.round((originalEnd.getTime() - projectedEnd.getTime()) / (1000 * 60 * 60 * 24))
    const diffMonths = Math.round(diffDays / 30.44)
    if (diffMonths > 0) {
      timeSavedLabel = `${diffMonths} mo earlier`
      timeSavedSub = `Original: ${originalEnd.toLocaleDateString('en-CA', { year: 'numeric', month: 'short' })}`
    } else if (diffMonths < 0) {
      timeSavedLabel = `${Math.abs(diffMonths)} mo later`
      timeSavedSub = `Original: ${originalEnd.toLocaleDateString('en-CA', { year: 'numeric', month: 'short' })}`
    } else {
      timeSavedLabel = 'On track'
      timeSavedSub = `Original: ${originalEnd.toLocaleDateString('en-CA', { year: 'numeric', month: 'short' })}`
    }
  }

  const startEdit = (field: 'payment' | 'term' | 'frequency') => {
    setEditing(field)
    if (field === 'payment') setEditPayment(loan.regular_payment.toString())
    if (field === 'term') setEditTerm(loan.term_months?.toString() || '')
    if (field === 'frequency') setEditFrequency(loan.payment_frequency)
  }

  const cancelEdit = () => setEditing(null)

  const saveEdit = async () => {
    setSaving(true)
    try {
      if (editing === 'payment') {
        const val = parseFloat(editPayment)
        if (val > 0) await updateLoan(loan.id, { regular_payment: val })
      } else if (editing === 'term') {
        const val = parseInt(editTerm)
        if (val > 0) await updateLoan(loan.id, { term_months: val })
      } else if (editing === 'frequency') {
        await updateLoan(loan.id, { payment_frequency: editFrequency })
      }
      setEditing(null)
      onRefresh()
    } finally {
      setSaving(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') saveEdit()
    if (e.key === 'Escape') cancelEdit()
  }

  return (
    <>
      <div className="grid grid-cols-3 gap-4 mb-4">
        {/* Payment - editable */}
        <div className="rounded-lg border p-4 border-sky-200 bg-sky-50 group relative">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Payment</p>
          {editing === 'payment' ? (
            <div className="mt-1">
              <input
                type="number"
                step="0.01"
                min="0"
                className="w-full border rounded px-2 py-1 text-lg font-bold"
                value={editPayment}
                onChange={e => setEditPayment(e.target.value)}
                onKeyDown={handleKeyDown}
                autoFocus
              />
              <div className="flex gap-1 mt-1">
                <button onClick={saveEdit} disabled={saving} className="text-xs px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700">Save</button>
                <button onClick={cancelEdit} className="text-xs px-2 py-0.5 border rounded hover:bg-gray-50">Cancel</button>
              </div>
              <p className="text-xs text-gray-400 mt-1">Term will recalculate based on current balance</p>
            </div>
          ) : (
            <>
              <p className="text-2xl font-bold mt-1">{formatCurrency(loan.regular_payment)}</p>
              <p className="text-xs text-gray-500 mt-1">{freqLabel}</p>
              <button
                onClick={() => startEdit('payment')}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-xs text-blue-600 hover:text-blue-800"
              >
                Adjust
              </button>
            </>
          )}
        </div>

        {/* Frequency - editable */}
        <div className="rounded-lg border p-4 border-sky-200 bg-sky-50 group relative">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Frequency</p>
          {editing === 'frequency' ? (
            <div className="mt-1">
              <select
                className="w-full border rounded px-2 py-1 text-lg font-bold"
                value={editFrequency}
                onChange={e => setEditFrequency(e.target.value)}
                onKeyDown={handleKeyDown}
                autoFocus
              >
                <option value="weekly">Weekly</option>
                <option value="biweekly">Biweekly</option>
                <option value="monthly">Monthly</option>
              </select>
              <div className="flex gap-1 mt-1">
                <button onClick={saveEdit} disabled={saving} className="text-xs px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700">Save</button>
                <button onClick={cancelEdit} className="text-xs px-2 py-0.5 border rounded hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          ) : (
            <>
              <p className="text-2xl font-bold mt-1">{freqLabel}</p>
              <p className="text-xs text-gray-500 mt-1">{formatCurrency(loan.regular_payment)} per period</p>
              <button
                onClick={() => startEdit('frequency')}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-xs text-blue-600 hover:text-blue-800"
              >
                Adjust
              </button>
            </>
          )}
        </div>

        {/* Term - editable */}
        <div className="rounded-lg border p-4 border-sky-200 bg-sky-50 group relative">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Term</p>
          {editing === 'term' ? (
            <div className="mt-1">
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  min="1"
                  className="w-full border rounded px-2 py-1 text-lg font-bold"
                  value={editTerm}
                  onChange={e => setEditTerm(e.target.value)}
                  onKeyDown={handleKeyDown}
                  autoFocus
                />
                <span className="text-sm text-gray-500">mo</span>
              </div>
              <div className="flex gap-1 mt-1">
                <button onClick={saveEdit} disabled={saving} className="text-xs px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700">Save</button>
                <button onClick={cancelEdit} className="text-xs px-2 py-0.5 border rounded hover:bg-gray-50">Cancel</button>
              </div>
              <p className="text-xs text-gray-400 mt-1">Payment will recalculate based on current balance</p>
            </div>
          ) : (
            <>
              <p className="text-2xl font-bold mt-1">{loan.term_months ? formatTerm(loan.term_months) : 'Open'}</p>
              <p className="text-xs text-gray-500 mt-1">{loan.term_months ? `${loan.term_months} months` : 'No fixed term'}</p>
              <button
                onClick={() => startEdit('term')}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-xs text-blue-600 hover:text-blue-800"
              >
                Adjust
              </button>
            </>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card label="Current Balance" value={formatCurrency(balance)} accent="blue" />
        <Card label="Interest Paid" value={formatCurrency(loan.interest_paid ?? 0)} sub="Total interest accrued to date" accent="amber" />
        <Card label="Interest Remaining" value={loan.interest_remaining != null ? formatCurrency(loan.interest_remaining) : 'N/A'} sub="Projected to payoff" accent="rose" />
        <Card label="Effective Rate" value={`${effectiveRate.toFixed(2)}%`} sub={`Prime + ${loan.spread}%`} accent="purple" />
        <Card label="Daily Interest" value={formatCurrency(dailyInterest)} sub={`${formatCurrency(monthlyInterest)}/mo est.`} accent="amber" />
        <Card label="Principal Paid" value={formatCurrency(principalPaid)} sub={`${((principalPaid / loan.initial_amount) * 100).toFixed(1)}% of original`} accent="green" />
        <Card label="Maturity Date" value={maturityLabel} sub="Projected payoff date" accent="indigo" />
        <Card label="Term Shift" value={timeSavedLabel} sub={timeSavedSub} accent={timeSavedLabel.includes('earlier') ? 'green' : timeSavedLabel.includes('later') ? 'rose' : 'sky'} />
      </div>
    </>
  )
}

function Card({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent: string }) {
  const colors: Record<string, string> = {
    sky: 'border-sky-200 bg-sky-50',
    blue: 'border-blue-200 bg-blue-50',
    amber: 'border-amber-200 bg-amber-50',
    purple: 'border-purple-200 bg-purple-50',
    green: 'border-green-200 bg-green-50',
    rose: 'border-rose-200 bg-rose-50',
    indigo: 'border-indigo-200 bg-indigo-50',
  }
  return (
    <div className={`rounded-lg border p-4 ${colors[accent] || ''}`}>
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  )
}
