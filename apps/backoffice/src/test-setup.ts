import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Les tests de composants choisissent jsdom avec `// @vitest-environment jsdom` ; le demontage est automatique.
afterEach(() => cleanup());
