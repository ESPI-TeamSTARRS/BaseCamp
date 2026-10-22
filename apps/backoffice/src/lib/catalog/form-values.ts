import { CATEGORIES, type Product, type Specs } from './types';
import { centsToInput, parseEuros } from './money';

// Saisie du formulaire produit et validation alignee sur l'API de shop (memes bornes), pour que
// l'operateur voie l'erreur avant l'envoi. Shop reste la reference : il valide a nouveau.

export interface FormValues {
  name: string;
  slug: string;
  category: string;
  price: string;
  comparePrice: string;
  shortDescription: string;
  description: string;
  stock: string;
  weightGrams: string;
  waterproofingMm: string;
  comfortTempC: string;
  seasons: string;
  capacityLiters: string;
  material: string;
}

export type FieldErrors = Partial<Record<keyof FormValues, string>>;
export type FormMode = 'create' | 'edit';

export const EMPTY_VALUES: FormValues = {
  name: '',
  slug: '',
  category: '',
  price: '',
  comparePrice: '',
  shortDescription: '',
  description: '',
  stock: '',
  weightGrams: '',
  waterproofingMm: '',
  comfortTempC: '',
  seasons: '',
  capacityLiters: '',
  material: '',
};

const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const MEASURE_MAX = 1_000_000;

export function parseInteger(text: string, min: number, max: number): number | null {
  const value = text.trim();
  if (!/^-?\d{1,9}$/.test(value)) return null;
  const number = Number(value);
  return number >= min && number <= max ? number : null;
}

function text(error: FieldErrors, field: keyof FormValues, value: string, max: number, label: string) {
  const length = value.trim().length;
  if (length === 0) error[field] = `${label} est obligatoire.`;
  else if (length > max) error[field] = `${label} : ${max} caractères au plus.`;
}

function optionalInteger(
  error: FieldErrors,
  field: keyof FormValues,
  value: string,
  min: number,
  max: number,
  label: string
) {
  if (value.trim() !== '' && parseInteger(value, min, max) === null)
    error[field] = `${label} : nombre entier entre ${min} et ${max}.`;
}

export function validateForm(values: FormValues, mode: FormMode): FieldErrors {
  const error: FieldErrors = {};
  text(error, 'name', values.name, 200, 'Le nom');
  if (mode === 'create' && values.slug.trim() !== '') {
    const slug = values.slug.trim();
    if (slug.length > 128 || !SLUG_RE.test(slug))
      error.slug = 'Identifiant : minuscules, chiffres et tirets (128 caractères au plus).';
  }
  if (!CATEGORIES.some((category) => category.value === values.category))
    error.category = 'Choisissez une catégorie.';
  if (values.price.trim() === '') error.price = 'Le prix est obligatoire.';
  else if (parseEuros(values.price) === null)
    error.price = 'Prix invalide : montant en euros, 2 décimales au plus, 100 000 € au plus.';
  if (values.comparePrice.trim() !== '' && parseEuros(values.comparePrice) === null)
    error.comparePrice = 'Prix barré invalide : montant en euros, 2 décimales au plus.';
  text(error, 'shortDescription', values.shortDescription, 300, 'La description courte');
  text(error, 'description', values.description, 5000, 'La description');
  if (values.stock.trim() === '') error.stock = 'Le stock est obligatoire.';
  else if (parseInteger(values.stock, 0, 1_000_000) === null)
    error.stock = 'Stock : nombre entier entre 0 et 1 000 000.';
  optionalInteger(error, 'weightGrams', values.weightGrams, 0, MEASURE_MAX, 'Poids');
  optionalInteger(error, 'waterproofingMm', values.waterproofingMm, 0, MEASURE_MAX, 'Imperméabilité');
  optionalInteger(error, 'comfortTempC', values.comfortTempC, -100, 100, 'Température de confort');
  optionalInteger(error, 'seasons', values.seasons, 0, 4, 'Saisons');
  optionalInteger(error, 'capacityLiters', values.capacityLiters, 0, MEASURE_MAX, 'Capacité');
  if (values.material.trim().length > 100) error.material = 'Matériau : 100 caractères au plus.';
  return error;
}

function specsOf(values: FormValues): Specs {
  const specs: Specs = {};
  const numbers: Array<[keyof Specs, string, number, number]> = [
    ['weight_grams', values.weightGrams, 0, MEASURE_MAX],
    ['waterproofing_mm', values.waterproofingMm, 0, MEASURE_MAX],
    ['comfort_temp_c', values.comfortTempC, -100, 100],
    ['seasons', values.seasons, 0, 4],
    ['capacity_liters', values.capacityLiters, 0, MEASURE_MAX],
  ];
  for (const [key, raw, min, max] of numbers) {
    const value = raw.trim() === '' ? null : parseInteger(raw, min, max);
    if (value !== null) (specs as Record<string, number>)[key] = value;
  }
  if (values.material.trim() !== '') specs.material = values.material.trim();
  return specs;
}

function common(values: FormValues) {
  return {
    name: values.name.trim(),
    category: values.category,
    price_cents: parseEuros(values.price) as number,
    compare_at_price_cents: values.comparePrice.trim() === '' ? null : parseEuros(values.comparePrice),
    short_description: values.shortDescription.trim(),
    description: values.description.trim(),
    specs: specsOf(values),
    stock: parseInteger(values.stock, 0, 1_000_000) as number,
  };
}

/** Corps de creation (valeurs deja validees). Le slug n'est envoye que s'il est renseigne. */
export function toCreatePayload(values: FormValues) {
  const payload: Record<string, unknown> = common(values);
  if (values.slug.trim() !== '') payload.slug = values.slug.trim();
  return payload;
}

/** Corps de modification : la version lue est celle qui sert de garde de concurrence. */
export function toUpdatePayload(values: FormValues, version: number) {
  return { version, ...common(values) };
}

export function valuesFromProduct(product: Product): FormValues {
  const specs = product.specs;
  const show = (value: number | undefined) => (value === undefined ? '' : String(value));
  return {
    name: product.name,
    slug: product.slug,
    category: product.category,
    price: centsToInput(product.price_cents),
    comparePrice: centsToInput(product.compare_at_price_cents),
    shortDescription: product.short_description,
    description: product.description,
    stock: String(product.stock),
    weightGrams: show(specs.weight_grams),
    waterproofingMm: show(specs.waterproofing_mm),
    comfortTempC: show(specs.comfort_temp_c),
    seasons: show(specs.seasons),
    capacityLiters: show(specs.capacity_liters),
    material: specs.material ?? '',
  };
}
