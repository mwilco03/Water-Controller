'use client';

/**
 * Root Layout - ISA-101 Compliant SCADA HMI
 *
 * Design principles:
 * - Clean, professional industrial interface
 * - Gray is normal, color is abnormal
 * - Responsive navigation for all screen sizes
 * - Minimal visual clutter
 * - SINGLE source of truth for system state (no contradictory indicators)
 */

import './globals.css';
import { useState, useEffect, useMemo, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { CommandModeProvider, useCommandMode } from '@/contexts/CommandModeContext';
import { QueryClientProvider } from '@/contexts/QueryClientProvider';
import CommandModeBanner from '@/components/CommandModeBanner';
import { HMIToastProvider, AuthenticationModal, BottomNavigation, GlobalStatusBar } from '@/components/hmi';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useRTUStatusData } from '@/hooks/useRTUStatusData';
import { useKeyboardShortcuts, commonShortcuts } from '@/hooks/useKeyboardShortcuts';
import { PROFINET_STATES } from '@/constants/system';

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
        <QueryClientProvider>
          <CommandModeProvider>
            <HMIToastProvider>
              <AppShell>{children}</AppShell>
            </HMIToastProvider>
          </CommandModeProvider>
        </QueryClientProvider>
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
  const [isApiConnected, setIsApiConnected] = useState(true);
  const lastUpdateRef = useRef<Date>(new Date());
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

  // Get RTU and alarm data for status bar
  const { rtus, alarms, error, dataMode, connected: wsConnected } = useRTUStatusData();

  // Track API connection status based on error state
  useEffect(() => {
    if (error) {
      setIsApiConnected(false);
    } else if (rtus.length >= 0) {
      setIsApiConnected(true);
      lastUpdateRef.current = new Date();
    }
  }, [error, rtus]);

  // Calculate alarm summary
  const activeAlarms = useMemo(() =>
    alarms.filter(a => a.state !== 'CLEARED'),
    [alarms]
  );
  const activeAlarmCount = activeAlarms.length;
  const highestAlarmSeverity = useMemo(() => {
    if (activeAlarms.length === 0) return null;
    const severityOrder = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] as const;
    for (const severity of severityOrder) {
      if (activeAlarms.some(a => a.severity === severity)) {
        return severity;
      }
    }
    return 'MEDIUM' as const;
  }, [activeAlarms]);

  // Prepare RTU status summary for GlobalStatusBar
  const rtuStatusSummary = useMemo(() =>
    rtus.map(rtu => ({
      stationName: rtu.station_name,
      state: rtu.state,
      hasAlarms: (rtu.alarm_count ?? 0) > 0,
    })),
    [rtus]
  );

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
    setConfigMenuOpen(false);
  }, [pathname]);

  const isActive = (path: string) => pathname === path;
  const isConfigActive = CONFIG_ITEMS.some(item => pathname.startsWith(item.href));

  return (
    <div className="min-h-screen flex flex-col">
      {/* Skip Link */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      {/* Command Mode Banner */}
      <CommandModeBanner />

      {/* Header */}
      <header className="hmi-nav sticky top-0 z-50">
        <div className="hmi-container">
          {/* Primary Row: Logo, Nav, Auth */}
          <div className="flex items-center justify-between h-14">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-3 shrink-0">
              <div className="w-8 h-8 rounded-lg bg-status-info flex items-center justify-center">
                <span className="text-white text-xs font-bold">WTC</span>
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
                  <span className="ml-1 text-xs">▼</span>
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

            {/* Right Side - Auth Only */}
            <div className="flex items-center gap-3">
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
                className="lg:hidden p-2 rounded-md hover:bg-hmi-bg text-hmi-text font-medium"
                aria-label="Toggle menu"
              >
                {mobileMenuOpen ? (
                  <span className="text-lg">×</span>
                ) : (
                  <span className="text-sm">Menu</span>
                )}
              </button>
            </div>
          </div>

          {/* Status Row: GlobalStatusBar - Visible on all screens */}
          <div className="border-t border-hmi-border py-2">
            <GlobalStatusBar
              isApiConnected={isApiConnected}
              isWebSocketConnected={wsConnected}
              profinetState={PROFINET_STATES.RUN}
              rtus={rtuStatusSummary}
              activeAlarmCount={activeAlarmCount}
              highestAlarmSeverity={highestAlarmSeverity}
              lastUpdate={lastUpdateRef.current}
            />
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
                className="p-1 hover:bg-hmi-bg rounded text-hmi-muted text-xl leading-none"
                aria-label="Close"
              >
                ×
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

// Simple text-based icon component (no SVGs)
function NavIcon({ name }: { name: string }) {
  // Text-based icon alternatives - navigation items already have text labels
  // These are minimal visual markers to maintain spacing consistency
  const icons: Record<string, React.ReactNode> = {
    grid: <span className="text-xs font-mono">::</span>,
    server: <span className="text-xs font-mono">[]</span>,
    bell: <span className="text-xs font-mono">!</span>,
    chart: <span className="text-xs font-mono">~</span>,
    sliders: <span className="text-xs font-mono">=</span>,
    cog: <span className="text-xs font-mono">*</span>,
    activity: <span className="text-xs font-mono">#</span>,
  };
  return icons[name] || null;
}
