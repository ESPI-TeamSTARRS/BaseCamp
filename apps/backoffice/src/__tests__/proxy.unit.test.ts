import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { proxy } from '../proxy';

afterEach(() => vi.restoreAllMocks());

describe('proxy', () => {
  it('journalise la page servie et propage le X-Correlation-ID reçu', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const response = proxy(
      new NextRequest('http://admin.localhost/', { headers: { 'x-correlation-id': 'abcdefgh-1234' } })
    );
    expect(response.headers.get('X-Correlation-ID')).toBe('abcdefgh-1234');
    expect(JSON.parse(spy.mock.calls[0][0] as string)).toMatchObject({
      service: 'basecamp-backoffice',
      event: 'backoffice.page_served',
      outcome: 'success',
      correlation_id: 'abcdefgh-1234',
    });
  });

  it('génère un identifiant quand celui reçu est invalide', () => {
    vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const response = proxy(
      new NextRequest('http://admin.localhost/', { headers: { 'x-correlation-id': 'x' } })
    );
    expect(response.headers.get('X-Correlation-ID')).toMatch(/^[0-9a-f-]{36}$/);
  });
});
