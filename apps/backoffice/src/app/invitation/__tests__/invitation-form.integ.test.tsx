// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import InvitationPage from '../page';
import { InvitationForm } from '../invitation-form';

vi.mock('@/lib/invitation-api', () => ({ completeInvitation: vi.fn() }));
vi.mock('@/lib/capture', () => ({ captureFrame: vi.fn() }));

import { captureFrame } from '@/lib/capture';
import { completeInvitation } from '@/lib/invitation-api';

const completeMock = vi.mocked(completeInvitation);
const captureMock = vi.mocked(captureFrame);
const STRONG = 'sentier-du-mont-blanc';
const LINK_MESSAGE =
  'Ce lien est invalide, expiré ou déjà utilisé. Demandez un nouveau lien à l’administrateur IT.';

let tracks: { stop: ReturnType<typeof vi.fn> }[];
let getUserMedia: ReturnType<typeof vi.fn>;
let shots: number;

beforeEach(() => {
  shots = 0;
  getUserMedia = vi.fn().mockImplementation(async () => {
    tracks = [{ stop: vi.fn() }];
    return { getTracks: () => tracks } as unknown as MediaStream;
  });
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });
  captureMock.mockImplementation(() => `photo-${++shots}`);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function open(token: string | null = 'jeton-valide-0123456789') {
  render(<InvitationForm readToken={() => token} />);
  if (token) await screen.findByLabelText(/^Mot de passe/);
}

async function startCameraAndShoot(count: number) {
  fireEvent.click(await screen.findByRole('button', { name: 'Activer la caméra' }));
  const shoot = await screen.findByRole('button', { name: 'Prendre une photo' });
  for (let i = 0; i < count; i++) fireEvent.click(shoot);
}

function fillPasswords(value = STRONG, confirmation = value) {
  fireEvent.change(screen.getByLabelText(/^Mot de passe/), { target: { value } });
  fireEvent.change(screen.getByLabelText('Confirmez le mot de passe'), { target: { value: confirmation } });
}

const submit = () => screen.getByRole('button', { name: 'Créer mon compte' }) as HTMLButtonElement;

describe('page', () => {
  it('rend le formulaire d’invitation', () => {
    expect((InvitationPage() as { type: unknown }).type).toBe(InvitationForm);
  });
});

describe('lecture unique du jeton', () => {
  it('lit le jeton UNE seule fois : le fragment est effacé à la première lecture, un rendu suivant ne doit pas le relire', async () => {
    // Le composant est rendu avec une NOUVELLE fonction a chaque rendu (comme le defaut en production) :
    // la lecture ne doit pas se rejouer, sinon la seconde lecture ne trouve plus rien (fragment efface).
    const reads = vi
      .fn<() => string | null>()
      .mockReturnValueOnce('jeton-valide-0123456789')
      .mockReturnValue(null);
    const view = render(<InvitationForm readToken={() => reads()} />);
    await screen.findByLabelText(/^Mot de passe/);

    view.rerender(<InvitationForm readToken={() => reads()} />);
    fireEvent.change(screen.getByLabelText(/^Mot de passe/), { target: { value: STRONG } });
    await new Promise((resolve) => setTimeout(resolve, 20)); // laisse passer une relecture eventuelle

    expect(reads).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByLabelText(/^Mot de passe/)).toBeTruthy();
  });

  it('avec le vrai lecteur : fragment lu, adresse nettoyée, formulaire affiché et jeton envoyé', async () => {
    window.history.replaceState(null, '', '/invitation#token=abcdefghijklmnopqrstuvwxyz0123456789_-AB');
    completeMock.mockResolvedValue('created');
    render(<InvitationForm />);
    await screen.findByLabelText(/^Mot de passe/);
    expect(window.location.hash).toBe('');

    fillPasswords();
    await startCameraAndShoot(3);
    fireEvent.click(submit());

    await screen.findByText(/Votre compte est créé/);
    expect(completeMock).toHaveBeenCalledWith(
      'abcdefghijklmnopqrstuvwxyz0123456789_-AB',
      STRONG,
      expect.any(Array)
    );
  });
});

describe('lien', () => {
  it('sans jeton valide : un seul message, aucun formulaire', async () => {
    await open(null);

    expect((await screen.findByRole('alert')).textContent).toBe(LINK_MESSAGE);
    expect(screen.queryByLabelText(/^Mot de passe/)).toBeNull();
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('avec un jeton : formulaire, caméra éteinte tant qu’on ne l’active pas', async () => {
    await open();

    expect(screen.getByRole('button', { name: 'Activer la caméra' })).toBeTruthy();
    expect(getUserMedia).not.toHaveBeenCalled();
  });
});

describe('photos', () => {
  it('active la caméra, prend des photos, compte et permet de les retirer', async () => {
    await open();
    await startCameraAndShoot(4);

    expect(screen.getAllByAltText(/^Photo \d$/)).toHaveLength(4);
    fireEvent.click(screen.getAllByRole('button', { name: 'Retirer' })[0]);
    expect(screen.getAllByAltText(/^Photo \d$/)).toHaveLength(3);
    expect(screen.getByText(/3 photos sur 10/)).toBeTruthy();
  });

  it('ne dépasse pas 10 photos', async () => {
    await open();
    await startCameraAndShoot(12);

    expect(screen.getAllByAltText(/^Photo \d+$/)).toHaveLength(10);
    expect((screen.getByRole('button', { name: 'Prendre une photo' }) as HTMLButtonElement).disabled).toBe(
      true
    );
  });

  it('une capture qui échoue affiche un message sans ajouter de photo', async () => {
    await open();
    captureMock.mockImplementation(() => {
      throw new Error('video_not_ready');
    });
    await startCameraAndShoot(1);

    expect((await screen.findByRole('alert')).textContent).toBe('La capture a échoué. Réessayez.');
    expect(screen.queryAllByAltText(/^Photo/)).toHaveLength(0);
  });

  it.each([
    ['NotAllowedError', 'L’accès à la caméra n’est pas autorisé'],
    ['NotFoundError', 'Aucune caméra détectée'],
    ['AbortError', 'La caméra est inutilisable'],
  ])('caméra refusée (%s) : message clair', async (name, text) => {
    getUserMedia.mockRejectedValue(Object.assign(new Error('x'), { name }));
    await open();
    fireEvent.click(screen.getByRole('button', { name: 'Activer la caméra' }));

    expect((await screen.findByRole('alert')).textContent).toContain(text);
  });
});

describe('envoi', () => {
  it('reste bloqué sous 3 photos ou avec un mot de passe trop court ou différent', async () => {
    await open();
    fillPasswords();
    await startCameraAndShoot(2);
    expect(submit().disabled).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Prendre une photo' }));
    expect(submit().disabled).toBe(false);

    fillPasswords('court');
    expect(submit().disabled).toBe(true);
    fillPasswords(STRONG, 'autre-chose-que-ci-dessus');
    expect(submit().disabled).toBe(true);
    fireEvent.submit(submit().closest('form') as HTMLFormElement);
    expect((await screen.findByRole('alert')).textContent).toContain('différents');
    expect(completeMock).not.toHaveBeenCalled();
  });

  it('un mot de passe de moins de 12 caractères est expliqué au clavier', async () => {
    await open();
    fillPasswords('court');
    await startCameraAndShoot(3);

    fireEvent.submit(submit().closest('form') as HTMLFormElement);

    expect((await screen.findByRole('alert')).textContent).toContain('au moins 12 caractères');
  });

  it('sans assez de photos, la soumission clavier est refusée avec un message', async () => {
    await open();
    fillPasswords();
    await startCameraAndShoot(1);

    fireEvent.submit(submit().closest('form') as HTMLFormElement);

    expect((await screen.findByRole('alert')).textContent).toContain('entre 3 et 10 photos');
    expect(completeMock).not.toHaveBeenCalled();
  });

  it('succès : envoie jeton, mot de passe et photos, puis ne garde rien et éteint la caméra', async () => {
    completeMock.mockResolvedValue('created');
    await open();
    fillPasswords();
    await startCameraAndShoot(3);

    fireEvent.click(submit());

    await screen.findByText(/Votre compte est créé/);
    expect(completeMock).toHaveBeenCalledWith('jeton-valide-0123456789', STRONG, [
      'photo-1',
      'photo-2',
      'photo-3',
    ]);
    expect(tracks[0].stop).toHaveBeenCalled();
    expect(screen.queryAllByAltText(/^Photo/)).toHaveLength(0);
    expect(
      within(screen.getByRole('status')).getByRole('link', { name: 'vous connecter' }).getAttribute('href')
    ).toBe('/login');
  });

  it('lien refusé (401) : message unique, plus de formulaire', async () => {
    completeMock.mockResolvedValue('invalid_link');
    await open();
    fillPasswords();
    await startCameraAndShoot(3);

    fireEvent.click(submit());

    expect((await screen.findByRole('alert')).textContent).toBe(LINK_MESSAGE);
    expect(screen.queryByLabelText(/^Mot de passe/)).toBeNull();
  });

  it.each([
    ['weak_password', 'Ce mot de passe n’est pas accepté'],
    ['photo_count', 'entre 3 et 10 photos'],
    ['invalid_photo', 'Une photo est illisible'],
    ['no_face', 'visage n’a pas été reconnu'],
    ['error', 'Service momentanément indisponible'],
  ] as const)(
    '%s : message clair, photos effacées, nouvel essai possible avec le même lien',
    async (result, text) => {
      completeMock.mockResolvedValueOnce(result);
      await open();
      fillPasswords();
      await startCameraAndShoot(3);

      fireEvent.click(submit());

      await waitFor(() => expect(screen.getByRole('alert').textContent).toContain(text));
      expect(screen.queryAllByAltText(/^Photo/)).toHaveLength(0);
      expect(tracks[0].stop).toHaveBeenCalled();
      expect((screen.getByLabelText(/^Mot de passe/) as HTMLInputElement).value).toBe('');

      completeMock.mockResolvedValueOnce('created');
      fillPasswords();
      await startCameraAndShoot(3);
      fireEvent.click(submit());
      await screen.findByText(/Votre compte est créé/);
      expect(completeMock).toHaveBeenLastCalledWith('jeton-valide-0123456789', STRONG, expect.any(Array));
    }
  );

  it('éteint la caméra si on quitte la page', async () => {
    await open();
    fireEvent.click(screen.getByRole('button', { name: 'Activer la caméra' }));
    await screen.findByTestId('camera-preview');

    cleanup();

    expect(tracks[0].stop).toHaveBeenCalled();
  });

  it('n’interroge pas le serveur sans formulaire complet (double clic)', async () => {
    let release: (value: 'created') => void = () => undefined;
    completeMock.mockReturnValue(new Promise((resolve) => (release = resolve)));
    await open();
    fillPasswords();
    await startCameraAndShoot(3);

    fireEvent.click(submit());
    fireEvent.submit(submit().closest('form') as HTMLFormElement);

    expect(completeMock).toHaveBeenCalledTimes(1);
    release('created');
    await screen.findByText(/Votre compte est créé/);
  });
});
