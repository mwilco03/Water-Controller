'use client';

/**
 * Root Layout - ISA-101 Compliant SCADA HMI
 *
 * Design principles:
 * - Clean, professional industrial interface
 * - Gray is normal, color is abnormal
 * - Responsive navigation for all screen sizes
 * - Minimal visual clutter
 */

import './globals.css';
import { useState, useEffect, useMemo } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { CommandModeProvider, useCommandMode } from '@/contexts/CommandModeContext';
import CommandModeBanner from '@/components/CommandModeBanner';
import { HMIToastProvider, AuthenticationModal, DegradedModeBanner, BottomNavigation } from '@/components/hmi';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useRTUStatusData } from '@/hooks/useRTUStatusData';
import { useKeyboardShortcuts, commonShortcuts, getRegisteredShortcuts, formatShortcut } from '@/hooks/useKeyboardShortcuts';

// Navigation items configuration
const NAV_ITEMS = [
  { href: '/', label: 'Status', icon: 'grid' },
  { href: '/rtus', label: 'RTUs', icon: 'server' },
  { href: '/alarms', label: 'Alarms', icon: 'bell' },
  { href: '/trends', label: 'Trends', icon: 'chart' },
  { href: '/control', label: 'Control', icon: 'sliders' },
] as const;

const CONFIG_ITEMS = [
  { href: '/io-tags', label: 'I/O Tags' },
  { href: '/modbus', label: 'Modbus' },
  { href: '/network', label: 'Network' },
  { href: '/users', label: 'Users' },
  { href: '/settings', label: 'Settings' },
] as const;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <title>Water Treatment Controller</title>
        <meta name="description" content="SCADA HMI for Water Treatment RTU Network" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        {/* Local fonts for air-gapped deployment - no external network calls */}
        {/* eslint-disable-next-line @next/next/no-css-tags -- Intentional for air-gapped deployments */}
        <link rel="stylesheet" href="/fonts/fonts.css" />
      </head>
      <body className="bg-hmi-bg text-hmi-text">
        <CommandModeProvider>
          <HMIToastProvider>
            <AppShell>{children}</AppShell>
          </HMIToastProvider>
        </CommandModeProvider>
      </body>
    </html>
  );
}

function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [configMenuOpen, setConfigMenuOpen] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);
  const [degradedSince, setDegradedSince] = useState<Date | null>(null);
  const { isAuthenticated, exitCommandMode } = useCommandMode();

  // Global keyboard shortcuts for veteran operators
  const shortcuts = useMemo(() => [
    // Single-key navigation (no modifiers required)
    { key: 'a', description: 'Go to Alarms', handler: () => router.push('/alarms') },
    { key: 'c', description: 'Go to Control', handler: () => router.push('/control') },
    { key: 't', description: 'Go to Trends', handler: () => router.push('/trends') },
    { key: 's', description: 'Go to Status (home)', handler: () => router.push('/') },
    { key: 'r', description: 'Go to RTUs', handler: () => router.push('/rtus') },
    // Help shortcut
    commonShortcuts.help(() => setShowShortcutsHelp(true)),
    commonShortcuts.escape(() => setShowShortcutsHelp(false)),
  ], [router]);

  useKeyboardShortcuts(shortcuts);

  // Get alarm data for bottom nav badge
  const { alarms } = useRTUStatusData();
  const activeAlarmCount = alarms.filter(a => a.state !== 'CLEARED').length;

  // WebSocket connection status
  const { connected } = useWebSocket({
    onConnect: () => setDegradedSince(null),
    onDisconnect: () => setDegradedSince(new Date()),
  });

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
    setConfigMenuOpen(false);
  }, [pathname]);

  const isActive = (path: string) => pathname === path;
  const isConfigActive = CONFIG_ITEMS.some(item => pathname.startsWith(item.href));

  // Degraded mode info
  const degradedInfo = !connected ? {
    reason: 'websocket_disconnected' as const,
    message: 'Real-time updates unavailable. Using polling.',
    details: 'Attempting to reconnect...',
    since: degradedSince || undefined,
  } : null;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Skip Link */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      {/* Command Mode Banner */}
      <CommandModeBanner />

      {/* Degraded Mode Banner */}
      {degradedInfo && <DegradedModeBanner degradedInfo={degradedInfo} />}

      {/* Header */}
      <header className="hmi-nav sticky top-0 z-50">
        <div className="hmi-container">
          <div className="flex items-center justify-between h-14">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-3 shrink-0">
              <div className="w-8 h-8 rounded-lg bg-status-info flex items-center justify-center">
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                </svg>
              </div>
              <div className="hidden sm:block">
                <div className="font-semibold text-hmi-text leading-tight">Water Treatment</div>
                <div className="text-xs text-hmi-muted">SCADA/HMI</div>
              </div>
            </Link>

            {/* Desktop Navigation */}
            <nav className="hidden lg:flex items-center gap-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`hmi-nav-link ${isActive(item.href) ? 'active' : ''}`}
                >
                  <NavIcon name={item.icon} />
                  {item.label}
                </Link>
              ))}

              {/* Config Dropdown */}
              <div className="relative ml-2">
                <button
                  onClick={() => setConfigMenuOpen(!configMenuOpen)}
                  className={`hmi-nav-link ${isConfigActive ? 'active' : ''}`}
                >
                  <NavIcon name="cog" />
                  Config
                  <svg className="w-3 h-3 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {configMenuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setConfigMenuOpen(false)} />
                    <div className="absolute right-0 mt-2 w-48 bg-hmi-panel rounded-lg shadow-card-hover border border-hmi-border py-1 z-50">
                      {CONFIG_ITEMS.map((item) => (
                        <Link
                          key={item.href}
                          href={item.href}
                          className="block px-4 py-2 text-sm text-hmi-text hover:bg-hmi-bg"
                        >
                          {item.label}
                        </Link>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <Link href="/system" className={`hmi-nav-link ${isActive('/system') ? 'active' : ''}`}>
                <NavIcon name="activity" />
                System
              </Link>
            </nav>

            {/* Right Side - Status & Auth */}
            <div className="flex items-center gap-3">
              {/* Connection Status */}
              <div className="hidden sm:flex items-center gap-2 text-sm">
                <span className={`status-dot ${connected ? 'ok' : 'offline'}`} />
                <span className="text-hmi-muted">{connected ? 'Online' : 'Offline'}</span>
              </div>

              {/* Auth Button */}
              {isAuthenticated ? (
                <button
                  onClick={exitCommandMode}
                  className="hmi-btn hmi-btn-secondary text-sm"
                >
                  Logout
                </button>
              ) : (
                <button
                  onClick={() => setShowLoginModal(true)}
                  className="hmi-btn hmi-btn-primary text-sm"
                >
                  Login
                </button>
              )}

              {/* Mobile Menu Button */}
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="lg:hidden p-2 rounded-md hover:bg-hmi-bg"
                aria-label="Toggle menu"
              >
                <svg className="w-6 h-6 text-hmi-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  {mobileMenuOpen ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  )}
                </svg>
              </button>
            </div>
          </div>

          {/* Mobile Navigation */}
          {mobileMenuOpen && (
            <nav className="lg:hidden py-4 border-t border-hmi-border">
              <div className="grid gap-1">
                {NAV_ITEMS.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`hmi-nav-link ${isActive(item.href) ? 'active' : ''}`}
                  >
                    <NavIcon name={item.icon} />
                    {item.label}
                  </Link>
                ))}
                <div className="border-t border-hmi-border my-2" />
                <div className="text-xs font-medium text-hmi-muted uppercase px-4 py-2">Configuration</div>
                {CONFIG_ITEMS.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`hmi-nav-link ${isActive(item.href) ? 'active' : ''}`}
                  >
                    {item.label}
                  </Link>
                ))}
                <div className="border-t border-hmi-border my-2" />
                <Link href="/system" className={`hmi-nav-link ${isActive('/system') ? 'active' : ''}`}>
                  <NavIcon name="activity" />
                  System
                </Link>
              </div>
            </nav>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main id="main-content" className="flex-1 has-bottom-nav">
        <div className="hmi-container py-6">
          {children}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-hmi-border py-4 mt-auto">
        <div className="hmi-container flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-hmi-muted">
          <span>Water Treatment Controller SCADA/HMI</span>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setShowShortcutsHelp(true)}
              className="hover:text-hmi-text transition-colors flex items-center gap-1"
              title="Keyboard shortcuts"
            >
              <kbd className="px-1.5 py-0.5 bg-hmi-bg rounded border border-hmi-border text-xs">?</kbd>
              <span>Shortcuts</span>
            </button>
            <span>PROFINET I/O Controller v1.0</span>
          </div>
        </div>
      </footer>

      {/* Login Modal */}
      <AuthenticationModal
        isOpen={showLoginModal}
        actionDescription="Access Command Mode"
        onClose={() => setShowLoginModal(false)}
        onSuccess={() => setShowLoginModal(false)}
      />

      {/* Keyboard Shortcuts Help Dialog */}
      {showShortcutsHelp && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowShortcutsHelp(false)}>
          <div className="bg-hmi-panel rounded-lg p-6 max-w-md w-full mx-4 border border-hmi-border shadow-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-hmi-text">Keyboard Shortcuts</h3>
              <button
                onClick={() => setShowShortcutsHelp(false)}
                className="p-1 hover:bg-hmi-bg rounded"
                aria-label="Close"
              >
                <svg className="w-5 h-5 text-hmi-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="space-y-3">
              <div className="text-sm text-hmi-muted mb-2">Navigation</div>
              <div className="grid gap-2">
                {[
                  { key: 'A', desc: 'Go to Alarms' },
                  { key: 'C', desc: 'Go to Control' },
                  { key: 'T', desc: 'Go to Trends' },
                  { key: 'S', desc: 'Go to Status (home)' },
                  { key: 'R', desc: 'Go to RTUs' },
                ].map(({ key, desc }) => (
                  <div key={key} className="flex items-center justify-between py-1">
                    <span className="text-hmi-text text-sm">{desc}</span>
                    <kbd className="px-2 py-1 bg-hmi-bg rounded border border-hmi-border text-xs font-mono text-hmi-text">{key}</kbd>
                  </div>
                ))}
              </div>

              <div className="border-t border-hmi-border pt-3 mt-3">
                <div className="text-sm text-hmi-muted mb-2">General</div>
                <div className="grid gap-2">
                  {[
                    { key: 'Shift + ?', desc: 'Show this help' },
                    { key: 'Esc', desc: 'Close dialogs' },
                    { key: 'Enter', desc: 'Confirm action' },
                  ].map(({ key, desc }) => (
                    <div key={key} className="flex items-center justify-between py-1">
                      <span className="text-hmi-text text-sm">{desc}</span>
                      <kbd className="px-2 py-1 bg-hmi-bg rounded border border-hmi-border text-xs font-mono text-hmi-text">{key}</kbd>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <p className="text-xs text-hmi-muted mt-4">
              Shortcuts are disabled when typing in input fields
            </p>
          </div>
        </div>
      )}

      {/* Bottom Navigation (Mobile) */}
      <BottomNavigation activeAlarmCount={activeAlarmCount} />
    </div>
  );
}

// Simple icon component
function NavIcon({ name }: { name: string }) {
  const icons: Record<string, React.ReactNode> = {
    grid: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
      </svg>
    ),
    server: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
    ),
    bell: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
      </svg>
    ),
    chart: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
      </svg>
    ),
    sliders: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
      </svg>
    ),
    cog: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    activity: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  };
  return icons[name] || null;
}
