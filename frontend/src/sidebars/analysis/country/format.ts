import type { Rate } from '../../../api/types';

export const number = (value: number) => value.toLocaleString();

export function rate(value: Rate | null | undefined, unit: string): string | null {
  return value ? `${value.value} ${unit}${value.as_of ? ` (${value.as_of})` : ''}` : null;
}
