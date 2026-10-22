import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: 'Basecamp · Back-office',
  robots: { index: false, follow: false, noarchive: true },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body
        style={{ margin: 0, fontFamily: 'system-ui, sans-serif', background: '#F5F2EB', color: '#1E3A2F' }}
      >
        {children}
      </body>
    </html>
  );
}
