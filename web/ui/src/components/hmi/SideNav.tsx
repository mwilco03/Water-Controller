'use client';

/**
 * SideNav - Collapsible side navigation for desktop
 *
 * Design principles:
 * - Icons-only by default (collapsed state)
 * - Expands on click to show labels
 * - Persists preference in localStorage
 * - Alarm badge always visible
 * - Config section collapsed by default
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

interface NavItem {
  href: string;
  label: string;
  icon: string;
  shortLabel: string;
  badge?: number;
}

interface SideNavProps {
  activeAlarmCount?: number;
  isAuthenticated?: boolean;
  onLoginClick?: () => void;
  onLogoutClick?: () => void;
}

const STORAGE_KEY = 'sidenav-expanded';

const NAV_ITEMS: NavItem[] = [
  { href: '/', label: 'Status', icon: '📊', shortLabel: 'STS' },
  { href: '/rtus', label: 'RTUs', icon: '📡', shortLabel: 'RTU' },
  { href: '/alarms', label: 'Alarms', icon: '⚠️', shortLabel: 'ALM' },
  { href: '/trends', label: 'Trends', icon: '📈', shortLabel: 'TRD' },
  { href: '/control', label: 'Control', icon: '⚙️', shortLabel: 'CTL' },
];

const CONFIG_ITEMS: NavItem[] = [
  { href: '/io-tags', label: 'I/O Tags', icon: '🏷️', shortLabel: 'I/O' },
  { href: '/modbus', label: 'Modbus', icon: '🔌', shortLabel: 'MOD' },
  { href: '/network', label: 'Network', icon: '🌐', shortLabel: 'NET' },
  { href: '/users', label: 'Users', icon: '👤', shortLabel: 'USR' },
  { href: '/settings', label: 'Settings', icon: '🛠️', shortLabel: 'SET' },
];

const SYSTEM_ITEM: NavItem = { href: '/system', label: 'System', icon: '🖥️', shortLabel: 'SYS' };

export function SideNav({
  activeAlarmCount = 0,
  isAuthenticated = false,
  onLoginClick,
  onLogoutClick
}: SideNavProps) {
  const pathname = usePathname();
  const [isExpanded, setIsExpanded] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Load preference from localStorage
  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'true') {
      setIsExpanded(true);
    }
  }, []);

  // Save preference
  const toggleExpanded = () => {
    const next = !isExpanded;
    setIsExpanded(next);
    localStorage.setItem(STORAGE_KEY, String(next));
  };

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  const isConfigActive = CONFIG_ITEMS.some(item => isActive(item.href));

  // Don't render until mounted to avoid hydration mismatch
  if (!mounted) return null;

  return (
    <aside
      className={`
        hidden lg:flex flex-col
        fixed left-0 top-0 bottom-0
        bg-hmi-panel border-r border-hmi-border
        transition-all duration-200 ease-out
        z-40
        ${isExpanded ? 'w-48' : 'w-14'}
      `}
    >
      {/* Toggle button */}
      <button
        onClick={toggleExpanded}
        className="h-14 flex items-center justify-center border-b border-hmi-border hover:bg-hmi-bg transition-colors"
        aria-label={isExpanded ? 'Collapse navigation' : 'Expand navigation'}
        title={isExpanded ? 'Collapse' : 'Expand'}
      >
        <span className="text-lg">{isExpanded ? '◀' : '▶'}</span>
      </button>

      {/* Main navigation */}
      <nav className="flex-1 py-2 overflow-y-auto">
        <ul className="space-y-1 px-2">
          {NAV_ITEMS.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className={`
                  flex items-center gap-3 px-2 py-2 rounded-md
                  transition-colors text-sm font-medium
                  ${isActive(item.href)
                    ? 'bg-status-info/10 text-status-info'
                    : 'text-hmi-muted hover:bg-hmi-bg hover:text-hmi-text'}
                `}
                title={!isExpanded ? item.label : undefined}
              >
                <span className="relative flex-shrink-0 w-6 text-center">
                  {item.href === '/alarms' && activeAlarmCount > 0 && (
                    <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 bg-status-alarm text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                      {activeAlarmCount > 99 ? '99+' : activeAlarmCount}
                    </span>
                  )}
                  <span>{item.icon}</span>
                </span>
                {isExpanded && <span>{item.label}</span>}
              </Link>
            </li>
          ))}
        </ul>

        {/* Config section - collapsible */}
        <div className="mt-4 pt-4 border-t border-hmi-border px-2">
          <button
            onClick={() => setConfigOpen(!configOpen)}
            className={`
              w-full flex items-center gap-3 px-2 py-2 rounded-md
              transition-colors text-sm font-medium
              ${isConfigActive
                ? 'bg-status-info/10 text-status-info'
                : 'text-hmi-muted hover:bg-hmi-bg hover:text-hmi-text'}
            `}
            title={!isExpanded ? 'Config' : undefined}
          >
            <span className="flex-shrink-0 w-6 text-center">🔧</span>
            {isExpanded && (
              <>
                <span className="flex-1 text-left">Config</span>
                <span className="text-xs">{configOpen ? '▼' : '▶'}</span>
              </>
            )}
          </button>

          {configOpen && (
            <ul className="mt-1 space-y-1 ml-2">
              {CONFIG_ITEMS.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={`
                      flex items-center gap-3 px-2 py-1.5 rounded-md
                      transition-colors text-sm
                      ${isActive(item.href)
                        ? 'bg-status-info/10 text-status-info'
                        : 'text-hmi-muted hover:bg-hmi-bg hover:text-hmi-text'}
                    `}
                    title={!isExpanded ? item.label : undefined}
                  >
                    <span className="flex-shrink-0 w-5 text-center text-xs">{item.icon}</span>
                    {isExpanded && <span>{item.label}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* System link */}
        <div className="mt-2 px-2">
          <Link
            href={SYSTEM_ITEM.href}
            className={`
              flex items-center gap-3 px-2 py-2 rounded-md
              transition-colors text-sm font-medium
              ${isActive(SYSTEM_ITEM.href)
                ? 'bg-status-info/10 text-status-info'
                : 'text-hmi-muted hover:bg-hmi-bg hover:text-hmi-text'}
            `}
            title={!isExpanded ? SYSTEM_ITEM.label : undefined}
          >
            <span className="flex-shrink-0 w-6 text-center">{SYSTEM_ITEM.icon}</span>
            {isExpanded && <span>{SYSTEM_ITEM.label}</span>}
          </Link>
        </div>
      </nav>

      {/* User section at bottom */}
      <div className="border-t border-hmi-border p-2">
        {isAuthenticated ? (
          <button
            onClick={onLogoutClick}
            className="w-full flex items-center gap-3 px-2 py-2 rounded-md text-sm text-hmi-muted hover:bg-hmi-bg hover:text-hmi-text transition-colors"
            title={!isExpanded ? 'Logout' : undefined}
          >
            <span className="flex-shrink-0 w-6 text-center">🔓</span>
            {isExpanded && <span>Logout</span>}
          </button>
        ) : (
          <button
            onClick={onLoginClick}
            className="w-full flex items-center gap-3 px-2 py-2 rounded-md text-sm text-hmi-muted hover:bg-hmi-bg hover:text-hmi-text transition-colors"
            title={!isExpanded ? 'Login' : undefined}
          >
            <span className="flex-shrink-0 w-6 text-center">🔐</span>
            {isExpanded && <span>Login</span>}
          </button>
        )}

        {/* Keyboard shortcuts hint */}
        {isExpanded && (
          <div className="mt-2 px-2 py-1 text-xs text-hmi-muted">
            Press <kbd className="px-1 bg-hmi-bg rounded border border-hmi-border">?</kbd> for shortcuts
          </div>
        )}
      </div>
    </aside>
  );
}

export default SideNav;
