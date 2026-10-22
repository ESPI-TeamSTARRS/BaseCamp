'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { startCamera, stopCamera, type CameraFailure } from '@/lib/camera';
import { captureFrame } from '@/lib/capture';
import { completeInvitation, type CompleteResult } from '@/lib/invitation-api';
import { takeInvitationToken } from '@/lib/invitation-token';

export const MIN_PHOTOS = 3;
export const MAX_PHOTOS = 10;
export const MIN_PASSWORD_LENGTH = 12;

type Status = 'loading' | 'ready' | 'invalid' | 'done';

const INVALID_LINK =
  'Ce lien est invalide, expiré ou déjà utilisé. Demandez un nouveau lien à l’administrateur IT.';
const CAMERA_MESSAGES: Record<CameraFailure, string> = {
  denied: 'L’accès à la caméra n’est pas autorisé. Autorisez-la dans votre navigateur puis recommencez.',
  absent: 'Aucune caméra détectée. Branchez-en une puis recommencez.',
  unsupported: 'Ce navigateur ne permet pas l’accès à la caméra (connexion sécurisée requise).',
  unavailable: 'La caméra est inutilisable pour le moment. Fermez les autres applications qui l’utilisent.',
};
const FAILURE_MESSAGES: Record<Exclude<CompleteResult, 'created' | 'invalid_link'>, string> = {
  weak_password: 'Ce mot de passe n’est pas accepté. Choisissez-en un plus long et moins courant.',
  photo_count: `Il faut entre ${MIN_PHOTOS} et ${MAX_PHOTOS} photos. Reprenez-les.`,
  invalid_photo: 'Une photo est illisible. Reprenez vos photos.',
  no_face: 'Votre visage n’a pas été reconnu sur les photos. Reprenez-les, de face et bien éclairé.',
  error: 'Service momentanément indisponible. Réessayez.',
};

export function InvitationForm({
  readToken = () => takeInvitationToken(window.location, window.history),
}: {
  readToken?: () => string | null;
}) {
  const [status, setStatus] = useState<Status>('loading');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [photos, setPhotos] = useState<string[]>([]);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const tokenRef = useRef<string | null>(null);
  // Le jeton se lit UNE fois : la lecture efface le fragment de l'adresse, une seconde lecture ne trouverait plus rien.
  const readerRef = useRef(readToken);
  const readRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mountedRef = useRef(true);

  const releaseCamera = useCallback(() => {
    stopCamera(streamRef.current);
    streamRef.current = null;
    setStream(null);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    // Le jeton est lu apres l'hydratation (le fragment n'existe que dans le navigateur) puis retire de l'adresse.
    const reader = setTimeout(() => {
      if (!readRef.current) {
        readRef.current = true;
        tokenRef.current = readerRef.current();
      }
      setStatus(tokenRef.current ? 'ready' : 'invalid');
    }, 0);
    return () => {
      clearTimeout(reader);
      mountedRef.current = false;
      stopCamera(streamRef.current);
    };
  }, []);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = stream;
  }, [stream, status]);

  async function handleCamera() {
    if (busy || streamRef.current) return;
    setMessage(null);
    const camera = await startCamera();
    if (camera.kind === 'error') {
      setMessage(CAMERA_MESSAGES[camera.reason]);
      return;
    }
    if (!mountedRef.current) {
      stopCamera(camera.stream);
      return;
    }
    streamRef.current = camera.stream;
    setStream(camera.stream);
  }

  function handleShoot() {
    if (busy || !videoRef.current || photos.length >= MAX_PHOTOS) return;
    try {
      const image = captureFrame(videoRef.current);
      setPhotos((current) => [...current, image]);
      setMessage(null);
    } catch {
      setMessage('La capture a échoué. Réessayez.');
    }
  }

  function removePhoto(index: number) {
    setPhotos((current) => current.filter((_, position) => position !== index));
  }

  const passwordOk = password.length >= MIN_PASSWORD_LENGTH && password === confirmation;
  const photosOk = photos.length >= MIN_PHOTOS && photos.length <= MAX_PHOTOS;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy || !tokenRef.current) return;
    if (!passwordOk) {
      setMessage(
        password.length < MIN_PASSWORD_LENGTH
          ? `Le mot de passe doit contenir au moins ${MIN_PASSWORD_LENGTH} caractères.`
          : 'Les deux mots de passe sont différents.'
      );
      return;
    }
    if (!photosOk) {
      setMessage(`Prenez entre ${MIN_PHOTOS} et ${MAX_PHOTOS} photos.`);
      return;
    }
    setBusy(true);
    setMessage(null);
    const sent = photos;
    const result = await completeInvitation(tokenRef.current, password, sent);
    // Rien ne reste dans le navigateur apres l'envoi, quel que soit le resultat.
    releaseCamera();
    setPhotos([]);
    setPassword('');
    setConfirmation('');
    setBusy(false);
    if (!mountedRef.current) return;
    if (result === 'created') {
      tokenRef.current = null;
      setStatus('done');
    } else if (result === 'invalid_link') {
      tokenRef.current = null;
      setStatus('invalid');
    } else {
      setMessage(FAILURE_MESSAGES[result]);
    }
  }

  return (
    <main style={{ padding: '4rem 1.5rem', maxWidth: '28rem', margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>Back-office Basecamp</h1>
      <p style={{ marginTop: 0 }}>Création de votre compte opérateur.</p>

      {status === 'loading' && <p role="status">Chargement…</p>}

      {status === 'invalid' && (
        <p role="alert" style={{ color: '#E05638' }}>
          {INVALID_LINK}
        </p>
      )}

      {status === 'done' && (
        <p role="status">
          Votre compte est créé. Vous pouvez <a href="/login">vous connecter</a>.
        </p>
      )}

      {status === 'ready' && (
        <form onSubmit={handleSubmit} noValidate style={formStyle}>
          {message && (
            <p role="alert" style={{ color: '#E05638', margin: 0 }}>
              {message}
            </p>
          )}

          <label htmlFor="new-password">Mot de passe ({MIN_PASSWORD_LENGTH} caractères minimum)</label>
          <input
            id="new-password"
            type="password"
            autoComplete="new-password"
            value={password}
            disabled={busy}
            onChange={(event) => setPassword(event.target.value)}
            style={fieldStyle}
          />
          <label htmlFor="confirm-password">Confirmez le mot de passe</label>
          <input
            id="confirm-password"
            type="password"
            autoComplete="new-password"
            value={confirmation}
            disabled={busy}
            onChange={(event) => setConfirmation(event.target.value)}
            style={fieldStyle}
          />

          <p style={{ margin: '0.5rem 0 0' }}>
            Photos de votre visage : {MIN_PHOTOS} à {MAX_PHOTOS}, de face, avec de légères variations (léger
            tour de tête, expression).
          </p>
          {!stream && (
            <button type="button" onClick={handleCamera} disabled={busy} style={buttonStyle}>
              Activer la caméra
            </button>
          )}
          {stream && (
            <>
              <video
                ref={videoRef}
                data-testid="camera-preview"
                autoPlay
                playsInline
                muted
                style={{
                  width: '100%',
                  borderRadius: '0.5rem',
                  background: '#1E3A2F',
                  transform: 'scaleX(-1)',
                }}
              />
              <button
                type="button"
                onClick={handleShoot}
                disabled={busy || photos.length >= MAX_PHOTOS}
                style={buttonStyle}
              >
                Prendre une photo
              </button>
            </>
          )}

          <p role="status" style={{ margin: 0 }}>
            {photos.length} photo{photos.length > 1 ? 's' : ''} sur {MAX_PHOTOS} (minimum {MIN_PHOTOS}).
          </p>
          <ul
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '0.5rem',
              listStyle: 'none',
              padding: 0,
              margin: 0,
            }}
          >
            {photos.map((photo, index) => (
              <li
                key={`${index}-${photo.length}`}
                style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- apercu local en data URL, pas d'optimisation possible */}
                <img
                  src={`data:image/jpeg;base64,${photo}`}
                  alt={`Photo ${index + 1}`}
                  width={72}
                  height={54}
                  style={{ objectFit: 'cover', borderRadius: '0.3rem', transform: 'scaleX(-1)' }}
                />
                <button type="button" onClick={() => removePhoto(index)} disabled={busy}>
                  Retirer
                </button>
              </li>
            ))}
          </ul>

          <button type="submit" disabled={busy || !photosOk || !passwordOk} style={buttonStyle}>
            Créer mon compte
          </button>
        </form>
      )}
    </main>
  );
}

const formStyle = { display: 'flex', flexDirection: 'column', gap: '0.75rem' } as const;
const fieldStyle = {
  padding: '0.6rem',
  border: '1px solid #1E3A2F',
  borderRadius: '0.4rem',
  fontSize: '1rem',
} as const;
const buttonStyle = {
  padding: '0.7rem',
  background: '#1E3A2F',
  color: '#F5F2EB',
  border: 'none',
  borderRadius: '0.4rem',
  fontSize: '1rem',
  cursor: 'pointer',
} as const;
