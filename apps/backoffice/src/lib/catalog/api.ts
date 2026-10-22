import { redirectToLogin } from './navigation';
import type { Product, ProductPage } from './types';

// Appels du navigateur aux routes serveur du back-office (/bff/products) : memes origine, cookie HttpOnly
// envoye automatiquement. Aucun jeton n'est manipule ici.

export type ApiResult<T> =
  { ok: true; data: T } | { ok: false; status: number; code: string; detail: string };

const NETWORK_FAILURE = {
  status: 0,
  code: 'network',
  detail: 'Connexion impossible. Vérifiez votre réseau puis réessayez.',
};

export async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...init });
  } catch {
    return { ok: false, ...NETWORK_FAILURE };
  }
  const body: unknown = await response.json().catch(() => null);
  if (response.ok && body !== null) return { ok: true, data: body as T };
  if (response.status === 401) redirectToLogin();
  const failure = (typeof body === 'object' && body !== null ? body : {}) as {
    detail?: unknown;
    code?: unknown;
  };
  return {
    ok: false,
    status: response.status,
    code: typeof failure.code === 'string' ? failure.code : 'error',
    detail: typeof failure.detail === 'string' ? failure.detail : 'Une erreur est survenue. Réessayez.',
  };
}

const JSON_HEADERS = { 'content-type': 'application/json' };

export interface ListParams {
  q: string;
  includeArchived: boolean;
  offset: number;
  limit: number;
}

export const catalogApi = {
  list({ q, includeArchived, offset, limit }: ListParams) {
    const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (includeArchived) query.set('include_archived', 'true');
    if (q.trim() !== '') query.set('q', q.trim());
    return request<ProductPage>(`/bff/products?${query}`);
  },
  get(id: string) {
    return request<Product>(`/bff/products/${encodeURIComponent(id)}`);
  },
  create(payload: unknown) {
    return request<Product>('/bff/products', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
  },
  update(id: string, payload: unknown) {
    return request<Product>(`/bff/products/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
  },
  archive(id: string) {
    return request<Product>(`/bff/products/${encodeURIComponent(id)}/archive`, { method: 'POST' });
  },
  uploadImage(id: string, file: File) {
    return request<Product>(`/bff/products/${encodeURIComponent(id)}/image`, {
      method: 'POST',
      headers: { 'content-type': 'application/octet-stream' },
      body: file,
    });
  },
};
