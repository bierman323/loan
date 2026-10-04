import { useState } from 'react'
import type { Loan } from '../types'
import { updateLoan, errorMessage } from '../api/client'

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

function formatDate(isoDate: string, withDay = true): string {
  return new Date(isoDate + 'T00:00:00').toLocaleDateString('en-CA', withDay
    ? { year: 'numeric', month: 'short', day: 'numeric' }
    : { year: 'numeric', month: 'short' })
}

type EditField = 'payment' | 'term' | 'frequency' | 'plan' | 'spread'

export default function Dashboard({ loan, onRefresh }: Props) {
  const [editing, setEditing] = useState<EditField | null>(null)
  const [editPayment, setEditPayment] = useState('')
  const [editTerm, setEditTerm] = useState('')
  const [editFrequency, setEditFrequency] = useState('')
  const [editDrawAmount, setEditDrawAmount] = useState('')
  const [editDrawEndDate, setEditDrawEndDate] = useState('')
  const [editRepaymentStart, setEditRepaymentStart] = useState('')
  const [editSpread, setEditSpread] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const balance = loan.current_balance ?? loan.initial_amount
  const dailyInterest = loan.daily_interest ?? 0
  const effectiveRate = loan.effective_rate ?? loan.spread
  const monthlyInterest = dailyInterest * 30.44
  const totalBorrowed = loan.total_borrowed ?? loan.initial_amount
  const totalRepaid = loan.total_repaid ?? 0
  const freqLabel = freqLabels[loan.payment_frequency] || loan.payment_frequency
  const hasBorrowingPlan = loan.planned_draw_amount > 0 || !!loan.repayment_start_date

  // Maturity date formatting
  let maturityLabel = 'N/A'
  let maturitySub = 'Projected payoff date'
  if (loan.pays_off === false) {
    maturityLabel = 'Never'
    maturitySub = 'Payment does not cover the interest'
  } else if (loan.maturity_date) {
    maturityLabel = formatDate(loan.maturity_date)
  }

  // Time saved vs the planned payoff date
  let timeSavedLabel = 'N/A'
  let timeSavedSub = ''
  if (loan.maturity_date && loan.planned_maturity_date) {
    const plannedEnd = new Date(loan.planned_maturity_date + 'T00:00:00')
    const projectedEnd = new Date(loan.maturity_date + 'T00:00:00')
    const diffDays = Math.round((plannedEnd.getTime() - projectedEnd.getTime()) / (1000 * 60 * 60 * 24))
    const diffMonths = Math.round(diffDays / 30.44)
    timeSavedSub = `Planned: ${formatDate(loan.planned_maturity_date, false)}`
    if (diffMonths > 0) {
      timeSavedLabel = `${diffMonths} mo earlier`
    } else if (diffMonths < 0) {
      timeSavedLabel = `${Math.abs(diffMonths)} mo later`
    } else {
      timeSavedLabel = 'On track'
    }
  }

  const startEdit = (field: EditField) => {
    setError(null)
    setEditing(field)
    if (field === 'payment') setEditPayment(loan.regular_payment.toString())
    if (field === 'term') setEditTerm(loan.term_months?.toString() || '')
    if (field === 'frequency') setEditFrequency(loan.payment_frequency)
    if (field === 'spread') setEditSpread(loan.spread.toString())
    if (field === 'plan') {
      setEditDrawAmount(loan.planned_draw_amount ? loan.planned_draw_amount.toString() : '')
      setEditDrawEndDate(loan.planned_draw_end_date ?? '')
      setEditRepaymentStart(loan.repayment_start_date ?? '')
    }
  }

  const cancelEdit = () => {
    setEditing(null)
    setError(null)
  }

  const saveEdit = async () => {
    setSaving(true)
    setError(null)
    try {
      if (editing === 'payment') {
        const val = parseFloat(editPayment)
        if (!(val > 0)) {
          setError('Enter a payment greater than 0.')
          return
        }
        await updateLoan(loan.id, { regular_payment: val })
      } else if (editing === 'term') {
        const val = parseInt(editTerm)
        if (!(val > 0)) {
          setError('Enter a term of at least 1 month.')
          return
        }
        await updateLoan(loan.id, { term_months: val })
      } else if (editing === 'frequency') {
        await updateLoan(loan.id, { payment_frequency: editFrequency })
      } else if (editing === 'spread') {
        const val = parseFloat(editSpread)
        if (!(val >= 0)) {
          setError('Enter a spread of 0 or more.')
          return
        }
        await updateLoan(loan.id, { spread: val })
      } else if (editing === 'plan') {
        await updateLoan(loan.id, {
          planned_draw_amount: parseFloat(editDrawAmount) || 0,
          // Empty date fields clear the value
          planned_draw_end_date: editDrawEndDate || null,
          repayment_start_date: editRepaymentStart || null,
        })
      }
      setEditing(null)
      onRefresh()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') saveEdit()
    if (e.key === 'Escape') cancelEdit()
  }

  const editButtons = (
    <div className="flex gap-1 mt-1">
      <button onClick={saveEdit} disabled={saving} className="text-xs px-2 py-0.5 bg-blue-600 text-white rounded hover:bg-blue-700">Save</button>
      <button onClick={cancelEdit} className="text-xs px-2 py-0.5 border rounded hover:bg-gray-50">Cancel</button>
    </div>
  )

  return (
    <>
      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

      {loan.in_borrowing_phase && (
        <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-2 mb-4 text-sm text-teal-800">
          Borrowing phase: no payments are due until repayment begins on {formatDate(loan.repayment_start_date!)}.
          Interest accrues and is added to the balance monthly.
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 mb-4">
        {/* Payment - editable */}
        <div className="rounded-lg border p-4 border-sky-200 bg-sky-50 group relative">
          <p className="text-xs text-gray-500 uppercase tracking-wide">{loan.in_borrowing_phase ? 'Est. Payment' : 'Payment'}</p>
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
              {editButtons}
              <p className="text-xs text-gray-400 mt-1">
                {loan.in_borrowing_phase
                  ? 'Term will recalculate based on the projected balance when repayment begins'
                  : 'Term will recalculate based on current balance'}
              </p>
            </div>
          ) : (
            <>
              <p className="text-2xl font-bold mt-1">{loan.regular_payment > 0 ? formatCurrency(loan.regular_payment) : 'Not set'}</p>
              <p className="text-xs text-gray-500 mt-1">
                {loan.in_borrowing_phase
                  ? (loan.term_months ? `${freqLabel}; updates as draws are recorded` : 'Set a term to estimate')
                  : freqLabel}
              </p>
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
              {editButtons}
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
              {editButtons}
              <p className="text-xs text-gray-400 mt-1">
                {loan.in_borrowing_phase
                  ? 'Counted from when repayment begins; payment will recalculate'
                  : 'Payment will recalculate based on current balance'}
              </p>
            </div>
          ) : (
            <>
              <p className="text-2xl font-bold mt-1">{loan.term_months ? formatTerm(loan.term_months) : 'Open'}</p>
              <p className="text-xs text-gray-500 mt-1">
                {loan.term_months
                  ? (loan.in_borrowing_phase ? `${loan.term_months} months from repayment start` : `${loan.term_months} months`)
                  : 'No fixed term'}
              </p>
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

      {/* Borrowing plan - editable as one form */}
      {editing === 'plan' ? (
        <div className="rounded-lg border p-4 border-teal-200 bg-teal-50 mb-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Borrowing Plan</p>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Planned monthly draw ($)</label>
              <input type="number" step="0.01" min="0" className="w-full border rounded px-2 py-1 text-sm" placeholder="0" value={editDrawAmount} onChange={e => setEditDrawAmount(e.target.value)} onKeyDown={handleKeyDown} autoFocus />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Last planned draw</label>
              <input type="date" className="w-full border rounded px-2 py-1 text-sm" value={editDrawEndDate} onChange={e => setEditDrawEndDate(e.target.value)} onKeyDown={handleKeyDown} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Repayment begins</label>
              <input type="date" className="w-full border rounded px-2 py-1 text-sm" value={editRepaymentStart} onChange={e => setEditRepaymentStart(e.target.value)} onKeyDown={handleKeyDown} />
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Planned draws are only used for projections. They repeat monthly on the loan's start day; record each actual draw below.
            The first payment is due one period after repayment begins.
          </p>
          {editButtons}
        </div>
      ) : hasBorrowingPlan ? (
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div className="rounded-lg border p-4 border-teal-200 bg-teal-50 group relative">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Planned Draws</p>
            <p className="text-2xl font-bold mt-1">{loan.planned_draw_amount > 0 ? `${formatCurrency(loan.planned_draw_amount)}/mo` : 'None'}</p>
            <p className="text-xs text-gray-500 mt-1">
              {loan.planned_draw_amount > 0 && loan.planned_draw_end_date ? `Until ${formatDate(loan.planned_draw_end_date)}` : 'No further draws planned'}
            </p>
            <button
              onClick={() => startEdit('plan')}
              className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-xs text-blue-600 hover:text-blue-800"
            >
              Adjust
            </button>
          </div>
          <div className="rounded-lg border p-4 border-teal-200 bg-teal-50">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Repayment Begins</p>
            <p className="text-2xl font-bold mt-1">{loan.repayment_start_date ? formatDate(loan.repayment_start_date) : 'Not set'}</p>
            <p className="text-xs text-gray-500 mt-1">{loan.in_borrowing_phase ? 'No payments until then' : 'Repayment underway'}</p>
          </div>
          <div className="rounded-lg border p-4 border-teal-200 bg-teal-50">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Balance at Repayment</p>
            <p className="text-2xl font-bold mt-1">
              {loan.balance_at_repayment_start != null ? formatCurrency(loan.balance_at_repayment_start) : 'N/A'}
            </p>
            <p className="text-xs text-gray-500 mt-1">Projected, incl. planned draws and interest</p>
          </div>
        </div>
      ) : (
        <div className="mb-4 -mt-2 text-right">
          <button onClick={() => startEdit('plan')} className="text-xs text-blue-600 hover:text-blue-800">
            + Add borrowing plan (draws over time)
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card label="Current Balance" value={formatCurrency(balance)} accent="blue" />
        <Card label="Interest Paid" value={formatCurrency(loan.interest_paid ?? 0)} sub="Total interest accrued to date" accent="amber" />
        <Card
          label="Interest Remaining"
          value={loan.interest_remaining != null ? formatCurrency(loan.interest_remaining) : 'N/A'}
          sub={loan.pays_off === false ? 'Loan never pays off at this payment' : 'Projected to payoff'}
          accent="rose"
        />
        {/* Effective Rate - spread above prime is editable */}
        <div className="rounded-lg border p-4 border-purple-200 bg-purple-50 group relative">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Effective Rate</p>
          {editing === 'spread' ? (
            <div className="mt-1">
              <div className="flex items-center gap-1">
                <span className="text-sm text-gray-500">Prime +</span>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  className="w-full border rounded px-2 py-1 text-lg font-bold"
                  value={editSpread}
                  onChange={e => setEditSpread(e.target.value)}
                  onKeyDown={handleKeyDown}
                  autoFocus
                />
                <span className="text-sm text-gray-500">%</span>
              </div>
              {editButtons}
              <p className="text-xs text-gray-400 mt-1">Recalculates all interest since the loan started</p>
            </div>
          ) : (
            <>
              <p className="text-2xl font-bold mt-1">{effectiveRate.toFixed(2)}%</p>
              <p className="text-xs text-gray-500 mt-1">Prime + {loan.spread}%</p>
              <button
                onClick={() => startEdit('spread')}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-xs text-blue-600 hover:text-blue-800"
              >
                Adjust
              </button>
            </>
          )}
        </div>
        <Card label="Daily Interest" value={formatCurrency(dailyInterest)} sub={`${formatCurrency(monthlyInterest)}/mo est.`} accent="amber" />
        <Card label="Total Repaid" value={formatCurrency(totalRepaid)} sub={`${formatCurrency(totalBorrowed)} borrowed to date`} accent="green" />
        <Card label="Maturity Date" value={maturityLabel} sub={maturitySub} accent={loan.pays_off === false ? 'rose' : 'indigo'} />
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
