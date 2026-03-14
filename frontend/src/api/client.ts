import axios from 'axios'
import type { Loan, LoanCreate, Transaction, TransactionCreate, Rate, DailyBalance, ProjectionResult } from '../types'

const api = axios.create({ baseURL: '/api' })

// Attach user token to every request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('loan_tracker_token')
  if (token) {
    config.headers['X-User-Token'] = token
  }
  return config
})

// Users
export interface User {
  id: number
  name: string
  token: string
}

export const getUsers = () => api.get<User[]>('/users').then(r => r.data)
export const createUser = (name: string) => api.post<User>('/users', { name }).then(r => r.data)
export const getUserByToken = (token: string) => api.get<User>(`/users/by-token/${token}`).then(r => r.data)

// Loans
export const getLoans = () => api.get<Loan[]>('/loans').then(r => r.data)
export const getLoan = (id: number) => api.get<Loan>(`/loans/${id}`).then(r => r.data)
export const createLoan = (data: LoanCreate) => api.post<Loan>('/loans', data).then(r => r.data)
export const updateLoan = (id: number, data: Partial<Loan>) => api.patch<Loan>(`/loans/${id}`, data).then(r => r.data)
export const deleteLoan = (id: number) => api.delete(`/loans/${id}`)
export const getLoanBalances = (id: number) => api.get<DailyBalance[]>(`/loans/${id}/balances`).then(r => r.data)

// Transactions
export const getTransactions = (loanId?: number) =>
  api.get<Transaction[]>('/transactions', { params: loanId ? { loan_id: loanId } : {} }).then(r => r.data)
export const createTransaction = (data: TransactionCreate) => api.post<Transaction>('/transactions', data).then(r => r.data)
export const updateTransaction = (id: number, data: Partial<Transaction>) => api.patch<Transaction>(`/transactions/${id}`, data).then(r => r.data)
export const deleteTransaction = (id: number) => api.delete(`/transactions/${id}`)

// Rates
export const getRates = () => api.get<Rate[]>('/rates').then(r => r.data)
export const createRate = (data: { effective_date: string; prime_rate: number; source: string }) =>
  api.post<Rate>('/rates', data).then(r => r.data)
export const deleteRate = (id: number) => api.delete(`/rates/${id}`)

// Projections
export const getProjection = (data: { loan_id: number; extra_payment?: number; extra_payment_date?: string; extra_recurring?: number }) =>
  api.post<ProjectionResult>('/projections', data).then(r => r.data)
