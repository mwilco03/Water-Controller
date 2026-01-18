'use client';

/**
 * Root Layout - ISA-101 Compliant SCADA HMI
 *
 * Design principles:
 * - Desktop: Collapsible side panel (icons-only default)
 * - Mobile: Bottom navigation (no horizontal scroll)
 * - Tablet: Collapsed side panel (icons only)
 * - Login de-emphasized (in side panel, not header)
 * - Alarm count always visible
 */

import './globals.css';
import { useState, useEffect, useMemo, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { CommandModeProvider, useCommandMode } from '@/contexts/CommandModeContext';
import { QueryClientProvider } from '@/contexts/QueryClientProvider';
import CommandModeBanner from '@/components/CommandModeBanner';
import { HMIToastProvider, AuthenticationModal, GlobalStatusBar } from '@/components/hmi';
import SideNav from '@/components/hmi/SideNav';
import BottomNavigation from '@/components/hmi/BottomNavigation';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useRTUStatusData } from '@/hooks/useRTUStatusData';
import { useKeyboardShortcuts, commonShortcuts } from '@/hooks/useKeyboardShortcuts';
import { PROFINET_STATES } from '@/constants/system';

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
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);
  const [isApiConnected, setIsApiConnected] = useState(true);
  const lastUpdateRef = useRef<Date>(new Date());
  const { isAuthenticated, exitCommandMode } = useCommandMode();

  // Global keyboard shortcuts
  const shortcuts = useMemo(() => [
    { key: 'a', description: 'Go to Alarms', handler: () => router.push('/alarms') },
    { key: 'c', description: 'Go to Control', handler: () => router.push('/control') },
    { key: 't', description: 'Go to Trends', handler: () => router.push('/trends') },
    { key: 's', description: 'Go to Status (home)', handler: () => router.push('/') },
    { key: 'r', description: 'Go to RTUs', handler: () => router.push('/rtus') },
    commonShortcuts.help(() => setShowShortcutsHelp(true)),
    commonShortcuts.escape(() => setShowShortcutsHelp(false)),
  ], [router]);

  useKeyboardShortcuts(shortcuts);

  // Get RTU and alarm data
  const { rtus, alarms, error, connected: wsConnected } = useRTUStatusData();

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

  const rtuStatusSummary = useMemo(() =>
    rtus.map(rtu => ({
      stationName: rtu.station_name,
      state: rtu.state,
      hasAlarms: (rtu.alarm_count ?? 0) > 0,
    })),
    [rtus]
  );

  return (
    <div className="min-h-screen flex">
      {/* Skip Link */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      {/* Desktop Side Navigation */}
      <SideNav
        activeAlarmCount={activeAlarmCount}
        isAuthenticated={isAuthenticated}
        onLoginClick={() => setShowLoginModal(true)}
        onLogoutClick={exitCommandMode}
      />

      {/* Main content area - left margin for icon rail on desktop */}
      <div className="flex-1 flex flex-col lg:ml-14">
        {/* Command Mode Banner */}
        <CommandModeBanner />

        {/* ALARM BANNER - Attention seeking when alarms active */}
        {activeAlarmCount > 0 && (
          <Link
            href="/alarms"
            className={`
              flex items-center justify-center gap-3 px-4 py-2 text-white font-medium
              ${highestAlarmSeverity === 'CRITICAL' || highestAlarmSeverity === 'HIGH'
                ? 'bg-red-600 animate-pulse'
                : 'bg-orange-500'
              }
              hover:brightness-110 transition-all
            `}
          >
            <span className="text-xl">⚠️</span>
            <span>
              {activeAlarmCount} Active Alarm{activeAlarmCount !== 1 ? 's' : ''}
              {highestAlarmSeverity && ` - ${highestAlarmSeverity}`}
            </span>
            <span className="text-sm opacity-80">Click to view →</span>
          </Link>
        )}

        {/* Mobile Header - only on smaller screens */}
        <header className="lg:hidden hmi-nav sticky top-0 z-30">
          <div className="hmi-container">
            <div className="flex items-center justify-between h-12">
              {/* Logo */}
              <Link href="/" className="flex items-center gap-2">
                <span className="text-lg font-bold text-status-info">WTC</span>
                <span className="text-sm text-hmi-muted hidden sm:inline">Water Treatment</span>
              </Link>

              {/* Status indicators */}
              <div className="flex items-center gap-3">
                {/* Connection status */}
                <span
                  className={`w-2 h-2 rounded-full ${isApiConnected ? 'bg-status-ok' : 'bg-status-alarm'}`}
                  title={isApiConnected ? 'Connected' : 'Disconnected'}
                />

                {/* Alarm badge - links to alarms */}
                {activeAlarmCount > 0 && (
                  <Link
                    href="/alarms"
                    className="flex items-center gap-1 px-2 py-1 bg-status-alarm/10 text-status-alarm rounded text-sm font-medium"
                  >
                    <span>⚠️</span>
                    <span>{activeAlarmCount}</span>
                  </Link>
                )}

                {/* Auth button - de-emphasized */}
                {isAuthenticated ? (
                  <button
                    onClick={exitCommandMode}
                    className="p-2 text-hmi-muted hover:text-hmi-text"
                    title="Logout"
                  >
                    🔓
                  </button>
                ) : (
                  <button
                    onClick={() => setShowLoginModal(true)}
                    className="p-2 text-hmi-muted hover:text-hmi-text"
                    title="Login"
                  >
                    🔐
                  </button>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Desktop Header - minimal status bar */}
        <header className="hidden lg:block border-b border-hmi-border bg-hmi-panel">
          <div className="px-4 py-2">
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
        </header>

        {/* Main Content */}
        <main id="main-content" className="flex-1">
          <div className="hmi-container py-4">
            {children}
          </div>
        </main>

        {/* Footer - minimal, desktop only */}
        <footer className="hidden lg:block border-t border-hmi-border py-2">
          <div className="hmi-container flex items-center justify-between text-xs text-hmi-muted">
            <span>Water Treatment Controller v1.0</span>
            <button
              onClick={() => setShowShortcutsHelp(true)}
              className="hover:text-hmi-text transition-colors flex items-center gap-1"
            >
              <kbd className="px-1 py-0.5 bg-hmi-bg rounded border border-hmi-border">?</kbd>
              <span>Shortcuts</span>
            </button>
          </div>
        </footer>
      </div>

      {/* Mobile Bottom Navigation */}
      <BottomNavigation activeAlarmCount={activeAlarmCount} />

      {/* Login Modal */}
      <AuthenticationModal
        isOpen={showLoginModal}
        actionDescription="Access Command Mode"
        onClose={() => setShowLoginModal(false)}
        onSuccess={() => setShowLoginModal(false)}
      />

      {/* Keyboard Shortcuts Dialog */}
      {showShortcutsHelp && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setShowShortcutsHelp(false)}
        >
          <div
            className="bg-hmi-panel rounded-lg p-4 max-w-sm w-full mx-4 border border-hmi-border shadow-lg"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-hmi-text">Keyboard Shortcuts</h3>
              <button
                onClick={() => setShowShortcutsHelp(false)}
                className="p-1 hover:bg-hmi-bg rounded text-hmi-muted"
              >
                ✕
              </button>
            </div>

            <div className="space-y-2 text-sm">
              <div className="text-xs text-hmi-muted uppercase mb-2">Navigation</div>
              {[
                { key: 'A', desc: 'Alarms' },
                { key: 'C', desc: 'Control' },
                { key: 'T', desc: 'Trends' },
                { key: 'S', desc: 'Status' },
                { key: 'R', desc: 'RTUs' },
              ].map(({ key, desc }) => (
                <div key={key} className="flex items-center justify-between py-1">
                  <span className="text-hmi-text">{desc}</span>
                  <kbd className="px-2 py-0.5 bg-hmi-bg rounded border border-hmi-border text-xs font-mono">{key}</kbd>
                </div>
              ))}

              <div className="border-t border-hmi-border pt-2 mt-2">
                <div className="text-xs text-hmi-muted uppercase mb-2">General</div>
                {[
                  { key: '?', desc: 'This help' },
                  { key: 'Esc', desc: 'Close dialogs' },
                ].map(({ key, desc }) => (
                  <div key={key} className="flex items-center justify-between py-1">
                    <span className="text-hmi-text">{desc}</span>
                    <kbd className="px-2 py-0.5 bg-hmi-bg rounded border border-hmi-border text-xs font-mono">{key}</kbd>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

