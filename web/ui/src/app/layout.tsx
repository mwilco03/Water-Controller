import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Water Treatment Controller - HMI',
  description: 'SCADA HMI for Water Treatment RTU Network',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="bg-scada-panel border-b border-scada-accent px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <h1 className="text-xl font-bold text-white">
                  Water Treatment Controller
                </h1>
                <span className="text-sm text-gray-400">v1.0.0</span>
              </div>
              <nav className="flex gap-6">
                <a href="/" className="text-gray-300 hover:text-white transition-colors">
                  Overview
                </a>
                <a href="/rtus" className="text-gray-300 hover:text-white transition-colors">
                  RTUs
                </a>
                <a href="/alarms" className="text-gray-300 hover:text-white transition-colors">
                  Alarms
                </a>
                <a href="/trends" className="text-gray-300 hover:text-white transition-colors">
                  Trends
                </a>
                <a href="/control" className="text-gray-300 hover:text-white transition-colors">
                  Control
                </a>
              </nav>
            </div>
          </header>
          <main className="p-6">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
