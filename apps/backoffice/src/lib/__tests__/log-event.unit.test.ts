import { describe, expect, it, vi } from 'vitest';
import { buildLogEvent, emit, resolveCorrelationId, SERVICE_NAME } from '../log-event';

const NOW = new Date('2026-10-21T22:00:00.123Z');
const base = { event: 'a.b', correlationId: 'abcdefgh' };

describe('resolveCorrelationId', () => {
  it('retient un identifiant bien forme', () => {
    expect(resolveCorrelationId('b3a9d7e1-55c4-4d0a', () => 'x')).toBe('b3a9d7e1-55c4-4d0a');
  });

  it.each([null, undefined, '', 'court', 'a'.repeat(65), 'avec espace 12345'])(
    'génère un identifiant pour %j',
    (received) => {
      expect(resolveCorrelationId(received, () => 'genere-12345678')).toBe('genere-12345678');
    }
  );
});

describe('buildLogEvent', () => {
  it('produit un événement de succès au contrat commun', () => {
    expect(buildLogEvent({ ...base, outcome: 'success', now: NOW })).toEqual({
      timestamp: '2026-10-21T22:00:00.123Z',
      service: SERVICE_NAME,
      level: 'info',
      event: 'a.b',
      correlation_id: 'abcdefgh',
      outcome: 'success',
    });
  });

  it('exige reason hors succès et choisit le niveau', () => {
    expect(() => buildLogEvent({ ...base, outcome: 'denied' })).toThrow();
    expect(buildLogEvent({ ...base, outcome: 'denied', reason: 'forbidden', durationMs: 4 })).toMatchObject({
      level: 'warning',
      reason: 'forbidden',
      duration_ms: 4,
    });
    expect(buildLogEvent({ ...base, outcome: 'error', reason: 'boom' }).level).toBe('error');
  });

  it('date l’événement à l’instant courant par défaut', () => {
    expect(buildLogEvent({ ...base, outcome: 'success' }).timestamp).toMatch(/Z$/);
  });
});

describe('emit', () => {
  it('écrit un document JSON par ligne', () => {
    const write = vi.fn();
    emit(buildLogEvent({ ...base, outcome: 'success', now: NOW }), write);
    expect(write).toHaveBeenCalledTimes(1);
    expect(JSON.parse(write.mock.calls[0][0]).event).toBe('a.b');
  });

  it('écrit sur la sortie standard par défaut', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    emit(buildLogEvent({ ...base, outcome: 'success', now: NOW }));
    expect(spy).toHaveBeenCalledOnce();
    spy.mockRestore();
  });
});
