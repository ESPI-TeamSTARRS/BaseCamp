export const SHIPPING_COUNTRIES = [
  { code: 'FR', label: 'France' },
  { code: 'BE', label: 'Belgique' },
  { code: 'CH', label: 'Suisse' },
  { code: 'LU', label: 'Luxembourg' },
  { code: 'DE', label: 'Allemagne' },
  { code: 'ES', label: 'Espagne' },
  { code: 'IT', label: 'Italie' },
] as const;

export interface OrderForm {
  email: string;
  fullName: string;
  line1: string;
  line2: string;
  postalCode: string;
  city: string;
  country: string;
}

export type OrderFormErrors = Partial<Record<keyof OrderForm, string>>;
export type OrderFormResult = { ok: true; form: OrderForm } | { ok: false; errors: OrderFormErrors };

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const REQUIRED_FIELDS: Array<[keyof OrderForm, string]> = [
  ['fullName', 'Indiquez votre nom complet.'],
  ['line1', 'Indiquez votre adresse.'],
  ['postalCode', 'Indiquez votre code postal.'],
  ['city', 'Indiquez votre ville.'],
];

/** Contrôle côté navigateur pour guider la saisie : le serveur revalide tout. */
export function validateOrderForm(input: OrderForm): OrderFormResult {
  const form: OrderForm = {
    email: input.email.trim(),
    fullName: input.fullName.trim(),
    line1: input.line1.trim(),
    line2: input.line2.trim(),
    postalCode: input.postalCode.trim(),
    city: input.city.trim(),
    country: input.country.trim().toUpperCase(),
  };
  const errors: OrderFormErrors = {};
  if (!EMAIL_PATTERN.test(form.email) || form.email.length > 254)
    errors.email = 'Indiquez une adresse email valide.';
  for (const [field, message] of REQUIRED_FIELDS) {
    if (form[field] === '') errors[field] = message;
  }
  if (!SHIPPING_COUNTRIES.some((country) => country.code === form.country)) {
    errors.country = 'Nous ne livrons pas ce pays.';
  }
  return Object.keys(errors).length === 0 ? { ok: true, form } : { ok: false, errors };
}
