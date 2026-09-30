export function currentOrderYear(now = new Date()): string {
  return new Intl.DateTimeFormat('en', { year: 'numeric', timeZone: 'Asia/Shanghai' }).format(now);
}

export function orderYearParams(year: string): Record<string, string> {
  return year ? { order_year: year } : {};
}

export function orderYearOptions(years: number[], current = currentOrderYear()) {
  return [...new Set([Number(current), ...years])].sort((a, b) => b - a).map(String);
}
