import path from 'node:path';
import { defineConfig } from 'vitest/config';

// Tests colocalises : src/**/__tests__/*.unit.test.ts et *.integ.test.ts (E2E : tests/e2e/).
// Le perimetre de couverture s'elargit au fil des fonctionnalites (TDD) ; seuil 80 % bloquant.
export default defineConfig({
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  test: {
    environment: 'node',
    include: ['src/**/__tests__/**/*.{unit,integ}.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: [
        'src/lib/rate-limit.ts',
        'src/lib/validations.ts',
        'src/lib/seo.ts',
        'src/lib/shop-api.ts',
        'src/lib/cart-lines.ts',
        'src/lib/categories.ts',
        'src/lib/cart-quote.ts',
        'src/lib/order-form.ts',
        'src/lib/place-order.ts',
      ],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});
