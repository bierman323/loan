import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, Legend } from 'recharts'
import { format, parseISO } from 'date-fns'
import { getProjection } from '../api/client'
import type { ProjectionResult } from '../types'
import Tooltip from './Tooltip'

interface Props {
  loanId: number
}

export default function ScenarioCalc({ loanId }: Props) {
  const [extraPayment, setExtraPayment] = useState('')
  const [extraRecurring, setExtraRecurring] = useState('')
  const [result, setResult] = useState<ProjectionResult | null>(null)
  const [loading, setLoading] = useState(false)

  const calculate = async () => {
    setLoading(true)
    try {
      const data = await getProjection({
        loan_id: loanId,
        extra_payment: parseFloat(extraPayment) || 0,
        extra_recurring: parseFloat(extraRecurring) || 0,
      })
      setResult(data)
    } finally {
      setLoading(false)
    }
  }

  const formatCurrency = (n: number) =>
    new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(n)

  // Merge trajectories for chart
  const chartData = result ? mergeTrajectories(result) : []

  return (
    <div className="bg-white rounded-lg border p-4 mb-6">
      <h3 className="font-semibold mb-3">What-If Scenario Calculator</h3>
      <div className="flex flex-wrap gap-3 items-end mb-4">
        <div>
          <Tooltip text="e.g., Enter 1000 to see how a $1,000 extra payment affects your loan">
            <label className="block text-xs text-gray-500 mb-1">One-Time Extra Payment ($)</label>
          </Tooltip>
          <input
            type="number"
            step="100"
            min="0"
            className="border rounded px-2 py-1.5 text-sm w-40"
            placeholder="1000"
            value={extraPayment}
            onChange={e => setExtraPayment(e.target.value)}
          />
        </div>
        <div>
          <Tooltip text="Extra amount added to each regular payment">
            <label className="block text-xs text-gray-500 mb-1">Extra Per Payment ($)</label>
          </Tooltip>
          <input
            type="number"
            step="50"
            min="0"
            className="border rounded px-2 py-1.5 text-sm w-40"
            placeholder="100"
            value={extraRecurring}
            onChange={e => setExtraRecurring(e.target.value)}
          />
        </div>
        <button
          onClick={calculate}
          disabled={loading}
          className="px-4 py-1.5 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 disabled:opacity-50"
        >
          {loading ? 'Calculating...' : 'Calculate'}
        </button>
      </div>

      {result && (
        <>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="bg-purple-50 rounded-lg p-3 border border-purple-100">
              <p className="text-xs text-gray-500">Interest Saved</p>
              <p className="text-xl font-bold text-purple-700">{formatCurrency(result.interest_saved)}</p>
            </div>
            <div className="bg-purple-50 rounded-lg p-3 border border-purple-100">
              <p className="text-xs text-gray-500">Months Saved</p>
              <p className="text-xl font-bold text-purple-700">{result.months_saved}</p>
            </div>
            <div className="bg-purple-50 rounded-lg p-3 border border-purple-100">
              <p className="text-xs text-gray-500">New Payoff Date</p>
              <p className="text-xl font-bold text-purple-700">
                {result.new_payoff_date ? format(parseISO(result.new_payoff_date), 'MMM yyyy') : 'N/A'}
              </p>
            </div>
          </div>

          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tickFormatter={d => format(parseISO(d), 'MMM yy')} fontSize={11} interval="preserveStartEnd" />
                <YAxis tickFormatter={n => `$${(n / 1000).toFixed(0)}k`} fontSize={11} />
                <RTooltip
                  labelFormatter={d => format(parseISO(d as string), 'MMM d, yyyy')}
                  formatter={(v: number) => formatCurrency(v)}
                />
                <Legend />
                <Line type="monotone" dataKey="current" stroke="#94a3b8" strokeWidth={2} dot={false} name="Current" />
                <Line type="monotone" dataKey="scenario" stroke="#7c3aed" strokeWidth={2} dot={false} name="With Extra" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </>
      )}
    </div>
  )
}

function mergeTrajectories(result: ProjectionResult) {
  const map = new Map<string, { date: string; current?: number; scenario?: number }>()
  for (const p of result.current_trajectory) {
    map.set(p.date, { date: p.date, current: p.balance })
  }
  for (const p of result.new_trajectory) {
    const existing = map.get(p.date)
    if (existing) existing.scenario = p.balance
    else map.set(p.date, { date: p.date, scenario: p.balance })
  }
  return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date))
}
