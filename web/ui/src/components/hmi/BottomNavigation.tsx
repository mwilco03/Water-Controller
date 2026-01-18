'use client';

/**
 * BottomNavigation - Mobile bottom nav with heroicons
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Squares2X2Icon,
  ServerStackIcon,
  BellAlertIcon,
  AdjustmentsHorizontalIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';
import {
  Squares2X2Icon as Squares2X2IconSolid,
  ServerStackIcon as ServerStackIconSolid,
  BellAlertIcon as BellAlertIconSolid,
  AdjustmentsHorizontalIcon as AdjustmentsHorizontalIconSolid,
  ChartBarIcon as ChartBarIconSolid,
} from '@heroicons/react/24/solid';

interface BottomNavigationProps {
  activeAlarmCount?: number;
}

export function BottomNavigation({ activeAlarmCount = 0 }: BottomNavigationProps) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  const navItems = [
    {
      href: '/',
      label: 'Status',
      Icon: Squares2X2Icon,
      IconActive: Squares2X2IconSolid,
    },
    {
      href: '/rtus',
      label: 'RTUs',
      Icon: ServerStackIcon,
      IconActive: ServerStackIconSolid,
    },
    {
      href: '/alarms',
      label: 'Alarms',
      Icon: BellAlertIcon,
      IconActive: BellAlertIconSolid,
      badge: activeAlarmCount > 0 ? activeAlarmCount : undefined,
    },
    {
      href: '/control',
      label: 'Control',
      Icon: AdjustmentsHorizontalIcon,
      IconActive: AdjustmentsHorizontalIconSolid,
    },
    {
      href: '/system',
      label: 'System',
      Icon: ChartBarIcon,
      IconActive: ChartBarIconSolid,
    },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-200 lg:hidden safe-area-pb">
      <div className="flex justify-around items-stretch h-14">
        {navItems.map((item) => {
          const active = isActive(item.href);
          const IconComponent = active ? item.IconActive : item.Icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center flex-1 min-w-0 py-1 ${
                active ? 'text-blue-600' : 'text-gray-500'
              }`}
            >
              <span className="relative">
                <IconComponent className="w-6 h-6" />
                {item.badge !== undefined && (
                  <span className="absolute -top-1 -right-2 min-w-[18px] h-[18px] px-1 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                    {item.badge > 99 ? '99+' : item.badge}
                  </span>
                )}
              </span>
              <span className="text-[10px] font-medium mt-0.5">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export default BottomNavigation;
