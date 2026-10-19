import type { Config } from 'tailwindcss';

// Design tokens — Basecamp Outdoor DA (voir .claude/skills/design-system-tokens)
const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        forest: {
          DEFAULT: '#1E3A2F',
          deep: '#132E22',
          light: '#2A5240',
        },
        bivouac: {
          DEFAULT: '#E05638',
          dark: '#C84B31',
          light: '#F07B5F',
        },
        granite: {
          DEFAULT: '#181D1A',
          light: '#222925',
        },
        sand: {
          DEFAULT: '#F5F2EB',
          dark: '#E8E2D5',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
      },
      spacing: {
        '1': '4px',
        '2': '8px',
        '3': '12px',
        '4': '16px',
        '5': '20px',
        '6': '24px',
        '8': '32px',
        '12': '48px',
        '16': '64px',
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1.3' }],
        sm: ['0.875rem', { lineHeight: '1.4' }],
        base: ['1rem', { lineHeight: '1.6' }],
        lg: ['1.125rem', { lineHeight: '1.5' }],
        xl: ['1.25rem', { lineHeight: '1.4' }],
        '2xl': ['1.5rem', { lineHeight: '1.3' }],
        '3xl': ['1.875rem', { lineHeight: '1.2' }],
        '4xl': ['2.5rem', { lineHeight: '1.1' }],
      },
      boxShadow: {
        card: '0 4px 12px rgba(0,0,0,0.12), 0 0 1px rgba(255,255,255,0.05) inset',
        'card-hover': '0 12px 32px rgba(0,0,0,0.18), 0 0 1px rgba(255,255,255,0.08) inset',
      },
      borderRadius: {
        card: '12px',
      },
      transitionTimingFunction: {
        'out-natural': 'cubic-bezier(0.16, 1, 0.3, 1)',
        'in-natural': 'cubic-bezier(0.4, 0, 1, 1)',
      },
    },
  },
  plugins: [],
};

export default config;
