'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { startCamera, stopCamera, type CameraFailure } from '@/lib/camera';
import { captureFrames } from '@/lib/capture';
import { identify, submitFace, submitPassword } from '@/lib/login-api';
import {
  EMPTY_LOCKOUT,
  parseLockout,
  recordFailure,
  recordSuccess,
  remainingMs,
  type FailureKind,
  type LockoutState,
} from '@/lib/lockout';

type Step = 'identifier' | 'face' | 'password';

const LOCK_STORAGE_KEY = 'basecamp-bo-login-lock';
const FRAME_COUNT = 3;

const GENERIC_REFUSAL = 'Vérification impossible. Recommencez.';
const CAMERA_MESSAGES: Record<CameraFailure, string> = {
  denied: 'L’accès à la caméra n’est pas autorisé. Autorisez-la dans votre navigateur puis recommencez.',
  absent: 'Aucune caméra détectée. Branchez-en une puis recommencez.',
  unsupported: 'Ce navigateur ne permet pas l’accès à la caméra (connexion sécurisée requise).',
  unavailable: 'La caméra est inutilisable pour le moment. Fermez les autres applications qui l’utilisent.',
};

function readLock(): LockoutState {
  try {
    return parseLockout(window.localStorage.getItem(LOCK_STORAGE_KEY));
  } catch {
    return EMPTY_LOCKOUT;
  }
}

function writeLock(state: LockoutState): void {
  try {
    window.localStorage.setItem(LOCK_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Stockage indisponible : le blocage reste actif pour la session de l'onglet.
  }
}

function formatCountdown(ms: number): string {
  const seconds = Math.ceil(ms / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function goHome(): void {
  window.location.assign(new URL('/', window.location.origin).href);
}

export function LoginForm({ onSuccess = goHome }: { onSuccess?: () => void }) {
  const [step, setStep] = useState<Step>('identifier');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [lock, setLock] = useState<LockoutState>(EMPTY_LOCKOUT);
  const [now, setNow] = useState(() => Date.now());

  const streamRef = useRef<MediaStream | null>(null);
  const challengeRef = useRef<string | null>(null);
  const expiryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mountedRef = useRef(true);

  const remaining = remainingMs(lock, now);
  const locked = remaining > 0;

  const releaseCamera = useCallback(() => {
    stopCamera(streamRef.current);
    streamRef.current = null;
    setStream(null);
  }, []);

  const clearExpiry = useCallback(() => {
    if (expiryRef.current) clearTimeout(expiryRef.current);
    expiryRef.current = null;
  }, []);

  // Retour a l'etape 1 : identifiant vide, camera arretee, defi oublie.
  const restart = useCallback(
    (text: string | null) => {
      clearExpiry();
      releaseCamera();
      challengeRef.current = null;
      setEmail('');
      setPassword('');
      setStep('identifier');
      setMessage(text);
    },
    [clearExpiry, releaseCamera]
  );

  const fail = useCallback(
    (kind: FailureKind) => {
      const next = recordFailure(readLock(), kind, Date.now());
      writeLock(next);
      setLock(next);
      setNow(Date.now());
      restart(GENERIC_REFUSAL);
    },
    [restart]
  );

  useEffect(() => {
    mountedRef.current = true;
    // Le blocage vit dans le stockage du navigateur : lu apres l'hydratation, hors du corps de l'effet.
    const loader = setTimeout(() => {
      setLock(readLock());
      setNow(Date.now());
    }, 0);
    return () => {
      clearTimeout(loader);
      mountedRef.current = false;
      if (expiryRef.current) clearTimeout(expiryRef.current);
      stopCamera(streamRef.current);
    };
  }, []);

  useEffect(() => {
    if (!locked) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [locked]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = stream;
  }, [stream, step]);

  async function handleIdentify(event: FormEvent) {
    event.preventDefault();
    if (locked || busy) return;
    if (!email.trim()) {
      setMessage('Saisissez votre identifiant.');
      return;
    }
    setBusy(true);
    setMessage(null);
    const identified = await identify(email.trim());
    if (identified.kind === 'error') {
      setBusy(false);
      setMessage('Service momentanément indisponible. Réessayez.');
      return;
    }
    const camera = await startCamera();
    setBusy(false);
    if (camera.kind === 'error') {
      setMessage(CAMERA_MESSAGES[camera.reason]);
      return;
    }
    if (!mountedRef.current) {
      stopCamera(camera.stream);
      return;
    }
    challengeRef.current = identified.challengeId;
    streamRef.current = camera.stream;
    setStream(camera.stream);
    setStep('face');
    expiryRef.current = setTimeout(
      () => restart('Le délai est dépassé. Recommencez.'),
      identified.expiresIn * 1000
    );
  }

  async function handleFace() {
    if (locked || busy || !challengeRef.current || !videoRef.current) return;
    setBusy(true);
    setMessage(null);
    let frames: string[];
    try {
      frames = await captureFrames(videoRef.current, FRAME_COUNT);
    } catch {
      setBusy(false);
      setMessage('La capture a échoué. Réessayez.');
      return;
    }
    const result = await submitFace(challengeRef.current, frames);
    setBusy(false);
    if (!mountedRef.current) return;
    if (result === 'accepted') {
      releaseCamera();
      setStep('password');
    } else if (result === 'refused') {
      fail('face');
    } else if (result === 'invalid_image') {
      setMessage('Image illisible. Placez votre visage face à la caméra et réessayez.');
    } else {
      setMessage('Service momentanément indisponible. Réessayez.');
    }
  }

  async function handlePassword(event: FormEvent) {
    event.preventDefault();
    if (locked || busy || !challengeRef.current) return;
    setBusy(true);
    setMessage(null);
    const result = await submitPassword(challengeRef.current, password);
    setBusy(false);
    if (!mountedRef.current) return;
    if (result === 'success') {
      clearExpiry();
      writeLock(recordSuccess(readLock()));
      onSuccess();
    } else if (result === 'refused') {
      fail('password');
    } else {
      setMessage('Service momentanément indisponible. Réessayez.');
    }
  }

  return (
    <main style={{ padding: '4rem 1.5rem', maxWidth: '26rem', margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>Back-office Basecamp</h1>
      <p style={{ marginTop: 0 }}>Connexion réservée à l’équipe.</p>

      {locked && (
        <p role="status">
          Trop d’échecs. Nouvelle tentative possible dans{' '}
          <strong data-testid="lock-countdown">{formatCountdown(remaining)}</strong>.
        </p>
      )}
      {message && (
        <p role="alert" style={{ color: '#E05638' }}>
          {message}
        </p>
      )}

      {step === 'identifier' && (
        <form onSubmit={handleIdentify} noValidate style={formStyle}>
          <label htmlFor="identifier">Identifiant</label>
          <input
            id="identifier"
            type="email"
            autoComplete="username"
            value={email}
            disabled={locked || busy}
            onChange={(event) => setEmail(event.target.value)}
            style={fieldStyle}
          />
          <button type="submit" disabled={locked || busy} style={buttonStyle}>
            Continuer
          </button>
        </form>
      )}

      {step === 'face' && (
        <div style={formStyle}>
          <video
            ref={videoRef}
            data-testid="camera-preview"
            autoPlay
            playsInline
            muted
            style={{ width: '100%', borderRadius: '0.5rem', background: '#1E3A2F', transform: 'scaleX(-1)' }}
          />
          <p style={{ margin: 0 }}>Placez votre visage face à la caméra.</p>
          <button type="button" onClick={handleFace} disabled={locked || busy} style={buttonStyle}>
            Vérifier mon visage
          </button>
        </div>
      )}

      {step === 'password' && (
        <form onSubmit={handlePassword} style={formStyle}>
          <label htmlFor="password">Mot de passe</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            disabled={locked || busy}
            onChange={(event) => setPassword(event.target.value)}
            style={fieldStyle}
          />
          <button type="submit" disabled={locked || busy} style={buttonStyle}>
            Se connecter
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
