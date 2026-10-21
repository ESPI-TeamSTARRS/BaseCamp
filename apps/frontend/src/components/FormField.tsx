export const inputClass =
  'mt-2 block h-12 w-full rounded-lg border border-granite/20 bg-white px-4 text-base text-granite focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/30';

export const submitClass =
  'mt-6 h-12 w-full rounded-lg bg-bivouac text-base font-bold text-white transition-colors hover:bg-bivouac-dark disabled:opacity-60';

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="mt-2 text-sm text-bivouac-dark">
      {message}
    </p>
  );
}

export function FormError({ message }: { message: string }) {
  return (
    <p role="alert" className="mt-6 rounded-lg bg-bivouac/10 p-3 text-sm text-bivouac-dark">
      {message}
    </p>
  );
}
