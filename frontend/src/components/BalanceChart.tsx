import { useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip } from 'recharts'
import { format, parseISO } from 'date-fns'
import type { DailyBalance } from '../types'

interface Props {
  balances: DailyBalance[]
}

export default function BalanceChart({ balances }: Props) {
  // Sample to max ~200 points for chart performance
  const data = useMemo(() => {
    if (balances.length <= 200) return balances
    const step = Math.ceil(balances.length / 200)
    return balances.filter((_, i) => i % step === 0 || i === balances.length - 1)
  }, [balances])

  if (data.length === 0) {
    return (
      <div className="bg-white rounded-lg border p-6 mb-6 text-center text-gray-400">
        No balance history yet.
      </div>
    )
  }

  const formatCurrency = (n: number) => `$${(n / 1000).toFixed(1)}k`

  return (
    <div className="bg-white rounded-lg border p-4 mb-6">
      <h3 className="font-semibold mb-3">Balance Over Time</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="date"
            tickFormatter={d => format(parseISO(d), 'MMM yy')}
            fontSize={11}
            interval="preserveStartEnd"
          />
          <YAxis tickFormatter={formatCurrency} fontSize={11} />
          <RTooltip
            labelFormatter={d => format(parseISO(d as string), 'MMM d, yyyy')}
            formatter={(v: number) =>
              new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(v)
            }
          />
          <Line
            type="monotone"
            dataKey="closing_balance"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            name="Balance"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
