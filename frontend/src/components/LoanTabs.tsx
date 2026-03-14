import { useState } from 'react'
import type { Loan, LoanCreate } from '../types'
import { createLoan, deleteLoan, updateLoan } from '../api/client'

interface Props {
  loans: Loan[]
  activeLoanId: number | null
  onSelect: (id: number) => void
  onRefresh: () => void
}

export default function LoanTabs({ loans, activeLoanId, onSelect, onRefresh }: Props) {
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [form, setForm] = useState<LoanCreate>({
    name: '',
    start_date: '',
    initial_amount: 0,
    regular_payment: 0,
    payment_frequency: 'biweekly',
    spread: 0.9,
    term_months: null,
  })

  const handleCreate = async () => {
    if (!form.name || !form.start_date || form.initial_amount <= 0) return
    await createLoan(form)
    setShowCreate(false)
    setForm({ name: '', start_date: '', initial_amount: 0, regular_payment: 0, payment_frequency: 'biweekly', spread: 0.9, term_months: null })
    onRefresh()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this loan and all its data?')) return
    await deleteLoan(id)
    onRefresh()
  }

  const handleRename = async (id: number) => {
    if (!editName.trim()) return
    await updateLoan(id, { name: editName })
    setEditingId(null)
    onRefresh()
  }

  return (
    <div className="mb-6">
      <div className="flex items-center gap-1 border-b border-gray-200">
        {loans.map(loan => (
          <div
            key={loan.id}
            className={`group flex items-center gap-1 px-4 py-2 cursor-pointer border-b-2 transition-colors ${
              loan.id === activeLoanId
                ? 'border-blue-600 text-blue-600 bg-blue-50'
                : 'border-transparent hover:bg-gray-100 text-gray-600'
            }`}
          >
            {editingId === loan.id ? (
              <input
                className="text-sm border rounded px-1 w-28"
                value={editName}
                onChange={e => setEditName(e.target.value)}
                onBlur={() => handleRename(loan.id)}
                onKeyDown={e => e.key === 'Enter' && handleRename(loan.id)}
                autoFocus
              />
            ) : (
              <span
                className="text-sm font-medium"
                onClick={() => onSelect(loan.id)}
                onDoubleClick={() => { setEditingId(loan.id); setEditName(loan.name) }}
              >
                {loan.name}
              </span>
            )}
            <button
              className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 ml-1 text-xs"
              onClick={(e) => { e.stopPropagation(); handleDelete(loan.id) }}
              title="Delete loan"
            >
              &times;
            </button>
          </div>
        ))}
        <button
          className="px-3 py-2 text-sm text-gray-500 hover:text-blue-600 hover:bg-gray-100 rounded-t"
          onClick={() => setShowCreate(true)}
        >
          + New Loan
        </button>
      </div>

      {showCreate && (
        <div className="mt-4 p-4 bg-white rounded-lg shadow border max-w-lg">
          <h3 className="font-semibold mb-3">Create New Loan</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Name</label>
              <input className="w-full border rounded px-2 py-1.5 text-sm" placeholder="e.g., Car Loan" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Start Date</label>
              <input className="w-full border rounded px-2 py-1.5 text-sm" type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Initial Amount ($)</label>
              <input className="w-full border rounded px-2 py-1.5 text-sm" type="number" step="0.01" placeholder="e.g., 25000.00" value={form.initial_amount || ''} onChange={e => setForm({ ...form, initial_amount: parseFloat(e.target.value) || 0 })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Regular Payment ($)</label>
              <input className="w-full border rounded px-2 py-1.5 text-sm" type="number" step="0.01" placeholder="e.g., 500.00" value={form.regular_payment || ''} onChange={e => setForm({ ...form, regular_payment: parseFloat(e.target.value) || 0 })} />
              <p className="text-xs text-gray-400 mt-0.5">Leave blank to calculate from term</p>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Term (months)</label>
              <input className="w-full border rounded px-2 py-1.5 text-sm" type="number" min="1" placeholder="e.g., 60" value={form.term_months ?? ''} onChange={e => setForm({ ...form, term_months: e.target.value ? parseInt(e.target.value) : null })} />
              <p className="text-xs text-gray-400 mt-0.5">Leave blank to calculate from payment</p>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Payment Frequency</label>
              <select className="w-full border rounded px-2 py-1.5 text-sm" value={form.payment_frequency} onChange={e => setForm({ ...form, payment_frequency: e.target.value })}>
                <option value="biweekly">Biweekly</option>
                <option value="monthly">Monthly</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Spread above Prime (%)</label>
              <input className="w-full border rounded px-2 py-1.5 text-sm" type="number" step="0.1" value={form.spread} onChange={e => setForm({ ...form, spread: parseFloat(e.target.value) || 0 })} />
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button className="px-4 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700" onClick={handleCreate}>Create</button>
            <button className="px-4 py-1.5 border rounded text-sm hover:bg-gray-50" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}

      {loans.length === 0 && !showCreate && (
        <div className="mt-12 text-center text-gray-400">
          <p className="text-lg mb-2">No loans yet</p>
          <p className="text-sm">Click "+ New Loan" to get started tracking your first loan.</p>
        </div>
      )}
    </div>
  )
}
