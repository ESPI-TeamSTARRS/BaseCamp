import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';

const eslintConfig = [...nextCoreWebVitals, { ignores: ['.next/**', 'coverage/**', 'next-env.d.ts'] }];

export default eslintConfig;
