import { useState } from 'react'
import { format, parseISO } from 'date-fns'
import type { Transaction } from '../types'
import { deleteTransaction, errorMessage } from '../api/client'

interface Props {
  transactions: Transaction[]
  onRefresh: () => void
}

type SortKey = 'date' | 'amount'

export default function PaymentHistory({ transactions, onRefresh }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [error, setError] = useState<string | null>(null)

  const sorted = [...transactions].sort((a, b) => {
    const mul = sortDir === 'asc' ? 1 : -1
    if (sortKey === 'date') return mul * a.date.localeCompare(b.date)
    return mul * (a.amount - b.amount)
  })

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this transaction? Balance will be recalculated.')) return
    setError(null)
    try {
      await deleteTransaction(id)
      onRefresh()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const formatCurrency = (n: number) =>
    new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(n)

  if (transactions.length === 0) {
    return (
      <div className="bg-white rounded-lg border p-6 mb-6 text-center text-gray-400">
        <p>No transactions yet. Record your first payment or draw above.</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg border mb-6 overflow-hidden">
      {error && <p className="text-sm text-red-600 px-4 pt-3">{error}</p>}
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b">
            <th className="px-4 py-2 text-left cursor-pointer hover:text-blue-600" onClick={() => toggleSort('date')}>
              Date {sortKey === 'date' && (sortDir === 'asc' ? '↑' : '↓')}
            </th>
            <th className="px-4 py-2 text-left">Type</th>
            <th className="px-4 py-2 text-right cursor-pointer hover:text-blue-600" onClick={() => toggleSort('amount')}>
              Amount {sortKey === 'amount' && (sortDir === 'asc' ? '↑' : '↓')}
            </th>
            <th className="px-4 py-2 text-left">Description</th>
            <th className="px-4 py-2 w-10"></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(txn => (
            <tr key={txn.id} className="border-b last:border-0 hover:bg-gray-50">
              <td className="px-4 py-2">{format(parseISO(txn.date), 'MMM d, yyyy')}</td>
              <td className="px-4 py-2 text-gray-500">{txn.amount < 0 ? 'Payment' : 'Draw'}</td>
              <td className={`px-4 py-2 text-right font-mono ${txn.amount < 0 ? 'text-green-600' : 'text-red-600'}`}>
                {txn.amount < 0 ? '-' : '+'}{formatCurrency(Math.abs(txn.amount))}
              </td>
              <td className="px-4 py-2 text-gray-500">{txn.description || '—'}</td>
              <td className="px-4 py-2">
                <button
                  className="text-gray-300 hover:text-red-500 text-xs"
                  onClick={() => handleDelete(txn.id)}
                  title="Delete"
                >
                  &times;
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
