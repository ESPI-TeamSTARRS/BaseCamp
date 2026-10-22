import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';

const CONFIG_PATH = path.resolve(__dirname, '../../next.config.mjs');

type Config = {
  output: string;
  poweredByHeader: boolean;
  headers: () => Promise<{ source: string; headers: { key: string; value: string }[] }[]>;
};

async function loadConfig(): Promise<Config> {
  const configModule = await import(/* @vite-ignore */ pathToFileURL(CONFIG_PATH).href);
  return configModule.default as Config;
}

async function headerMap(): Promise<Record<string, string>> {
  const [rule] = await (await loadConfig()).headers();
  return Object.fromEntries(rule.headers.map((h) => [h.key, h.value]));
}

describe('next.config du back-office', () => {
  it('produit un serveur autonome sans en-tête X-Powered-By', async () => {
    const config = await loadConfig();
    expect(config.output).toBe('standalone');
    expect(config.poweredByHeader).toBe(false);
  });

  it('interdit l’indexation, les cadres et le sniffing', async () => {
    const headers = await headerMap();
    expect(headers['X-Robots-Tag']).toContain('noindex');
    expect(headers['X-Frame-Options']).toBe('DENY');
    expect(headers['X-Content-Type-Options']).toBe('nosniff');
    expect(headers['Content-Security-Policy']).toContain("frame-ancestors 'none'");
    expect(headers['Content-Security-Policy']).toContain("frame-src 'none'");
  });

  it('autorise la caméra seulement pour cette origine', async () => {
    const headers = await headerMap();
    expect(headers['Permissions-Policy']).toContain('camera=(self)');
    expect(headers['Permissions-Policy']).toContain('microphone=()');
  });
});
