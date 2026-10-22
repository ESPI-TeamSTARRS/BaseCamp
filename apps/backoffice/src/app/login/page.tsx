const MESSAGES: Record<string, string> = {
  '2': 'Service momentanément indisponible. Réessayez dans un instant.',
};

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ erreur?: string }> }) {
  const { erreur } = await searchParams;
  const message = erreur ? MESSAGES[erreur] : undefined;
  return (
    <main style={{ padding: '4rem 1.5rem', maxWidth: '32rem', margin: '0 auto' }}>
      <h1>Connexion</h1>
      <p>
        Espace réservé à l’équipe. La connexion se fait en trois temps : identification, visage, mot de passe.
      </p>
      {message && (
        <p role="alert" style={{ color: '#9b1c1c' }}>
          {message}
        </p>
      )}
      <p>L’écran de connexion arrive avec la reconnaissance faciale.</p>
    </main>
  );
}
