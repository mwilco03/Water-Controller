'use client';

/**
 * SideNav - Icon rail with slide-out panel (LEFT side)
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Squares2X2Icon,
  ServerStackIcon,
  BellAlertIcon,
  ChartBarSquareIcon,
  AdjustmentsHorizontalIcon,
  Cog6ToothIcon,
  ComputerDesktopIcon,
  UserCircleIcon,
  XMarkIcon,
  ChevronRightIcon,
  TagIcon,
  GlobeAltIcon,
  UsersIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline';

interface SideNavProps {
  activeAlarmCount?: number;
  isAuthenticated?: boolean;
  onLoginClick?: () => void;
  onLogoutClick?: () => void;
}

interface NavItem {
  id: string;
  href: string;
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const MAIN_NAV: NavItem[] = [
  { id: 'status', href: '/', label: 'Status', Icon: Squares2X2Icon },
  { id: 'rtus', href: '/rtus', label: 'RTUs', Icon: ServerStackIcon },
  { id: 'alarms', href: '/alarms', label: 'Alarms', Icon: BellAlertIcon },
  { id: 'trends', href: '/trends', label: 'Trends', Icon: ChartBarSquareIcon },
  { id: 'control', href: '/control', label: 'Control', Icon: AdjustmentsHorizontalIcon },
];

const CONFIG_NAV: NavItem[] = [
  { id: 'io-tags', href: '/io-tags', label: 'I/O Tags', Icon: TagIcon },
  { id: 'modbus', href: '/modbus', label: 'Modbus', Icon: CpuChipIcon },
  { id: 'network', href: '/network', label: 'Network', Icon: GlobeAltIcon },
  { id: 'users', href: '/users', label: 'Users', Icon: UsersIcon },
  { id: 'settings', href: '/settings', label: 'Settings', Icon: Cog6ToothIcon },
];

export function SideNav({
  activeAlarmCount = 0,
  isAuthenticated = false,
  onLoginClick,
  onLogoutClick,
}: SideNavProps) {
  const pathname = usePathname();
  const [activePanel, setActivePanel] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  const togglePanel = (panelId: string) => {
    setActivePanel(activePanel === panelId ? null : panelId);
  };

  const closePanel = () => setActivePanel(null);

  if (!mounted) return null;

  return (
    <>
      {/* Icon Rail - LEFT side */}
      <aside className="hidden lg:flex flex-col fixed left-0 top-0 bottom-0 w-12 bg-white border-r border-gray-200 z-40">
        {/* Main nav icons */}
        <div className="flex-1 flex flex-col items-center py-2 gap-1">
          {MAIN_NAV.map((item) => (
            <button
              key={item.id}
              onClick={() => togglePanel(item.id)}
              className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors relative ${
                activePanel === item.id || isActive(item.href)
                  ? 'bg-blue-100 text-blue-600'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
              }`}
              title={item.label}
            >
              <item.Icon className="w-5 h-5" />
              {item.id === 'alarms' && activeAlarmCount > 0 && (
                <span className="absolute top-0.5 right-0.5 min-w-[16px] h-4 px-1 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                  {activeAlarmCount > 99 ? '99+' : activeAlarmCount}
                </span>
              )}
            </button>
          ))}

          <div className="w-6 border-t border-gray-200 my-2" />

          {/* Config button */}
          <button
            onClick={() => togglePanel('config')}
            className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${
              activePanel === 'config'
                ? 'bg-blue-100 text-blue-600'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
            }`}
            title="Configuration"
          >
            <Cog6ToothIcon className="w-5 h-5" />
          </button>

          {/* System */}
          <Link
            href="/system"
            className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${
              isActive('/system')
                ? 'bg-blue-100 text-blue-600'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
            }`}
            title="System"
          >
            <ComputerDesktopIcon className="w-5 h-5" />
          </Link>
        </div>

        {/* User at bottom */}
        <div className="py-2 flex flex-col items-center border-t border-gray-200">
          <button
            onClick={isAuthenticated ? onLogoutClick : onLoginClick}
            className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors"
            title={isAuthenticated ? 'Logout' : 'Login'}
          >
            <UserCircleIcon className="w-5 h-5" />
          </button>
        </div>
      </aside>

      {/* Slide-out Panel - appears to RIGHT of icon rail */}
      {activePanel && (
        <>
          {/* Backdrop */}
          <div
            className="hidden lg:block fixed inset-0 bg-black/20 z-30"
            onClick={closePanel}
          />

          {/* Panel */}
          <div className="hidden lg:block fixed left-12 top-0 bottom-0 w-64 bg-white border-r border-gray-200 shadow-lg z-35 animate-slide-in">
            {/* Panel Header */}
            <div className="h-14 flex items-center justify-between px-4 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">
                {activePanel === 'config' ? 'Configuration' : MAIN_NAV.find(n => n.id === activePanel)?.label}
              </h2>
              <button
                onClick={closePanel}
                className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100"
              >
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>

            {/* Panel Content */}
            <div className="p-2">
              {activePanel === 'config' ? (
                <nav className="space-y-1">
                  {CONFIG_NAV.map((item) => (
                    <Link
                      key={item.id}
                      href={item.href}
                      onClick={closePanel}
                      className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                        isActive(item.href)
                          ? 'bg-blue-50 text-blue-600'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      <item.Icon className="w-5 h-5" />
                      {item.label}
                    </Link>
                  ))}
                </nav>
              ) : (
                <Link
                  href={MAIN_NAV.find(n => n.id === activePanel)?.href || '/'}
                  onClick={closePanel}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm bg-blue-50 text-blue-600"
                >
                  <ChevronRightIcon className="w-4 h-4" />
                  Go to {MAIN_NAV.find(n => n.id === activePanel)?.label}
                </Link>
              )}
            </div>
          </div>
        </>
      )}

      <style jsx>{`
        @keyframes slide-in {
          from {
            transform: translateX(-100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
        .animate-slide-in {
          animation: slide-in 0.15s ease-out;
        }
      `}</style>
    </>
  );
}

export default SideNav;
