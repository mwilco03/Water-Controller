'use client';

/**
 * SideNav - Icon rail with direct navigation (LEFT side)
 *
 * Design: Click icon = navigate to page (not open panel)
 * Config gear opens submenu panel
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
  HomeIcon,
  TagIcon,
  GlobeAltIcon,
  UsersIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline';
import {
  Squares2X2Icon as Squares2X2IconSolid,
  ServerStackIcon as ServerStackIconSolid,
  BellAlertIcon as BellAlertIconSolid,
  ChartBarSquareIcon as ChartBarSquareIconSolid,
  AdjustmentsHorizontalIcon as AdjustmentsHorizontalIconSolid,
  ComputerDesktopIcon as ComputerDesktopIconSolid,
} from '@heroicons/react/24/solid';

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
  IconSolid?: React.ComponentType<{ className?: string }>;
}

const MAIN_NAV: NavItem[] = [
  { id: 'status', href: '/', label: 'Status', Icon: Squares2X2Icon, IconSolid: Squares2X2IconSolid },
  { id: 'rtus', href: '/rtus', label: 'RTUs', Icon: ServerStackIcon, IconSolid: ServerStackIconSolid },
  { id: 'alarms', href: '/alarms', label: 'Alarms', Icon: BellAlertIcon, IconSolid: BellAlertIconSolid },
  { id: 'trends', href: '/trends', label: 'Trends', Icon: ChartBarSquareIcon, IconSolid: ChartBarSquareIconSolid },
  { id: 'control', href: '/control', label: 'Control', Icon: AdjustmentsHorizontalIcon, IconSolid: AdjustmentsHorizontalIconSolid },
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
  const [configOpen, setConfigOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  const isConfigActive = () => {
    return CONFIG_NAV.some(item => pathname.startsWith(item.href));
  };

  if (!mounted) return null;

  return (
    <>
      {/* Icon Rail - LEFT side */}
      <aside className="hidden lg:flex flex-col fixed left-0 top-0 bottom-0 w-14 bg-white border-r border-gray-200 z-40">
        {/* Home/Logo at top - ALWAYS navigates home */}
        <div className="h-14 flex items-center justify-center border-b border-gray-200">
          <Link
            href="/"
            className="w-10 h-10 flex items-center justify-center rounded-lg text-blue-600 hover:bg-blue-50 transition-colors"
            title="Home - Water Treatment Controller"
          >
            <HomeIcon className="w-6 h-6" />
          </Link>
        </div>

        {/* Main nav icons - DIRECT LINKS */}
        <div className="flex-1 flex flex-col items-center py-2 gap-1">
          {MAIN_NAV.map((item) => {
            const active = isActive(item.href);
            const IconComponent = active && item.IconSolid ? item.IconSolid : item.Icon;

            return (
              <Link
                key={item.id}
                href={item.href}
                className={`w-11 h-11 flex items-center justify-center rounded-lg transition-colors relative ${
                  active
                    ? 'bg-blue-100 text-blue-600'
                    : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
                }`}
                title={item.label}
              >
                <IconComponent className="w-5 h-5" />
                {item.id === 'alarms' && activeAlarmCount > 0 && (
                  <span className={`absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center ${activeAlarmCount > 0 ? 'animate-pulse' : ''}`}>
                    {activeAlarmCount > 99 ? '99+' : activeAlarmCount}
                  </span>
                )}
              </Link>
            );
          })}

          <div className="w-8 border-t border-gray-200 my-2" />

          {/* Config button - opens submenu */}
          <button
            onClick={() => setConfigOpen(!configOpen)}
            className={`w-11 h-11 flex items-center justify-center rounded-lg transition-colors ${
              configOpen || isConfigActive()
                ? 'bg-blue-100 text-blue-600'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
            }`}
            title="Configuration"
          >
            <Cog6ToothIcon className="w-5 h-5" />
          </button>

          {/* System - DIRECT LINK */}
          <Link
            href="/system"
            className={`w-11 h-11 flex items-center justify-center rounded-lg transition-colors ${
              isActive('/system')
                ? 'bg-blue-100 text-blue-600'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
            }`}
            title="System"
          >
            {isActive('/system') ? (
              <ComputerDesktopIconSolid className="w-5 h-5" />
            ) : (
              <ComputerDesktopIcon className="w-5 h-5" />
            )}
          </Link>
        </div>

        {/* User at bottom */}
        <div className="py-2 flex flex-col items-center border-t border-gray-200">
          <button
            onClick={isAuthenticated ? onLogoutClick : onLoginClick}
            className={`w-11 h-11 flex items-center justify-center rounded-lg transition-colors ${
              isAuthenticated
                ? 'text-green-600 hover:bg-green-50'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
            }`}
            title={isAuthenticated ? 'Logout (Authenticated)' : 'Login'}
          >
            <UserCircleIcon className="w-5 h-5" />
          </button>
        </div>
      </aside>

      {/* Config Panel - slides out for config submenu only */}
      {configOpen && (
        <>
          {/* Backdrop */}
          <div
            className="hidden lg:block fixed inset-0 z-30"
            onClick={() => setConfigOpen(false)}
          />

          {/* Panel */}
          <div className="hidden lg:block fixed left-14 top-0 bottom-0 w-56 bg-white border-r border-gray-200 shadow-lg z-35">
            {/* Panel Header */}
            <div className="h-14 flex items-center justify-between px-4 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">Configuration</h2>
              <button
                onClick={() => setConfigOpen(false)}
                className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100"
              >
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>

            {/* Config Links */}
            <nav className="p-2 space-y-1">
              {CONFIG_NAV.map((item) => (
                <Link
                  key={item.id}
                  href={item.href}
                  onClick={() => setConfigOpen(false)}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium ${
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
          </div>
        </>
      )}
    </>
  );
}

export default SideNav;
