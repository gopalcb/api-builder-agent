import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { RoutingComponent } from './routing.component';
import { routeTypes, searchTypes } from '../../interfaces/route-type.interface';

it('creates and edits each route type without conflating type and access', async () => {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const fixture = TestBed.createComponent(RoutingComponent);
  const component = fixture.componentInstance;
  const http = TestBed.inject(HttpTestingController);
  http.expectOne('/api/endpoints').flush({ routes: [], revision: 0 });
  await fixture.whenStable();
  for (const type of routeTypes) {
    component.entity.setValue('Product');
    component.setType(type.value);
    component.path.setValue('/' + type.value);
    const saving = component.saveRoute();
    http.expectOne('/api/endpoints').flush({ revision: 1 });
    await saving;
    const draft = component.routes().at(-1)!;
    expect(draft.type).toBe(type.value);
    expect(draft.access).toBe(type.value === 'public' ? 'public' : 'authenticated');
    component.editRoute(draft);
    expect(component.routeType.value).toBe(type.value);
    component.cancelEdit();
  }
  const publicRoute = component.routes().find(route => route.type === 'public')!;
  component.editRoute(publicRoute);
  component.setType('semantic');
  const saving = component.saveRoute();
  http.expectOne('/api/endpoints').flush({ revision: 2 });
  await saving;
  const converted = component.routes().find(route => route.id === publicRoute.id)!;
  expect(converted.type).toBe('semantic');
  expect(converted.access).toBe('public');
  expect(converted.method).toBe('POST');
  component.store.ensureEntityRoutes([{ id: 1, name: 'Customer' }]);
  expect(component.routes().filter(route => route.entity === 'Customer').every(route => route.type === 'authenticated')).toBe(true);
  expect(searchTypes.find(type => type.value === 'regular')?.label).toBe('Keyword search');
  fixture.detectChanges();
  expect(fixture.nativeElement.textContent).toContain('Route type');
  expect(fixture.nativeElement.textContent).not.toContain('Access policy');
  fixture.destroy(); http.verify();
});


it('restores persisted routes after failure without losing the edit form', async () => {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const fixture = TestBed.createComponent(RoutingComponent);
  const component = fixture.componentInstance;
  const http = TestBed.inject(HttpTestingController);
  http.expectOne('/api/endpoints').flush({ routes: [], revision: 0, entities: ['Product'] });
  await fixture.whenStable();
  component.entity.setValue('Product');
  component.operation.setValue('sell');
  component.path.setValue('/product/sell');
  const saving = component.saveRoute();
  expect(component.form.disabled).toBe(true);
  http.expectOne('/api/endpoints').flush({}, { status: 500, statusText: 'Error' });
  await saving;
  expect(component.routes()).toEqual([]);
  expect(component.path.value).toBe('/product/sell');
  expect(component.form.enabled).toBe(true);
  const retry = component.saveRoute();
  http.expectOne('/api/endpoints').flush({ revision: 1 });
  await retry;
  expect(component.routes()).toHaveLength(1);
  expect(component.routes()[0].operation).toBe('sell');
  fixture.destroy();
  http.verify();
});
