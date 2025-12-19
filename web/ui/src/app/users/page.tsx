'use client';

import { useEffect, useState } from 'react';

interface User {
  id: number;
  username: string;
  role: string;
  active: boolean;
  sync_to_rtus: boolean;
  created_at: string;
  last_login: string | null;
}

interface Session {
  token: string;
  username: string;
  role: string;
  created_at: string;
  last_activity: string;
  ip_address: string;
}

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeTab, setActiveTab] = useState<'users' | 'sessions'>('users');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState<User | null>(null);
  const [showPasswordModal, setShowPasswordModal] = useState<User | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Form state for adding user
  const [newUser, setNewUser] = useState({
    username: '',
    password: '',
    confirmPassword: '',
    role: 'operator',
    sync_to_rtus: true,
  });

  // Form state for password change
  const [passwordForm, setPasswordForm] = useState({
    newPassword: '',
    confirmPassword: '',
  });

  useEffect(() => {
    fetchUsers();
    fetchSessions();
  }, []);

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const fetchUsers = async () => {
    try {
      const res = await fetch('/api/v1/users');
      if (res.ok) {
        setUsers(await res.json());
      }
    } catch (error) {
      console.error('Failed to fetch users:', error);
    }
  };

  const fetchSessions = async () => {
    try {
      const res = await fetch('/api/v1/auth/sessions');
      if (res.ok) {
        setSessions(await res.json());
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  };

  const addUser = async () => {
    if (!newUser.username || !newUser.password) {
      showMessage('error', 'Username and password are required');
      return;
    }

    if (newUser.password !== newUser.confirmPassword) {
      showMessage('error', 'Passwords do not match');
      return;
    }

    if (newUser.password.length < 6) {
      showMessage('error', 'Password must be at least 6 characters');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch('/api/v1/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: newUser.username,
          password: newUser.password,
          role: newUser.role,
          sync_to_rtus: newUser.sync_to_rtus,
        }),
      });

      if (res.ok) {
        showMessage('success', `User ${newUser.username} created successfully`);
        setShowAddModal(false);
        setNewUser({
          username: '',
          password: '',
          confirmPassword: '',
          role: 'operator',
          sync_to_rtus: true,
        });
        fetchUsers();
      } else {
        const error = await res.json();
        showMessage('error', error.detail || 'Failed to create user');
      }
    } catch (error) {
      showMessage('error', 'Error creating user');
    } finally {
      setLoading(false);
    }
  };

  const updateUser = async () => {
    if (!showEditModal) return;

    setLoading(true);
    try {
      const res = await fetch(`/api/v1/users/${showEditModal.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: showEditModal.role,
          active: showEditModal.active,
          sync_to_rtus: showEditModal.sync_to_rtus,
        }),
      });

      if (res.ok) {
        showMessage('success', `User ${showEditModal.username} updated`);
        setShowEditModal(null);
        fetchUsers();
      } else {
        const error = await res.json();
        showMessage('error', error.detail || 'Failed to update user');
      }
    } catch (error) {
      showMessage('error', 'Error updating user');
    } finally {
      setLoading(false);
    }
  };

  const changePassword = async () => {
    if (!showPasswordModal) return;

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      showMessage('error', 'Passwords do not match');
      return;
    }

    if (passwordForm.newPassword.length < 6) {
      showMessage('error', 'Password must be at least 6 characters');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`/api/v1/users/${showPasswordModal.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          password: passwordForm.newPassword,
        }),
      });

      if (res.ok) {
        showMessage('success', `Password changed for ${showPasswordModal.username}`);
        setShowPasswordModal(null);
        setPasswordForm({ newPassword: '', confirmPassword: '' });
      } else {
        const error = await res.json();
        showMessage('error', error.detail || 'Failed to change password');
      }
    } catch (error) {
      showMessage('error', 'Error changing password');
    } finally {
      setLoading(false);
    }
  };

  const deleteUser = async (user: User) => {
    if (user.username === 'admin') {
      showMessage('error', 'Cannot delete the admin user');
      return;
    }

    if (!confirm(`Are you sure you want to delete user "${user.username}"?`)) {
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`/api/v1/users/${user.id}`, {
        method: 'DELETE',
      });

      if (res.ok) {
        showMessage('success', `User ${user.username} deleted`);
        fetchUsers();
      } else {
        const error = await res.json();
        showMessage('error', error.detail || 'Failed to delete user');
      }
    } catch (error) {
      showMessage('error', 'Error deleting user');
    } finally {
      setLoading(false);
    }
  };

  const terminateSession = async (token: string) => {
    if (!confirm('Are you sure you want to terminate this session?')) {
      return;
    }

    try {
      const res = await fetch(`/api/v1/auth/sessions/${token}`, {
        method: 'DELETE',
      });

      if (res.ok) {
        showMessage('success', 'Session terminated');
        fetchSessions();
      } else {
        showMessage('error', 'Failed to terminate session');
      }
    } catch (error) {
      showMessage('error', 'Error terminating session');
    }
  };

  const getRoleBadge = (role: string) => {
    const colors: { [key: string]: string } = {
      admin: 'bg-red-900 text-red-300',
      engineer: 'bg-purple-900 text-purple-300',
      operator: 'bg-blue-900 text-blue-300',
      viewer: 'bg-gray-700 text-gray-300',
    };
    return colors[role] || 'bg-gray-700 text-gray-300';
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-white">User Management</h1>
        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white"
        >
          + Add User
        </button>
      </div>

      {/* Message Banner */}
      {message && (
        <div
          className={`p-4 rounded-lg ${
            message.type === 'success' ? 'bg-green-900 text-green-200' : 'bg-red-900 text-red-200'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Tabs */}
      <div className="flex space-x-4 border-b border-gray-700">
        {[
          { id: 'users', label: 'Users' },
          { id: 'sessions', label: 'Active Sessions' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as 'users' | 'sessions')}
            className={`px-4 py-2 -mb-px ${
              activeTab === tab.id
                ? 'border-b-2 border-blue-500 text-blue-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Users Tab */}
      {activeTab === 'users' && (
        <div className="scada-panel p-6">
          <table className="w-full">
            <thead>
              <tr className="text-left text-gray-400 text-sm border-b border-gray-700">
                <th className="pb-3">Username</th>
                <th className="pb-3">Role</th>
                <th className="pb-3">Status</th>
                <th className="pb-3">Sync to RTUs</th>
                <th className="pb-3">Last Login</th>
                <th className="pb-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-b border-gray-800">
                  <td className="py-4">
                    <span className="font-medium text-white">{user.username}</span>
                    {user.username === 'admin' && (
                      <span className="ml-2 text-xs text-yellow-400">(system)</span>
                    )}
                  </td>
                  <td className="py-4">
                    <span className={`px-2 py-1 rounded text-xs ${getRoleBadge(user.role)}`}>
                      {user.role}
                    </span>
                  </td>
                  <td className="py-4">
                    <span
                      className={`flex items-center gap-2 ${
                        user.active ? 'text-green-400' : 'text-gray-500'
                      }`}
                    >
                      <span
                        className={`w-2 h-2 rounded-full ${
                          user.active ? 'bg-green-400' : 'bg-gray-500'
                        }`}
                      />
                      {user.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="py-4">
                    <span className={user.sync_to_rtus ? 'text-blue-400' : 'text-gray-500'}>
                      {user.sync_to_rtus ? 'Yes' : 'No'}
                    </span>
                  </td>
                  <td className="py-4 text-gray-400 text-sm">{formatDate(user.last_login)}</td>
                  <td className="py-4 text-right">
                    <div className="flex justify-end space-x-2">
                      <button
                        onClick={() => setShowEditModal(user)}
                        className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => setShowPasswordModal(user)}
                        className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm text-white"
                      >
                        Password
                      </button>
                      {user.username !== 'admin' && (
                        <button
                          onClick={() => deleteUser(user)}
                          className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm text-white"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {users.length === 0 && (
            <p className="text-gray-400 text-center py-8">No users found</p>
          )}
        </div>
      )}

      {/* Sessions Tab */}
      {activeTab === 'sessions' && (
        <div className="scada-panel p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Active Sessions</h2>
            <button
              onClick={fetchSessions}
              className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white"
            >
              Refresh
            </button>
          </div>

          {sessions.length === 0 ? (
            <p className="text-gray-400">No active sessions</p>
          ) : (
            <div className="space-y-3">
              {sessions.map((session) => (
                <div
                  key={session.token}
                  className="flex items-center justify-between p-4 bg-gray-800 rounded"
                >
                  <div>
                    <div className="font-medium text-white">{session.username}</div>
                    <div className="text-sm text-gray-400">
                      <span className={`px-2 py-0.5 rounded text-xs ${getRoleBadge(session.role)}`}>
                        {session.role}
                      </span>
                      <span className="ml-3">IP: {session.ip_address || 'Unknown'}</span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Started: {formatDate(session.created_at)} | Last activity:{' '}
                      {formatDate(session.last_activity)}
                    </div>
                  </div>
                  <button
                    onClick={() => terminateSession(session.token)}
                    className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm text-white"
                  >
                    Terminate
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Add User Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-900 p-6 rounded-lg w-full max-w-md">
            <h2 className="text-xl font-semibold text-white mb-4">Add New User</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">Username</label>
                <input
                  type="text"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                  placeholder="Enter username"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Password</label>
                <input
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                  placeholder="Enter password"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Confirm Password</label>
                <input
                  type="password"
                  value={newUser.confirmPassword}
                  onChange={(e) => setNewUser({ ...newUser, confirmPassword: e.target.value })}
                  placeholder="Confirm password"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Role</label>
                <select
                  value={newUser.role}
                  onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                >
                  <option value="viewer">Viewer (read-only)</option>
                  <option value="operator">Operator (control access)</option>
                  <option value="engineer">Engineer (configuration)</option>
                  <option value="admin">Administrator (full access)</option>
                </select>
              </div>

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="syncToRtus"
                  checked={newUser.sync_to_rtus}
                  onChange={(e) => setNewUser({ ...newUser, sync_to_rtus: e.target.checked })}
                />
                <label htmlFor="syncToRtus" className="text-sm text-gray-300">
                  Sync credentials to RTUs
                </label>
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
              >
                Cancel
              </button>
              <button
                onClick={addUser}
                disabled={loading}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Creating...' : 'Create User'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {showEditModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-900 p-6 rounded-lg w-full max-w-md">
            <h2 className="text-xl font-semibold text-white mb-4">Edit User: {showEditModal.username}</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">Role</label>
                <select
                  value={showEditModal.role}
                  onChange={(e) => setShowEditModal({ ...showEditModal, role: e.target.value })}
                  disabled={showEditModal.username === 'admin'}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white disabled:opacity-50"
                >
                  <option value="viewer">Viewer (read-only)</option>
                  <option value="operator">Operator (control access)</option>
                  <option value="engineer">Engineer (configuration)</option>
                  <option value="admin">Administrator (full access)</option>
                </select>
              </div>

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="editActive"
                  checked={showEditModal.active}
                  onChange={(e) => setShowEditModal({ ...showEditModal, active: e.target.checked })}
                  disabled={showEditModal.username === 'admin'}
                />
                <label htmlFor="editActive" className="text-sm text-gray-300">
                  Account active
                </label>
              </div>

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="editSyncToRtus"
                  checked={showEditModal.sync_to_rtus}
                  onChange={(e) => setShowEditModal({ ...showEditModal, sync_to_rtus: e.target.checked })}
                />
                <label htmlFor="editSyncToRtus" className="text-sm text-gray-300">
                  Sync credentials to RTUs
                </label>
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowEditModal(null)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
              >
                Cancel
              </button>
              <button
                onClick={updateUser}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Change Password Modal */}
      {showPasswordModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-900 p-6 rounded-lg w-full max-w-md">
            <h2 className="text-xl font-semibold text-white mb-4">
              Change Password: {showPasswordModal.username}
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">New Password</label>
                <input
                  type="password"
                  value={passwordForm.newPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                  placeholder="Enter new password"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">Confirm Password</label>
                <input
                  type="password"
                  value={passwordForm.confirmPassword}
                  onChange={(e) =>
                    setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })
                  }
                  placeholder="Confirm new password"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => {
                  setShowPasswordModal(null);
                  setPasswordForm({ newPassword: '', confirmPassword: '' });
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white"
              >
                Cancel
              </button>
              <button
                onClick={changePassword}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white disabled:opacity-50"
              >
                {loading ? 'Changing...' : 'Change Password'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
