import { decimalMoney, type MoneyValue } from './money';

export interface ProfitInputs {
  orderValue: MoneyValue;
  purchaseAmount?: MoneyValue;
  taxAmount?: MoneyValue;
  taxRefund?: MoneyValue;
  grossProfit?: MoneyValue;
}

// Keep precision until the final display/aggregate. The API includes original
// source precision and is authoritative when it supplies the calculated value.
export function grossProfitValue(input: ProfitInputs): string {
  if (input.grossProfit !== undefined) return String(input.grossProfit);
  return decimalMoney(input.orderValue)
    .minus(input.purchaseAmount ?? 0)
    .minus(input.taxAmount ?? 0)
    .plus(input.taxRefund ?? 0)
    .toString();
}
