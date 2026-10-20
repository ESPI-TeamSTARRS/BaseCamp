import { z } from 'zod';

const envSchema = z.object({
  NEXT_PUBLIC_SITE_URL: z.string().url(),
  // URL interne de l'API shop : lue cote serveur uniquement (jamais prefixee NEXT_PUBLIC_).
  SHOP_API_URL: z.string().url(),
  STRIPE_SECRET_KEY: z.string().min(1, 'STRIPE_SECRET_KEY manquante'),
  NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY: z.string().min(1, 'NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY manquante'),
  STRIPE_WEBHOOK_SECRET: z.string().min(1, 'STRIPE_WEBHOOK_SECRET manquante'),
  RESEND_API_KEY: z.string().min(1, 'RESEND_API_KEY manquante'),
  RESEND_FROM_EMAIL: z.string().email(),
});

function loadEnv() {
  const parsed = envSchema.safeParse(process.env);
  if (!parsed.success) {
    // Erreur de configuration : on ne fait jamais confiance à des variables manquantes en prod.
    throw new Error(
      `Configuration d'environnement invalide :\n${JSON.stringify(parsed.error.flatten().fieldErrors, null, 2)}`
    );
  }
  return parsed.data;
}

// N'exécute la validation stricte qu'au runtime serveur (jamais pendant le build statique sans secrets).
export const env = process.env.SKIP_ENV_VALIDATION
  ? (process.env as unknown as z.infer<typeof envSchema>)
  : loadEnv();
