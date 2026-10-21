import path from 'node:path';
import { defineConfig } from 'vitest/config';

// Tests colocalises : src/**/__tests__/*.unit.test.ts. Seuil de couverture 80 % bloquant.
export default defineConfig({
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  test: {
    environment: 'node',
    include: ['src/**/__tests__/**/*.{unit,integ}.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/lib/**/*.ts', 'src/proxy.ts', 'src/app/robots.ts', 'src/app/page.tsx'],
      exclude: ['src/**/__tests__/**'],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});
