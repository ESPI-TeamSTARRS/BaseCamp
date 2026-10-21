'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { createSessionKeeper } from '../lib/session-keeper';

const LOGIN_PATH = '/compte/connexion';

/** Sans rendu : retrouve la session au chargement et la rafraichit avant l'expiration. */
export function SessionKeeper() {
  const router = useRouter();

  useEffect(() => {
    const keeper = createSessionKeeper({ onExpired: () => router.replace(LOGIN_PATH) });
    void keeper.start();
    return keeper.stop;
  }, [router]);

  return null;
}
