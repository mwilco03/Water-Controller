'use client';

import './globals.css';
import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [showConfigMenu, setShowConfigMenu] = useState(false);
  const [user, setUser] = useState<{ username: string; role: string } | null>(null);

  useEffect(() => {
    // Check for stored user session
    const storedUser = localStorage.getItem('user');
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        // Invalid stored data
      }
    }
  }, []);

  const handleLogout = async () => {
    try {
      await fetch('/api/v1/auth/logout', { method: 'POST' });
    } catch {
      // Ignore errors
    }
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    setUser(null);
    window.location.href = '/login';
  };

  const isActive = (path: string) => pathname === path;
  const isConfigActive = ['/settings', '/io-tags', '/network', '/users'].some(p => pathname.startsWith(p));

  return (
    <html lang="en">
      <head>
        <title>Water Treatment Controller - HMI</title>
        <meta name="description" content="SCADA HMI for Water Treatment RTU Network" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="min-h-screen flex flex-col">
          <header className="sticky top-0 z-50 bg-slate-900/95 backdrop-blur-lg border-b border-sky-500/20 px-6 py-3">
            <div className="flex items-center justify-between max-w-[1800px] mx-auto">
              <div className="flex items-center gap-4">
                {/* Logo */}
                <a href="/" className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-sky-400 to-blue-600 flex items-center justify-center shadow-lg shadow-sky-500/25">
                    <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                    </svg>
                  </div>
                  <div>
                    <h1 className="text-lg font-bold text-white leading-tight">
                      Water Treatment Controller
                    </h1>
                    <span className="text-xs text-sky-400 font-medium">SCADA/HMI v1.0.0</span>
                  </div>
                </a>
              </div>

              {/* Navigation */}
              <nav className="flex items-center gap-1">
                <NavLink href="/" active={isActive('/')}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                  </svg>
                  Dashboard
                </NavLink>
                <NavLink href="/rtus" active={isActive('/rtus')}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  RTUs
                </NavLink>
                <NavLink href="/alarms" active={isActive('/alarms')}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                  </svg>
                  Alarms
                </NavLink>
                <NavLink href="/trends" active={isActive('/trends')}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                  </svg>
                  Trends
                </NavLink>
                <NavLink href="/control" active={isActive('/control')}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                  </svg>
                  Control
                </NavLink>

                {/* Configuration Dropdown */}
                <div className="relative">
                  <button
                    onClick={() => setShowConfigMenu(!showConfigMenu)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                      isConfigActive
                        ? 'text-white bg-slate-800'
                        : 'text-slate-300 hover:text-white hover:bg-slate-800/50'
                    }`}
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    Configuration
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {showConfigMenu && (
                    <div className="absolute right-0 mt-2 w-48 bg-slate-800 rounded-lg shadow-xl border border-slate-700 py-2 z-50">
                      <a href="/io-tags" className="block px-4 py-2 text-sm text-slate-300 hover:text-white hover:bg-slate-700">
                        I/O Tags
                      </a>
                      <a href="/network" className="block px-4 py-2 text-sm text-slate-300 hover:text-white hover:bg-slate-700">
                        Network
                      </a>
                      <a href="/users" className="block px-4 py-2 text-sm text-slate-300 hover:text-white hover:bg-slate-700">
                        Users
                      </a>
                      <div className="border-t border-slate-700 my-1" />
                      <a href="/settings" className="block px-4 py-2 text-sm text-slate-300 hover:text-white hover:bg-slate-700">
                        Backup & Settings
                      </a>
                    </div>
                  )}
                </div>

                <NavLink href="/system" active={isActive('/system')}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  System
                </NavLink>

                {/* Divider */}
                <div className="w-px h-6 bg-slate-700 mx-2" />

                {/* User Menu */}
                {user ? (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-slate-400">{user.username}</span>
                    <span className="text-xs px-2 py-0.5 bg-slate-700 text-slate-300 rounded">{user.role}</span>
                    <button
                      onClick={handleLogout}
                      className="flex items-center gap-1 px-3 py-2 rounded-lg text-sm text-red-400 hover:text-red-300 hover:bg-slate-800/50 transition-all"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                      </svg>
                      Logout
                    </button>
                  </div>
                ) : (
                  <a
                    href="/login"
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-sky-500 to-blue-600 text-white text-sm font-medium shadow-lg shadow-sky-500/25 hover:shadow-sky-500/40 transition-all hover:-translate-y-0.5"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    Login
                  </a>
                )}
              </nav>
            </div>
          </header>

          {/* Click outside to close config menu */}
          {showConfigMenu && (
            <div
              className="fixed inset-0 z-40"
              onClick={() => setShowConfigMenu(false)}
            />
          )}

          <main className="flex-1 p-6 max-w-[1800px] mx-auto w-full">
            {children}
          </main>

          <footer className="border-t border-slate-800/50 py-4 px-6">
            <div className="max-w-[1800px] mx-auto flex items-center justify-between text-xs text-slate-500">
              <span>Water Treatment Controller SCADA/HMI</span>
              <span>PROFINET I/O Controller - Browser Configuration</span>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}

function NavLink({
  href,
  children,
  active = false,
}: {
  href: string;
  children: React.ReactNode;
  active?: boolean;
}) {
  return (
    <a
      href={href}
      className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
        active
          ? 'text-white bg-slate-800'
          : 'text-slate-300 hover:text-white hover:bg-slate-800/50'
      }`}
    >
      {children}
    </a>
  );
}
