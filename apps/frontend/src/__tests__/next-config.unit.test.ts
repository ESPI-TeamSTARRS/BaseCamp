import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';

const CONFIG_PATH = path.resolve(__dirname, '../../next.config.mjs');

async function loadConfig() {
  // Chemin dynamique : le fichier .mjs n'est pas résolu par TypeScript (allowJs désactivé).
  const configModule = await import(/* @vite-ignore */ pathToFileURL(CONFIG_PATH).href);
  return configModule.default as {
    images: { remotePatterns?: { protocol?: string; hostname: string }[] };
  };
}

describe('next.config images', () => {
  it("n'autorise aucun domaine générique dans remotePatterns", async () => {
    // Étant donné la configuration Next.js, quand on lit remotePatterns,
    // alors aucun hostname ne contient de joker (**, *).
    const { images } = await loadConfig();
    const hostnames = (images.remotePatterns ?? []).map((pattern) => pattern.hostname);
    expect(hostnames.filter((hostname) => hostname.includes('*'))).toEqual([]);
  });

  it('limite remotePatterns aux domaines de la passerelle (hôte du site)', async () => {
    // Étant donné NEXT_PUBLIC_SITE_URL absent des tests, alors aucun domaine distant n'est autorisé.
    const { images } = await loadConfig();
    expect(images.remotePatterns ?? []).toEqual([]);
  });
});
