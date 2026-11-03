/** Shared route classifications; regular is the backend's keyword-search identifier. */
export type SearchRouteType = 'embedding' | 'semantic' | 'hybrid' | 'regular';
export type RouteType = 'authenticated' | 'public' | SearchRouteType;

export const searchTypes = [
  { value: 'embedding', label: 'Vector embedding', hint: 'Turn source text into vectors for indexing.', placeholder: 'Embed product names and descriptions. Keep product IDs and update changed records.' },
  { value: 'semantic', label: 'Semantic search', hint: 'Find results by meaning using indexed vectors.', placeholder: 'Find products by meaning. Search descriptions and return the 10 most relevant results.' },
  { value: 'hybrid', label: 'Hybrid search', hint: 'Combine keyword and semantic results.', placeholder: 'Combine exact product keywords with meaning. Support category filters and return 10 results.' },
  { value: 'regular', label: 'Keyword search', hint: 'Match words and phrases with full-text search. No embeddings.', placeholder: 'Search product names and descriptions by keyword. Support category filters.' },
] satisfies { value: SearchRouteType; label: string; hint: string; placeholder: string }[];

export const routeTypes = [
  { value: 'authenticated', label: 'Authenticated' },
  { value: 'public', label: 'Public' },
  ...searchTypes.map(({ value, label }) => ({ value, label })),
] satisfies { value: RouteType; label: string }[];

export function isSearchRouteType(type: string): type is SearchRouteType {
  return searchTypes.some(option => option.value === type);
}
