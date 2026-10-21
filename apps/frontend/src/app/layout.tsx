import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { Inter } from 'next/font/google';
import './globals.css';
import { CartProvider } from '../context/CartContext';
import { Header } from '../components/Header';
import { Footer } from '../components/Footer';
import { CartDrawer } from '../components/CartDrawer';
import { SessionKeeper } from '../components/SessionKeeper';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://basecamp-outdoor.fr';

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: 'Basecamp Outdoor — Équipement Bivouac & Grande Randonnée',
    template: '%s | Basecamp Outdoor',
  },
  description:
    "Tentes ultralight, duvets techniques et sacs à dos de trek pour l'autonomie en pleine nature. Expédition 24/48h, retours gratuits sous 30 jours.",
  alternates: { canonical: '/' },
  openGraph: {
    title: 'Basecamp Outdoor — Équipement Bivouac & Grande Randonnée',
    description:
      "Tentes ultralight, duvets techniques et sacs à dos de trek pour l'autonomie en pleine nature. Expédition 24/48h, retours gratuits sous 30 jours.",
    url: siteUrl,
    siteName: 'Basecamp Outdoor',
    locale: 'fr_FR',
    type: 'website',
    images: [{ url: '/images/og-image.jpg', width: 1200, height: 630, alt: 'Basecamp Outdoor' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Basecamp Outdoor',
    description:
      "Tentes ultralight, duvets techniques et sacs à dos de trek pour l'autonomie en pleine nature. Expédition 24/48h, retours gratuits sous 30 jours.",
    images: ['/images/og-image.jpg'],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr" className={inter.variable}>
      <body className="flex min-h-screen flex-col font-sans text-granite">
        <CartProvider>
          <SessionKeeper />
          <Header />
          <main className="flex-1">{children}</main>
          <Footer />
          <CartDrawer />
        </CartProvider>
      </body>
    </html>
  );
}
