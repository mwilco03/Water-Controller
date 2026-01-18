'use client';

/**
 * BottomNavigation - Mobile-first thumb-reachable navigation
 *
 * Design principles:
 * - Fixed at bottom for easy thumb access
 * - 48px+ touch targets for gloved operation
 * - Icon + text for clarity (never icon alone)
 * - Badge for alarm count visibility
 * - Hides on desktop (lg+) where top nav is shown
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

interface BottomNavigationProps {
  activeAlarmCount?: number;
}

export function BottomNavigation({ activeAlarmCount = 0 }: BottomNavigationProps) {
  const pathname = usePathname();

  const navItems: NavItem[] = [
    {
      href: '/',
      label: 'Status',
      icon: (
        <span className="nav-icon text-base font-bold" aria-hidden="true">[=]</span>
      ),
    },
    {
      href: '/rtus',
      label: 'RTUs',
      icon: (
        <span className="nav-icon text-base font-bold" aria-hidden="true">[#]</span>
      ),
    },
    {
      href: '/alarms',
      label: 'Alarms',
      icon: (
        <span className="nav-icon text-base font-bold" aria-hidden="true">[!]</span>
      ),
      badge: activeAlarmCount > 0 ? activeAlarmCount : undefined,
    },
    {
      href: '/control',
      label: 'Control',
      icon: (
        <span className="nav-icon text-base font-bold" aria-hidden="true">[~]</span>
      ),
    },
    {
      href: '/system',
      label: 'System',
      icon: (
        <span className="nav-icon text-base font-bold" aria-hidden="true">[|]</span>
      ),
    },
  ];

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  return (
    <nav
      className="bottom-nav lg:hidden"
      role="navigation"
      aria-label="Primary navigation"
    >
      {navItems.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={`bottom-nav-item ${isActive(item.href) ? 'active' : ''}`}
          aria-current={isActive(item.href) ? 'page' : undefined}
        >
          <span className="relative">
            {item.icon}
            {item.badge !== undefined && (
              <span
                className="bottom-nav-badge"
                aria-label={`${item.badge} active alarms`}
              >
                {item.badge > 99 ? '99+' : item.badge}
              </span>
            )}
          </span>
          <span className="nav-label">{item.label}</span>
        </Link>
      ))}
    </nav>
  );
}

export default BottomNavigation;
