'use client';

import { useEffect, useState, useCallback } from 'react';
import { useCommandMode } from '@/contexts/CommandModeContext';
import CommandModeLogin from '@/components/CommandModeLogin';
import { extractArrayData, extractErrorMessage } from '@/lib/api';
import { useHMIToast } from '@/components/hmi';

interface User {
  id: number;
  username: string;
  role: string;
  active: boolean;
  sync_to_rtus: boolean;
  created_at: string | null;
  updated_at: string | null;
  last_login: string | null;
  password_changed_at: string | null;
  password_expires_at: string | null;
}

interface UserForm {
  username: string;
  password: string;
  role: string;
  active: boolean;
  sync_to_rtus: boolean;
}

const emptyForm: UserForm = {
  username: '',
  password: '',
  role: 'viewer',
  active: true,
  sync_to_rtus: true,
};

export default function UsersPage() {
  const { canCommand, mode } = useCommandMode();
  const { showMessage } = useHMIToast();

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form, setForm] = useState<UserForm>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  // Delete state
  const [deletingUser, setDeletingUser] = useState<User | null>(null);

  const fetchUsers = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/users?include_inactive=true');
      if (res.status === 401) {
        setError('auth');
        setLoading(false);
        return;
      }
      if (!res.ok) throw new Error('Failed to fetch users');
      const json = await res.json();
      setUsers(extractArrayData<User>(json));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const openCreateModal = () => {
    setEditingUser(null);
    setForm(emptyForm);
    setShowModal(true);
  };

  const openEditModal = (user: User) => {
    setEditingUser(user);
    setForm({
      username: user.username,
      password: '',
      role: user.role,
      active: user.active,
      sync_to_rtus: user.sync_to_rtus,
    });
    setShowModal(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      if (editingUser) {
        // Update
        const body: Record<string, unknown> = {};
        if (form.password) body.password = form.password;
        if (form.role !== editingUser.role) body.role = form.role;
        if (form.active !== editingUser.active) body.active = form.active;
        if (form.sync_to_rtus !== editingUser.sync_to_rtus) body.sync_to_rtus = form.sync_to_rtus;

        if (Object.keys(body).length === 0) {
          showMessage('info', 'No changes to save');
          setShowModal(false);
          setSubmitting(false);
          return;
        }

        const res = await fetch(`/api/v1/users/${editingUser.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(extractErrorMessage(data.detail, 'Failed to update user'));
        }
        showMessage('success', `User '${editingUser.username}' updated`);
      } else {
        // Create
        const res = await fetch('/api/v1/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(extractErrorMessage(data.detail, 'Failed to create user'));
        }
        showMessage('success', `User '${form.username}' created`);
      }
      setShowModal(false);
      fetchUsers();
    } catch (err) {
      showMessage('error', err instanceof Error ? err.message : 'Operation failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingUser) return;
    try {
      const res = await fetch(`/api/v1/users/${deletingUser.id}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(data.detail, 'Failed to delete user'));
      }
      showMessage('success', `User '${deletingUser.username}' deleted`);
      setDeletingUser(null);
      fetchUsers();
    } catch (err) {
      showMessage('error', err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleUnlock = async (user: User) => {
    try {
      const res = await fetch(`/api/v1/users/${user.id}/unlock`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to unlock user');
      showMessage('success', `User '${user.username}' unlocked`);
      fetchUsers();
    } catch (err) {
      showMessage('error', err instanceof Error ? err.message : 'Unlock failed');
    }
  };

  const roleBadge = (role: string) => {
    const colors: Record<string, string> = {
      admin: 'bg-purple-600/20 text-purple-400 border-purple-500/30',
      operator: 'bg-blue-600/20 text-blue-400 border-blue-500/30',
      viewer: 'bg-gray-600/20 text-gray-400 border-gray-500/30',
    };
    return colors[role] || colors.viewer;
  };

  // Auth required
  if (error === 'auth' || (!loading && !canCommand)) {
    return (
      <div className="p-6">
        <div className="max-w-2xl mx-auto">
          <h1 className="text-2xl font-bold text-hmi-text mb-6">User Management</h1>
          <div className="bg-hmi-panel border border-hmi-border rounded-lg p-6 text-center">
            <p className="text-hmi-muted mb-4">Admin authentication required to manage users.</p>
            <CommandModeLogin showButton={true} onClose={fetchUsers} />
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold text-hmi-text mb-6">User Management</h1>
        <div className="animate-pulse space-y-3">
          <div className="h-10 bg-hmi-panel rounded w-full"></div>
          <div className="h-10 bg-hmi-panel rounded w-full"></div>
          <div className="h-10 bg-hmi-panel rounded w-full"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-hmi-text">User Management</h1>
        <button
          onClick={openCreateModal}
          className="px-4 py-2 bg-status-info hover:bg-status-info/90 text-white rounded font-medium text-sm"
        >
          Add User
        </button>
      </div>

      {error && error !== 'auth' && (
        <div className="p-3 bg-red-900/20 border border-red-600/50 rounded text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Users Table */}
      <div className="bg-hmi-panel border border-hmi-border rounded-lg overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-hmi-border bg-hmi-bg/50">
              <th className="px-4 py-3 text-sm font-medium text-hmi-muted">Username</th>
              <th className="px-4 py-3 text-sm font-medium text-hmi-muted">Role</th>
              <th className="px-4 py-3 text-sm font-medium text-hmi-muted">Status</th>
              <th className="px-4 py-3 text-sm font-medium text-hmi-muted">Sync to RTUs</th>
              <th className="px-4 py-3 text-sm font-medium text-hmi-muted">Last Login</th>
              <th className="px-4 py-3 text-sm font-medium text-hmi-muted text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className="border-b border-hmi-border hover:bg-hmi-bg/30">
                <td className="px-4 py-3 text-hmi-text font-medium">{user.username}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs font-medium border ${roleBadge(user.role)}`}>
                    {user.role}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    user.active
                      ? 'bg-green-600/20 text-green-400'
                      : 'bg-red-600/20 text-red-400'
                  }`}>
                    {user.active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="px-4 py-3 text-hmi-muted text-sm">
                  {user.sync_to_rtus ? 'Yes' : 'No'}
                </td>
                <td className="px-4 py-3 text-hmi-muted text-sm">
                  {user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => openEditModal(user)}
                      className="px-3 py-1 text-xs bg-hmi-bg hover:bg-hmi-border rounded text-hmi-text"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleUnlock(user)}
                      className="px-3 py-1 text-xs bg-yellow-600/20 hover:bg-yellow-600/30 rounded text-yellow-400"
                      title="Unlock account"
                    >
                      Unlock
                    </button>
                    <button
                      onClick={() => setDeletingUser(user)}
                      className="px-3 py-1 text-xs bg-red-600/20 hover:bg-red-600/30 rounded text-red-400"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-hmi-muted">
                  No users found. Click &quot;Add User&quot; to create one.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-hmi-panel border border-hmi-border rounded-lg shadow-lg w-full max-w-md">
            <div className="flex items-center justify-between p-4 border-b border-hmi-border">
              <h2 className="text-lg font-semibold text-hmi-text">
                {editingUser ? `Edit User: ${editingUser.username}` : 'Create User'}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="text-hmi-muted hover:text-hmi-text text-xl font-bold leading-none"
              >
                X
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-4 space-y-4">
              {!editingUser && (
                <div>
                  <label className="block text-sm font-medium text-hmi-text mb-1">Username</label>
                  <input
                    type="text"
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    className="w-full px-3 py-2 bg-hmi-bg border border-hmi-border rounded text-hmi-text"
                    required
                    autoFocus
                  />
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-hmi-text mb-1">
                  Password{editingUser ? ' (leave empty to keep current)' : ''}
                </label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full px-3 py-2 bg-hmi-bg border border-hmi-border rounded text-hmi-text"
                  required={!editingUser}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-hmi-text mb-1">Role</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  className="w-full px-3 py-2 bg-hmi-bg border border-hmi-border rounded text-hmi-text"
                >
                  <option value="viewer">Viewer</option>
                  <option value="operator">Operator</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm text-hmi-text">
                  <input
                    type="checkbox"
                    checked={form.active}
                    onChange={(e) => setForm({ ...form, active: e.target.checked })}
                  />
                  Active
                </label>
                <label className="flex items-center gap-2 text-sm text-hmi-text">
                  <input
                    type="checkbox"
                    checked={form.sync_to_rtus}
                    onChange={(e) => setForm({ ...form, sync_to_rtus: e.target.checked })}
                  />
                  Sync to RTUs
                </label>
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="flex-1 px-4 py-2 bg-hmi-bg hover:bg-hmi-border border border-hmi-border rounded text-hmi-text"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 px-4 py-2 bg-status-info hover:bg-status-info/90 rounded text-white disabled:opacity-50"
                >
                  {submitting ? 'Saving...' : editingUser ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingUser && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-hmi-panel border border-hmi-border rounded-lg shadow-lg w-full max-w-sm p-6">
            <h2 className="text-lg font-semibold text-hmi-text mb-2">Delete User</h2>
            <p className="text-hmi-muted mb-4">
              Are you sure you want to delete user &quot;{deletingUser.username}&quot;? This action cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeletingUser(null)}
                className="flex-1 px-4 py-2 bg-hmi-bg hover:bg-hmi-border border border-hmi-border rounded text-hmi-text"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 rounded text-white"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
