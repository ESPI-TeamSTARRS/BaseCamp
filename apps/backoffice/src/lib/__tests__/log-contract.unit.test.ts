import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildLogEvent } from '../log-event';

// Contrat commun des journaux (docs/development/log-event.schema.json), relu ici pour que les
// evenements du back-office restent conformes sans dependance de validation supplementaire.
interface Schema {
  required: string[];
  properties: Record<string, { pattern?: string; enum?: string[] }>;
  description: string;
}

const schema = JSON.parse(
  readFileSync(path.resolve(__dirname, '../../../../../docs/development/log-event.schema.json'), 'utf8')
) as Schema;

function violations(event: Record<string, unknown>): string[] {
  const problems: string[] = [];
  for (const name of schema.required) if (!(name in event)) problems.push(`manque ${name}`);
  for (const [name, value] of Object.entries(event)) {
    const rule = schema.properties[name];
    if (!rule) {
      problems.push(`champ inconnu ${name}`);
      continue;
    }
    if (rule.pattern && !new RegExp(rule.pattern).test(String(value))) problems.push(`motif ${name}`);
    if (rule.enum && !rule.enum.includes(String(value))) problems.push(`valeur ${name}`);
  }
  if (event.resource_id !== undefined && event.resource_type === undefined)
    problems.push('resource_id sans resource_type');
  if ((event.outcome === 'success') === 'reason' in event) problems.push('reason incoherent');
  return problems;
}

const base = { correlationId: 'b3a9d7e1-55c4-4d0a-8f21-0c9e4a6d7f33' };

describe('contrat des journaux : backoffice.order_view', () => {
  it('une consultation réussie respecte le schéma commun', () => {
    const event = buildLogEvent({
      ...base,
      event: 'backoffice.order_view',
      outcome: 'success',
      durationMs: 12,
      resource: { type: 'order', id: '00000000-0000-4000-8000-000000000001' },
      actor: { type: 'user', id: '0123456789abcdef' },
      attributes: { status: 200 },
    });

    expect(violations({ ...event })).toEqual([]);
  });

  it('un refus respecte le schéma commun et porte un motif', () => {
    const event = buildLogEvent({
      ...base,
      event: 'backoffice.order_view',
      outcome: 'denied',
      reason: 'not_found',
      resource: { type: 'order', id: 'abc' },
      actor: { type: 'user', id: '0123456789abcdef' },
    });

    expect(violations({ ...event })).toEqual([]);
  });

  it('détecte un champ hors contrat', () => {
    expect(
      violations({ ...buildLogEvent({ ...base, event: 'a.b', outcome: 'success' }), email: 'x' })
    ).toEqual(['champ inconnu email']);
  });

  it('le schéma nomme le back-office parmi les émetteurs', () => {
    expect(schema.description).toContain('backoffice');
  });
});
