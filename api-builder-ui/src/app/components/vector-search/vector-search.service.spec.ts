import { BuilderProjectsService } from '../../services/builder-projects.service';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { VectorSearchService, SearchConfiguration } from './vector-search.service';
import { RoutingDraftsService } from '../routing/routing-drafts.service';
import { searchTypes } from '../../interfaces/route-type.interface';
import { VectorSearchComponent } from './vector-search.component';
import { safeReturnPath } from '../../services/auth.service';
import { routes } from '../../app.routes';
import { authGuard } from '../../guards/auth.guard';

const configuration: SearchConfiguration = {
  summary: 'Find matching products', source: 'Products index to confirm', fields: ['description'],
  embedding: { model: 'Confirm model', dimensions: 'Match index', chunking: 'Paragraphs' },
  ranking: 'vector', request: 'query', response: 'IDs', steps: ['Apply tenant filter'], requirements: ['Confirm source'],
};
beforeEach(() => {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const routing = TestBed.inject(RoutingDraftsService);
  for (const type of searchTypes) routing.save({ type: type.value, path: type.value === 'semantic' ? '/products/search' : '/' + type.value,
    method: 'POST', operation: null, entity: '', access: 'authenticated', prompt: '' }, null);
  routing.save({ type: 'regular', path: '/search', method: 'POST', operation: null, entity: '', access: 'authenticated', prompt: '' }, null);
});
afterEach(() => TestBed.inject(HttpTestingController).verify());

it('generates, preserves prior configuration on failed edit, retries, and removes', () => {
  const store = TestBed.inject(VectorSearchService);
  const http = TestBed.inject(HttpTestingController);
  store.form.setValue({ type: 'semantic', path: '/products/search/', prompt: 'Search descriptions' });
  store.generate();
  expect(store.busy()).toBe(true);
  expect(store.form.disabled).toBe(true);
  store.generate();
  const request = http.expectOne('/api/generate-search-configuration');
  expect(request.request.body.path).toBe('/products/search');
  request.flush({ configuration });
  expect(store.drafts().length).toBe(1);
  expect(store.busy()).toBe(false);
  const saved = store.drafts()[0];
  store.edit(saved);
  store.prompt.setValue('Changed intent');
  store.generate();
  http.expectOne('/api/generate-search-configuration').flush({}, { status: 504, statusText: 'Timeout' });
  expect(store.drafts()[0]).toEqual(saved);
  expect(store.prompt.value).toBe('Changed intent');
  expect(store.error()).toContain('timed out');
  store.generate();
  http.expectOne('/api/generate-search-configuration').flush({ configuration: { ...configuration, summary: 'Updated' } });
  expect(store.drafts().length).toBe(1);
  expect(store.drafts()[0].configuration.summary).toBe('Updated');
  store.remove(store.drafts()[0]);
  expect(store.drafts()).toEqual([]);
});

it('rejects blank/invalid intent and conflicting paths without making requests', () => {
  const store = TestBed.inject(VectorSearchService);
  store.generate();
  expect(store.form.invalid).toBe(true);
  store.form.setValue({ type: 'regular', path: '/../bad', prompt: ' ' });
  store.generate();
  expect(store.path.invalid).toBe(true);
  expect(store.prompt.invalid).toBe(true);
  store.drafts.set([{ id: 1, type: 'regular', path: '/search', prompt: 'Find', configuration }]);
  store.form.setValue({ type: 'regular', path: '/search', prompt: 'Find words' });
  store.generate();
  expect(store.path.hasError('duplicate')).toBe(true);
  TestBed.inject(HttpTestingController).expectNone('/api/generate-search-configuration');
});

it('renders minimal editor, focuses invalid input, and retains edits on navigation', () => {
  const fixture = TestBed.createComponent(VectorSearchComponent);
  document.body.appendChild(fixture.nativeElement);
  fixture.detectChanges();
  fixture.componentInstance.generate();
  fixture.detectChanges();
  expect(document.activeElement?.id).toBe('search-path');
  expect(fixture.nativeElement.querySelectorAll('input').length).toBe(0);
  expect(fixture.nativeElement.querySelector('#search-path').getAttribute('role')).toBe('combobox');
  expect(fixture.componentInstance.types.length).toBe(4);
  fixture.componentInstance.store.prompt.setValue('Retained intent');
  fixture.destroy();
  const next = TestBed.createComponent(VectorSearchComponent);
  expect(next.componentInstance.store.prompt.value).toBe('Retained intent');
  expect(safeReturnPath('/api-builder/vector-search')).toBe('/api-builder/vector-search');
  expect(routes.find(route => route.path === 'api-builder/vector-search')?.canActivate).toContain(authGuard);
});


it('filters matching routes for all types and clears a mismatched selection', () => {
  const store = TestBed.inject(VectorSearchService);
  const routing = TestBed.inject(RoutingDraftsService);
  routing.save({ path: '/ordinary', method: null, operation: null, entity: '', access: 'public', prompt: '' }, null);
  store.setPath('/products/search');
  expect(store.path.value).toBe('/products/search');
  store.setType('hybrid');
  expect(store.path.value).toBe('');
  for (const type of searchTypes) {
    store.setType(type.value);
    expect(store.routeOptions.map(option => option.value)).toEqual(
      routing.routes().filter(route => route.type === type.value).map(route => route.path));
    expect(store.routeOptions.some(option => option.value === '/ordinary')).toBe(false);
  }
  expect(store.accessLabel('/ordinary')).toBe('Public');
  store.setPath('/ordinary');
  expect(store.path.value).toBe('');
});

it('rejects removed or retyped routes before generation and while a request is pending', () => {
  const store = TestBed.inject(VectorSearchService);
  const routing = TestBed.inject(RoutingDraftsService);
  const http = TestBed.inject(HttpTestingController);
  store.form.setValue({ type: 'semantic', path: '/products/search', prompt: 'Search products' });
  store.generate();
  const request = http.expectOne('/api/generate-search-configuration');
  const source = routing.routes().find(route => route.path === '/products/search')!;
  routing.save({ ...source, type: 'hybrid' }, source.id);
  request.flush({ configuration });
  expect(store.drafts()).toEqual([]);
  expect(store.path.value).toBe('');
  expect(store.error()).toContain('type changed');
  store.path.setValue('/products/search');
  store.generate();
  expect(store.path.hasError('routeType')).toBe(true);
  http.expectNone('/api/generate-search-configuration');
  routing.remove(source.id);
  store.reconcilePath();
  expect(store.routeOptions).toEqual([]);
  expect(store.accessLabel('/products/search')).toBe('Route removed');
  expect(store.path.value).toBe('');
});


it('uses only the active project routing scope', () => {
  const projects = TestBed.inject(BuilderProjectsService);
  projects.projects.set([{ id: 101, name: 'A', summary: '' }, { id: 102, name: 'B', summary: '' }]);
  projects.select(101);
  const a = TestBed.createComponent(VectorSearchComponent);
  a.componentInstance.store.routing.save({ type: 'semantic', path: '/a/search', method: 'POST', operation: null, entity: '', access: 'authenticated', prompt: '' }, null);
  expect(a.componentInstance.store.routeOptions.map(option => option.value)).toEqual(['/a/search']);
  a.destroy();
  projects.select(102);
  const b = TestBed.createComponent(VectorSearchComponent);
  expect(b.componentInstance.store.routeOptions).toEqual([]);
  b.destroy();
  projects.select(101);
  const restored = TestBed.createComponent(VectorSearchComponent);
  expect(restored.componentInstance.store.routeOptions.map(option => option.value)).toEqual(['/a/search']);
  restored.destroy();
  localStorage.removeItem('api-builder.active-project');
});
