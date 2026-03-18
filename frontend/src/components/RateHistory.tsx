import { useState, useEffect } from 'react'
import { format, parseISO } from 'date-fns'
import type { Rate } from '../types'
import { getRates, createRate, deleteRate } from '../api/client'

export default function RateHistory() {
  const [rates, setRates] = useState<Rate[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [newDate, setNewDate] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })
  const [newRate, setNewRate] = useState('')

  const load = async () => {
    setRates(await getRates())
  }

  useEffect(() => { load() }, [])

  const handleAdd = async () => {
    const rate = parseFloat(newRate)
    if (!rate || !newDate) return
    await createRate({ effective_date: newDate, prime_rate: rate, source: 'manual' })
    setShowAdd(false)
    setNewRate('')
    load()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this rate entry? Balances will be recalculated.')) return
    await deleteRate(id)
    load()
  }

  return (
    <div className="bg-white rounded-lg border p-4 mb-6">
      <div className="flex justify-between items-center mb-3">
        <h3 className="font-semibold">Prime Rate History</h3>
        <button
          className="text-sm text-blue-600 hover:text-blue-800"
          onClick={() => setShowAdd(!showAdd)}
        >
          {showAdd ? 'Cancel' : '+ Manual Override'}
        </button>
      </div>

      {showAdd && (
        <div className="flex gap-3 items-end mb-3 p-3 bg-gray-50 rounded">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Effective Date</label>
            <input type="date" className="border rounded px-2 py-1.5 text-sm" value={newDate} onChange={e => setNewDate(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Prime Rate (%)</label>
            <input type="number" step="0.05" className="border rounded px-2 py-1.5 text-sm w-24" placeholder="4.45" value={newRate} onChange={e => setNewRate(e.target.value)} />
          </div>
          <button className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700" onClick={handleAdd}>Save</button>
        </div>
      )}

      {rates.length === 0 ? (
        <p className="text-gray-400 text-sm">No rate history yet. Rates are fetched automatically from the Bank of Canada.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-gray-50">
              <th className="px-3 py-2 text-left">Effective Date</th>
              <th className="px-3 py-2 text-right">Prime Rate</th>
              <th className="px-3 py-2 text-left">Source</th>
              <th className="px-3 py-2 w-10"></th>
            </tr>
          </thead>
          <tbody>
            {rates.map(r => (
              <tr key={r.id} className="border-b last:border-0 hover:bg-gray-50">
                <td className="px-3 py-2">{format(parseISO(r.effective_date), 'MMM d, yyyy')}</td>
                <td className="px-3 py-2 text-right font-mono">{r.prime_rate.toFixed(2)}%</td>
                <td className="px-3 py-2 text-gray-500 text-xs">
                  {r.source === 'bank_of_canada_api' ? 'Bank of Canada' : 'Manual'}
                </td>
                <td className="px-3 py-2">
                  <button className="text-gray-300 hover:text-red-500 text-xs" onClick={() => handleDelete(r.id)}>&times;</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
