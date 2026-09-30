export async function loadAllPages<T>(
  fetchPage: (params: { limit: number; offset: number }) => Promise<{ items: T[]; total: number }>,
  onPage?: (page: { items: T[]; total: number }) => void,
  isCurrent: () => boolean = () => true,
) {
  const items: T[] = [];
  let total = 0;
  do {
    if (!isCurrent()) break;
    const page = await fetchPage({ limit: 500, offset: items.length });
    if (!isCurrent()) break;
    total = page.total;
    if (!page.items.length && items.length < total) throw new Error('数据加载不完整，请刷新重试');
    items.push(...page.items);
    onPage?.({ items: [...items], total });
  } while (items.length < total);
  return { items, total };
}
