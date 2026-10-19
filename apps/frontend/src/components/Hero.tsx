'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';

export function Hero() {
  return (
    <section className="relative overflow-hidden bg-forest-deep">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(224,86,56,0.18),_transparent_60%)]" />
      <div className="relative mx-auto flex max-w-6xl flex-col items-start gap-6 px-4 py-20 sm:py-28">
        <motion.span
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="rounded-full bg-bivouac/15 px-4 py-1.5 text-sm font-semibold text-bivouac-light"
        >
          Équipement bivouac & grande randonnée
        </motion.span>

        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-2xl text-4xl font-bold leading-tight text-sand sm:text-5xl"
        >
          Partez léger. Campez où bon vous semble.
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-xl text-lg text-sand/70"
        >
          Tentes ultralight, duvets techniques, réchauds titane : du matériel conçu pour l&apos;autonomie en
          pleine nature, testé en conditions réelles de bivouac.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
        >
          <Link
            href="/categories/tentes"
            className="group inline-flex items-center gap-2 rounded-full bg-bivouac px-6 py-3.5 text-base font-semibold text-white transition-transform duration-150 hover:bg-bivouac-dark active:scale-[0.98]"
          >
            Découvrir la collection
            <ArrowRight size={18} className="transition-transform duration-150 group-hover:translate-x-1" />
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
