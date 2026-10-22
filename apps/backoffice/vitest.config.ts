import path from 'node:path';
import { defineConfig } from 'vitest/config';

// Tests colocalises : src/**/__tests__/*.unit.test.ts. Seuil de couverture 80 % bloquant.
export default defineConfig({
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  test: {
    environment: 'node',
    setupFiles: ['src/test-setup.ts'],
    include: ['src/**/__tests__/**/*.{unit,integ}.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: [
        'src/lib/**/*.ts',
        'src/proxy.ts',
        'src/app/robots.ts',
        'src/app/page.tsx',
        'src/app/login/**/*.tsx',
        'src/app/session/**/route.ts',
        'src/app/bff/**/route.ts',
        'src/app/produits/**/page.tsx',
        'src/app/commandes/**/page.tsx',
        'src/components/**/*.tsx',
      ],
      exclude: ['src/**/__tests__/**'],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});
