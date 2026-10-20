import { useEffect, useState } from 'react'
import api from '../utils/api'

interface AdminUser {
  id: string
  email: string
  display_name?: string | null
  role: string
  created_at?: string | null
}

/**
 * Super Admin user management (fixed 3-slot role model).
 *
 * Only reachable by an authenticated 'admin'; the API enforces this too
 * (403 for anyone else). There is no self-registration anywhere in the app.
 * Roles are fixed, so the edit form changes only email / display name /
 * password — never a role.
 */
export default function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editing, setEditing] = useState<AdminUser | null>(null)
  const [form, setForm] = useState({ email: '', display_name: '', password: '' })

  const load = () => {
    api
      .get('/admin/users')
      .then((r) => setUsers(r.data.users))
      .catch((e) => setError(e.response?.data?.detail?.message || 'Failed to load users'))
  }

  useEffect(load, [])

  const startEdit = (u: AdminUser) => {
    setEditing(u)
    setNotice(null)
    setForm({ email: u.email, display_name: u.display_name || '', password: '' })
  }

  const save = async () => {
    if (!editing) return
    const body: Record<string, string> = {}
    if (form.email !== editing.email) body.email = form.email
    if (form.display_name !== (editing.display_name || '')) body.display_name = form.display_name
    if (form.password) body.password = form.password
    try {
      await api.put(`/admin/users/${editing.id}`, body)
      setEditing(null)
      setNotice('User updated')
      load()
    } catch (e: any) {
      setError(e.response?.data?.detail?.message || 'Update failed')
    }
  }

  const resetPassword = async (u: AdminUser) => {
    try {
      const r = await api.post(`/admin/users/reset-password/${u.id}`, {})
      if (r.data.generated_password) {
        setNotice(`New password for ${u.email}: ${r.data.generated_password} — copy it now, it is not shown again.`)
      } else {
        setNotice(`Password reset for ${u.email}`)
      }
    } catch (e: any) {
      setError(e.response?.data?.detail?.message || 'Reset failed')
    }
  }

  return (
    <div className="space-y-4 max-w-3xl">
      <div>
        <h1 className="text-3xl font-bold">Users</h1>
        <p className="text-sm text-text-secondary mt-1">
          One Super Admin and two standard users. Roles are fixed; you can change a standard user's
          email, display name and password.
        </p>
      </div>

      {error && <div className="panel p-3 text-sm text-risk-critical">{error}</div>}
      {notice && <div className="panel p-3 text-sm text-text-secondary">{notice}</div>}

      <div className="panel divide-y divide-border">
        {users.map((u) => (
          <div key={u.id} className="p-4 flex items-center justify-between gap-4">
            <div>
              <div className="font-medium">{u.display_name || u.email}</div>
              <div className="text-sm text-text-secondary mono-id">{u.email}</div>
              <div className="text-xs mt-1">
                <span className={u.role === 'admin' ? 'text-accent-400' : 'text-text-secondary'}>
                  {u.role === 'admin' ? 'Super Admin' : 'Standard user'}
                </span>
              </div>
            </div>
            {u.role === 'admin' ? (
              <span className="text-xs text-text-secondary">not editable here</span>
            ) : (
              <div className="flex gap-2">
                <button className="btn-secondary" onClick={() => startEdit(u)}>Edit</button>
                <button className="btn-secondary" onClick={() => resetPassword(u)}>Reset password</button>
              </div>
            )}
          </div>
        ))}
      </div>

      {editing && (
        <div className="panel p-5 space-y-3">
          <h2 className="text-lg font-semibold">Edit {editing.email}</h2>
          <div>
            <label className="micro-label block mb-1">Email</label>
            <input className="input w-full" value={form.email}
                   onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div>
            <label className="micro-label block mb-1">Display name</label>
            <input className="input w-full" value={form.display_name}
                   onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </div>
          <div>
            <label className="micro-label block mb-1">New password (leave blank to keep)</label>
            <input className="input w-full" type="password" value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          <div className="flex gap-2 pt-1">
            <button className="btn-primary" onClick={save}>Save</button>
            <button className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
