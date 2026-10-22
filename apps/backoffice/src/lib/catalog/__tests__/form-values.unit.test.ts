import { describe, expect, it } from 'vitest';
import {
  EMPTY_VALUES,
  parseInteger,
  toCreatePayload,
  toUpdatePayload,
  validateForm,
  valuesFromProduct,
  type FormValues,
} from '../form-values';
import type { Product } from '../types';

const VALID: FormValues = {
  ...EMPTY_VALUES,
  name: ' Tente Tunnel ',
  category: 'tentes',
  price: '129,90',
  shortDescription: 'Deux places',
  description: 'Une tente légère.',
  stock: '12',
};

const PRODUCT: Product = {
  id: 'tente-tunnel',
  slug: 'tente-tunnel',
  name: 'Tente Tunnel',
  category: 'tentes',
  price_cents: 12990,
  compare_at_price_cents: 14900,
  short_description: 'Deux places',
  description: 'Une tente légère.',
  specs: { weight_grams: 2100, comfort_temp_c: -5, material: 'Nylon' },
  stock: 12,
  availability: 'in_stock',
  image_keys: [],
  image_urls: [],
  version: 4,
  archived_at: null,
};

describe('validateForm', () => {
  it('accepte une saisie complète', () => {
    expect(validateForm(VALID, 'create')).toEqual({});
  });

  it('exige les champs obligatoires, avec un message par champ', () => {
    const errors = validateForm(EMPTY_VALUES, 'create');

    expect(Object.keys(errors).sort()).toEqual(
      ['category', 'description', 'name', 'price', 'shortDescription', 'stock'].sort()
    );
    expect(errors.name).toBe('Le nom est obligatoire.');
  });

  it.each([
    ['name', 'x'.repeat(201), 'Le nom : 200 caractères au plus.'],
    ['shortDescription', 'x'.repeat(301), 'La description courte : 300 caractères au plus.'],
    ['description', 'x'.repeat(5001), 'La description : 5000 caractères au plus.'],
    ['price', '12,345', 'Prix invalide : montant en euros, 2 décimales au plus, 100 000 € au plus.'],
    ['comparePrice', '-1', 'Prix barré invalide : montant en euros, 2 décimales au plus.'],
    ['stock', '1.5', 'Stock : nombre entier entre 0 et 1 000 000.'],
    ['stock', '1000001', 'Stock : nombre entier entre 0 et 1 000 000.'],
    ['category', 'jardin', 'Choisissez une catégorie.'],
    ['seasons', '5', 'Saisons : nombre entier entre 0 et 4.'],
    ['comfortTempC', '-101', 'Température de confort : nombre entier entre -100 et 100.'],
    ['weightGrams', 'lourd', 'Poids : nombre entier entre 0 et 1000000.'],
    ['material', 'x'.repeat(101), 'Matériau : 100 caractères au plus.'],
  ] as const)('refuse %s = « %s »', (field, value, message) => {
    expect(validateForm({ ...VALID, [field]: value }, 'create')[field]).toBe(message);
  });

  it('contrôle l’identifiant seulement à la création, et seulement s’il est saisi', () => {
    expect(validateForm({ ...VALID, slug: 'Tente Tunnel' }, 'create').slug).toMatch(/minuscules/);
    expect(validateForm({ ...VALID, slug: 'a'.repeat(129) }, 'create').slug).toMatch(/128/);
    expect(validateForm({ ...VALID, slug: 'tente-tunnel' }, 'create')).toEqual({});
    expect(validateForm({ ...VALID, slug: 'Pas Valide' }, 'edit')).toEqual({});
  });
});

describe('parseInteger', () => {
  it('borne les entiers et refuse le reste', () => {
    expect(parseInteger(' 7 ', 0, 10)).toBe(7);
    expect(parseInteger('-3', -5, 5)).toBe(-3);
    expect(parseInteger('11', 0, 10)).toBeNull();
    expect(parseInteger('1e2', 0, 1000)).toBeNull();
    expect(parseInteger('', 0, 10)).toBeNull();
  });
});

describe('corps envoyés à l’API', () => {
  it('crée en centimes, sans slug vide ni champ vide, avec les caractéristiques saisies', () => {
    const payload = toCreatePayload({
      ...VALID,
      weightGrams: '2100',
      comfortTempC: '-5',
      material: ' Nylon ',
    });

    expect(payload).toEqual({
      name: 'Tente Tunnel',
      category: 'tentes',
      price_cents: 12990,
      compare_at_price_cents: null,
      short_description: 'Deux places',
      description: 'Une tente légère.',
      specs: { weight_grams: 2100, comfort_temp_c: -5, material: 'Nylon' },
      stock: 12,
    });
    expect(toCreatePayload({ ...VALID, slug: 'tente-tunnel' })).toMatchObject({ slug: 'tente-tunnel' });
  });

  it('modifie avec la version lue et permet d’effacer le prix barré', () => {
    const payload = toUpdatePayload({ ...VALID, comparePrice: '' }, 4);

    expect(payload).toMatchObject({ version: 4, compare_at_price_cents: null, price_cents: 12990 });
    expect(payload).not.toHaveProperty('slug');
  });
});

describe('valuesFromProduct', () => {
  it('remplit le formulaire depuis le produit et revient au même produit', () => {
    const values = valuesFromProduct(PRODUCT);

    expect(values).toMatchObject({
      name: 'Tente Tunnel',
      price: '129,90',
      comparePrice: '149',
      stock: '12',
      weightGrams: '2100',
      comfortTempC: '-5',
      material: 'Nylon',
      seasons: '',
    });
    expect(validateForm(values, 'edit')).toEqual({});
    expect(toUpdatePayload(values, 4)).toMatchObject({
      price_cents: 12990,
      compare_at_price_cents: 14900,
      specs: PRODUCT.specs,
    });
  });
});
