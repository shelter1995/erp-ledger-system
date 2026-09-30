import { decimalMoney } from './money';

/** Display only: keep the original value for calculations and editing. */
export function formatQuantity(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  const text = String(value);
  const match = text.match(/^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(.*)$/i);
  if (!match) return text;
  return decimalMoney(match[1]).toFixed(2) + match[2];
}
