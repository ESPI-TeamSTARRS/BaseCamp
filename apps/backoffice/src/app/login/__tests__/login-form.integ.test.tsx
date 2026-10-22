// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LOCK_DURATION_MS } from '@/lib/lockout';
import { LoginForm } from '../login-form';

vi.mock('@/lib/login-api', () => ({
  identify: vi.fn(),
  submitFace: vi.fn(),
  submitPassword: vi.fn(),
}));
vi.mock('@/lib/capture', () => ({ captureFrames: vi.fn() }));

import { captureFrames } from '@/lib/capture';
import { identify, submitFace, submitPassword } from '@/lib/login-api';

const identifyMock = vi.mocked(identify);
const faceMock = vi.mocked(submitFace);
const passwordMock = vi.mocked(submitPassword);
const captureMock = vi.mocked(captureFrames);

let tracks: { stop: ReturnType<typeof vi.fn> }[];
let getUserMedia: ReturnType<typeof vi.fn>;

function newStream(): MediaStream {
  tracks = [{ stop: vi.fn() }];
  return { getTracks: () => tracks } as unknown as MediaStream;
}

beforeEach(() => {
  window.localStorage.clear();
  getUserMedia = vi.fn().mockImplementation(async () => newStream());
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });
  identifyMock.mockResolvedValue({ kind: 'ok', challengeId: 'chal-1', expiresIn: 120 });
  captureMock.mockResolvedValue(['img1', 'img2', 'img3']);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

const email = () => screen.getByLabelText('Identifiant') as HTMLInputElement;

async function validateIdentifier(value = 'ops@basecamp.test'): Promise<void> {
  fireEvent.change(email(), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuer' }));
  await screen.findByRole('button', { name: 'Vérifier mon visage' });
}

async function reachPassword(onSuccess = vi.fn()) {
  render(<LoginForm onSuccess={onSuccess} />);
  await validateIdentifier();
  faceMock.mockResolvedValue('accepted');
  fireEvent.click(screen.getByRole('button', { name: 'Vérifier mon visage' }));
  await screen.findByLabelText('Mot de passe');
  return onSuccess;
}

describe('étape 1 : identifiant', () => {
  it('affiche seulement le champ identifiant au départ', () => {
    render(<LoginForm />);
    expect(email()).toBeTruthy();
    expect(screen.queryByLabelText('Mot de passe')).toBeNull();
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('à la validation, active la caméra et affiche l’aperçu', async () => {
    render(<LoginForm />);
    await validateIdentifier();
    expect(identifyMock).toHaveBeenCalledWith('ops@basecamp.test');
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('camera-preview')).toBeTruthy();
    expect(screen.queryByLabelText('Mot de passe')).toBeNull();
  });

  it('refuse un identifiant vide sans appeler le serveur', () => {
    render(<LoginForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Continuer' }));
    expect(identifyMock).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toContain('identifiant');
  });

  it('affiche une erreur si le serveur est injoignable', async () => {
    identifyMock.mockResolvedValue({ kind: 'error' });
    render(<LoginForm />);
    fireEvent.change(email(), { target: { value: 'ops@basecamp.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continuer' }));
    await screen.findByRole('alert');
    expect(getUserMedia).not.toHaveBeenCalled();
  });
});

describe('étape 2 : visage', () => {
  it('capture jusqu’à 3 images, les envoie, puis affiche l’étape mot de passe', async () => {
    render(<LoginForm />);
    await validateIdentifier();
    faceMock.mockResolvedValue('accepted');
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier mon visage' }));
    await screen.findByLabelText('Mot de passe');
    expect(captureMock).toHaveBeenCalledWith(expect.anything(), 3);
    expect(faceMock).toHaveBeenCalledWith('chal-1', ['img1', 'img2', 'img3']);
    tracks.forEach((track) => expect(track.stop).toHaveBeenCalled());
  });

  it('visage refusé : identifiant vidé, caméra arrêtée, message générique', async () => {
    render(<LoginForm />);
    await validateIdentifier();
    const opened = tracks;
    faceMock.mockResolvedValue('refused');
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier mon visage' }));
    await screen.findByRole('alert');
    expect(email().value).toBe('');
    opened.forEach((track) => expect(track.stop).toHaveBeenCalled());
    expect(screen.getByRole('alert').textContent).toBe('Vérification impossible. Recommencez.');
    expect(screen.queryByLabelText('Mot de passe')).toBeNull();
  });

  it('image illisible : reste sur l’étape visage, caméra active', async () => {
    render(<LoginForm />);
    await validateIdentifier();
    faceMock.mockResolvedValue('invalid_image');
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier mon visage' }));
    await screen.findByRole('alert');
    expect(screen.getByTestId('camera-preview')).toBeTruthy();
    tracks.forEach((track) => expect(track.stop).not.toHaveBeenCalled());
  });

  it('échec de capture ou erreur réseau : reste sur l’étape visage', async () => {
    render(<LoginForm />);
    await validateIdentifier();
    captureMock.mockRejectedValueOnce(new Error('video_not_ready'));
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier mon visage' }));
    await screen.findByRole('alert');
    faceMock.mockResolvedValue('error');
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier mon visage' }));
    await waitFor(() => expect(faceMock).toHaveBeenCalled());
    expect(screen.getByTestId('camera-preview')).toBeTruthy();
  });
});

describe('étape 3 : mot de passe', () => {
  it('succès : appelle onSuccess', async () => {
    const onSuccess = await reachPassword();
    passwordMock.mockResolvedValue('success');
    fireEvent.change(screen.getByLabelText('Mot de passe'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Se connecter' }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(passwordMock).toHaveBeenCalledWith('chal-1', 'secret');
  });

  it('mot de passe faux : retour à l’étape 1, identifiant vide, message générique', async () => {
    await reachPassword();
    passwordMock.mockResolvedValue('refused');
    fireEvent.change(screen.getByLabelText('Mot de passe'), { target: { value: 'faux' } });
    fireEvent.click(screen.getByRole('button', { name: 'Se connecter' }));
    await screen.findByRole('button', { name: 'Continuer' });
    expect(email().value).toBe('');
    expect(screen.getByRole('alert').textContent).toBe('Vérification impossible. Recommencez.');
    expect(screen.queryByLabelText('Mot de passe')).toBeNull();
  });

  it('erreur technique : reste sur l’étape mot de passe', async () => {
    await reachPassword();
    passwordMock.mockResolvedValue('error');
    fireEvent.change(screen.getByLabelText('Mot de passe'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Se connecter' }));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('Mot de passe')).toBeTruthy();
  });
});

describe('caméra refusée ou absente', () => {
  it.each([
    ['NotAllowedError', 'autoris'],
    ['NotFoundError', 'aucune caméra'],
  ])('%s : message clair, pas d’étape suivante', async (name, fragment) => {
    getUserMedia.mockRejectedValue(Object.assign(new Error('x'), { name }));
    render(<LoginForm />);
    fireEvent.change(email(), { target: { value: 'ops@basecamp.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continuer' }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent?.toLowerCase()).toContain(fragment);
    expect(screen.queryByRole('button', { name: 'Vérifier mon visage' })).toBeNull();
    expect(screen.queryByLabelText('Mot de passe')).toBeNull();
    expect(faceMock).not.toHaveBeenCalled();
  });
});

describe('défi expiré', () => {
  it('au bout du délai : retour à l’étape 1, caméra arrêtée', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    identifyMock.mockResolvedValue({ kind: 'ok', challengeId: 'chal-1', expiresIn: 120 });
    render(<LoginForm />);
    await validateIdentifier();
    const opened = tracks;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(121_000);
    });
    await screen.findByRole('button', { name: 'Continuer' });
    expect(screen.getByRole('alert').textContent).toContain('délai');
    opened.forEach((track) => expect(track.stop).toHaveBeenCalled());
  });
});

describe('arrêt de la caméra', () => {
  it('à la sortie de l’écran, arrête les pistes', async () => {
    const view = render(<LoginForm />);
    await validateIdentifier();
    const opened = tracks;
    view.unmount();
    opened.forEach((track) => expect(track.stop).toHaveBeenCalled());
  });
});

describe('blocage', () => {
  async function failPasswordOnce() {
    passwordMock.mockResolvedValue('refused');
    fireEvent.change(screen.getByLabelText('Mot de passe'), { target: { value: 'faux' } });
    fireEvent.click(screen.getByRole('button', { name: 'Se connecter' }));
    await screen.findByRole('button', { name: 'Continuer' });
  }

  it('après 3 mots de passe faux : compte à rebours, champs désactivés, aucun appel', async () => {
    render(<LoginForm />);
    for (let i = 0; i < 3; i++) {
      await validateIdentifier();
      faceMock.mockResolvedValue('accepted');
      fireEvent.click(screen.getByRole('button', { name: 'Vérifier mon visage' }));
      await screen.findByLabelText('Mot de passe');
      await failPasswordOnce();
    }
    expect(screen.getByTestId('lock-countdown').textContent).toBe('05:00');
    expect(email().disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Continuer' }) as HTMLButtonElement).disabled).toBe(true);
    identifyMock.mockClear();
    fireEvent.submit(email().closest('form') as HTMLFormElement);
    expect(identifyMock).not.toHaveBeenCalled();
  });

  it('le blocage survit à un rechargement et se lève à l’échéance', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    window.localStorage.setItem(
      'basecamp-bo-login-lock',
      JSON.stringify({ face: 0, password: 0, windowStart: 0, lockedUntil: Date.now() + LOCK_DURATION_MS })
    );
    render(<LoginForm />);
    await waitFor(() => expect(screen.getByTestId('lock-countdown').textContent).toBe('05:00'));
    expect(email().disabled).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(LOCK_DURATION_MS + 1000);
    });
    await waitFor(() => expect(email().disabled).toBe(false));
    expect(screen.queryByTestId('lock-countdown')).toBeNull();
  });

  it('après 5 visages refusés, bloque aussi', async () => {
    render(<LoginForm />);
    faceMock.mockResolvedValue('refused');
    for (let i = 0; i < 5; i++) {
      await validateIdentifier();
      fireEvent.click(screen.getByRole('button', { name: 'Vérifier mon visage' }));
      await waitFor(() => expect(faceMock).toHaveBeenCalledTimes(i + 1));
      await screen.findByRole('button', { name: 'Continuer' });
    }
    expect(screen.getByTestId('lock-countdown')).toBeTruthy();
  });
});
