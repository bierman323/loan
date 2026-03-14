import { useState, useEffect, useCallback } from 'react'
import type { Loan, Transaction, DailyBalance } from './types'
import { getLoans, getTransactions, getLoanBalances, getUserByToken, type User } from './api/client'
import UserSwitcher from './components/UserSwitcher'
import LoanTabs from './components/LoanTabs'
import Dashboard from './components/Dashboard'
import PaymentForm from './components/PaymentForm'
import PaymentHistory from './components/PaymentHistory'
import BalanceChart from './components/BalanceChart'
import ScenarioCalc from './components/ScenarioCalc'
import RateHistory from './components/RateHistory'

export default function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [userLoaded, setUserLoaded] = useState(false)
  const [loans, setLoans] = useState<Loan[]>([])
  const [activeLoanId, setActiveLoanId] = useState<number | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [balances, setBalances] = useState<DailyBalance[]>([])

  const activeLoan = loans.find(l => l.id === activeLoanId) ?? null

  // Restore user from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem('loan_tracker_token')
    if (token) {
      getUserByToken(token)
        .then(user => setCurrentUser(user))
        .catch(() => localStorage.removeItem('loan_tracker_token'))
        .finally(() => setUserLoaded(true))
    } else {
      setUserLoaded(true)
    }
  }, [])

  const loadLoans = useCallback(async () => {
    if (!currentUser) {
      setLoans([])
      setActiveLoanId(null)
      return
    }
    const data = await getLoans()
    setLoans(data)
    if (data.length > 0 && !data.find(l => l.id === activeLoanId)) {
      setActiveLoanId(data[0].id)
    } else if (data.length === 0) {
      setActiveLoanId(null)
    }
  }, [currentUser, activeLoanId])

  const loadLoanData = useCallback(async () => {
    if (!activeLoanId) {
      setTransactions([])
      setBalances([])
      return
    }
    const [txns, bals] = await Promise.all([
      getTransactions(activeLoanId),
      getLoanBalances(activeLoanId),
    ])
    setTransactions(txns)
    setBalances(bals)
  }, [activeLoanId])

  // Reload loans when user changes
  useEffect(() => {
    if (userLoaded) loadLoans()
  }, [currentUser, userLoaded])

  useEffect(() => {
    if (activeLoanId) loadLoanData()
  }, [activeLoanId])

  const handleRefresh = async () => {
    await loadLoans()
    if (activeLoanId) await loadLoanData()
  }

  const handleUserChange = (user: User | null) => {
    setCurrentUser(user)
    setLoans([])
    setActiveLoanId(null)
    setTransactions([])
    setBalances([])
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Loan Tracker</h1>
          <p className="text-sm text-gray-500">Track balances, payments, and interest on personal loans</p>
        </div>
        <UserSwitcher currentUser={currentUser} onUserChange={handleUserChange} />
      </div>

      {!currentUser ? (
        <div className="mt-20 text-center text-gray-400">
          <p className="text-lg mb-2">Welcome to Loan Tracker</p>
          <p className="text-sm">Select or create a user to get started.</p>
        </div>
      ) : (
        <>
          <LoanTabs
            loans={loans}
            activeLoanId={activeLoanId}
            onSelect={id => setActiveLoanId(id)}
            onRefresh={handleRefresh}
          />

          {activeLoan && (
            <>
              <Dashboard loan={activeLoan} onRefresh={handleRefresh} />
              <PaymentForm loan={activeLoan} onPaymentAdded={handleRefresh} />
              <PaymentHistory transactions={transactions} onRefresh={handleRefresh} />
              <BalanceChart balances={balances} />
              <ScenarioCalc loanId={activeLoan.id} />
              <RateHistory />
            </>
          )}
        </>
      )}
    </div>
  )
}
