import { useState, useEffect, useRef } from 'react'
import { getUsers, createUser, getUserByToken, type User } from '../api/client'

interface Props {
  currentUser: User | null
  onUserChange: (user: User | null) => void
}

export default function UserSwitcher({ currentUser, onUserChange }: Props) {
  const [users, setUsers] = useState<User[]>([])
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) {
      getUsers().then(setUsers)
    }
  }, [open])

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setCreating(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const selectUser = (user: User) => {
    localStorage.setItem('loan_tracker_token', user.token)
    onUserChange(user)
    setOpen(false)
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    const user = await createUser(newName.trim())
    setNewName('')
    setCreating(false)
    selectUser(user)
  }

  const handleSignOut = () => {
    localStorage.removeItem('loan_tracker_token')
    onUserChange(null)
    setOpen(false)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg border hover:bg-gray-100 text-sm"
      >
        <span className="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-xs font-bold">
          {currentUser ? currentUser.name[0].toUpperCase() : '?'}
        </span>
        <span>{currentUser ? currentUser.name : 'Select User'}</span>
        <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-64 bg-white rounded-lg shadow-lg border z-50">
          {currentUser && (
            <div className="px-4 py-2 border-b bg-gray-50 rounded-t-lg">
              <p className="text-xs text-gray-500">Signed in as</p>
              <p className="font-medium text-sm">{currentUser.name}</p>
            </div>
          )}

          <div className="max-h-48 overflow-y-auto">
            {users.filter(u => u.id !== currentUser?.id).map(user => (
              <button
                key={user.id}
                onClick={() => selectUser(user)}
                className="w-full text-left px-4 py-2 hover:bg-gray-50 text-sm flex items-center gap-2"
              >
                <span className="w-6 h-6 rounded-full bg-gray-300 text-white flex items-center justify-center text-xs font-bold">
                  {user.name[0].toUpperCase()}
                </span>
                {user.name}
              </button>
            ))}
          </div>

          <div className="border-t">
            {creating ? (
              <div className="p-3">
                <input
                  className="w-full border rounded px-2 py-1.5 text-sm mb-2"
                  placeholder="Enter name"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleCreate()}
                  autoFocus
                />
                <div className="flex gap-2">
                  <button
                    className="flex-1 px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
                    onClick={handleCreate}
                  >
                    Create
                  </button>
                  <button
                    className="px-3 py-1 border rounded text-sm hover:bg-gray-50"
                    onClick={() => { setCreating(false); setNewName('') }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setCreating(true)}
                className="w-full text-left px-4 py-2 hover:bg-gray-50 text-sm text-blue-600"
              >
                + New User
              </button>
            )}
          </div>

          {currentUser && (
            <div className="border-t">
              <button
                onClick={handleSignOut}
                className="w-full text-left px-4 py-2 hover:bg-gray-50 text-sm text-gray-500"
              >
                Sign Out
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
