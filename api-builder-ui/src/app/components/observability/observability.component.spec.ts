import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { BuilderProjectsService } from '../../services/builder-projects.service';
import { ObservabilityComponent, ObservabilityConfiguration } from './observability.component';

const defaults: ObservabilityConfiguration = { enabled: false, service_name: 'api-builder', service_namespace: 'local', environment: 'development', endpoint: 'http://127.0.0.1:4318/v1/traces', sample_ratio: 1, exclude_health: true };

beforeEach(() => TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }));

it('saves and tests only a saved enabled revision, reports real probe failure and permits retry', async () => {
  const fixture = TestBed.createComponent(ObservabilityComponent);
  const component = fixture.componentInstance;
  const http = TestBed.inject(HttpTestingController);
  http.expectOne('/api/observability').flush({ revision: 0, configuration: defaults });
  await fixture.whenStable();
  fixture.detectChanges();
  expect(component.canTest).toBe(false);
  component.state.configuration.enabled = true;
  await component.testTrace();
  http.expectNone('/api/observability/test');
  const saving = component.save();
  const request = http.expectOne('/api/observability');
  expect(request.request.method).toBe('PUT');
  expect(request.request.body.revision).toBe(0);
  request.flush({ revision: 1, configuration: request.request.body.configuration });
  await saving;
  expect(component.canTest).toBe(true);
  const testing = component.testTrace();
  expect(component.canTest).toBe(false);
  const probe = http.expectOne('/api/observability/test');
  expect(probe.request.body).toEqual({ revision: 1 });
  probe.flush({ error: 'Unavailable' }, { status: 502, statusText: 'Bad Gateway' });
  await testing;
  expect(component.traceId()).toBe('');
  expect(component.error()).toContain('could not be exported');
  const retry = component.testTrace();
  http.expectOne('/api/observability/test').flush({ trace_id: '0123456789abcdef0123456789abcdef', message: 'Accepted' });
  await retry;
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelector('a[href*="/trace/"]').href).toBe('http://127.0.0.1:16686/trace/0123456789abcdef0123456789abcdef');
  component.state.configuration.sample_ratio = 0.5;
  expect(component.canTest).toBe(false);
  await component.testTrace();
  http.expectNone('/api/observability/test');
  http.verify();
});

it('preserves project drafts after a conflict and requires explicit discard before reload', async () => {
  const fixture = TestBed.createComponent(ObservabilityComponent);
  const component = fixture.componentInstance;
  const http = TestBed.inject(HttpTestingController);
  http.expectOne('/api/observability').flush({ revision: 1, configuration: defaults });
  await fixture.whenStable();
  component.state.configuration.service_name = 'edited';
  const saving = component.save();
  http.expectOne('/api/observability').flush({}, { status: 409, statusText: 'Conflict' });
  await saving;
  expect(component.state.configuration.service_name).toBe('edited');
  expect(component.error()).toContain('changed elsewhere');
  fixture.destroy();
  const returning = TestBed.createComponent(ObservabilityComponent).componentInstance;
  expect(returning.state.configuration.service_name).toBe('edited');
  http.expectNone('/api/observability');
  await returning.load();
  expect(returning.discard()).toBe(true);
  http.expectNone('/api/observability');
  const reloading = returning.load(true);
  http.expectOne('/api/observability').flush({ revision: 2, configuration: defaults });
  await reloading;
  expect(returning.dirty).toBe(false);
  expect(returning.state.revision).toBe(2);
  http.verify();
});

it('retries failed loading and focuses invalid local endpoint without sending it', async () => {
  const fixture = TestBed.createComponent(ObservabilityComponent);
  const component = fixture.componentInstance;
  const http = TestBed.inject(HttpTestingController);
  http.expectOne('/api/observability').flush({}, { status: 500, statusText: 'Failed' });
  await fixture.whenStable();
  fixture.detectChanges();
  expect(component.state.loaded).toBe(false);
  expect(fixture.nativeElement.querySelector('fieldset').disabled).toBe(true);
  const retry = component.load();
  http.expectOne('/api/observability').flush({ revision: 0, configuration: defaults });
  await retry;
  fixture.detectChanges();
  for (const endpoint of ['https://example.com/v1/traces', 'http://127.0.0.1:0/v1/traces', 'http://127.0.0.1:4318/v1/traces?key=secret']) {
    component.state.configuration.endpoint = endpoint;
    await component.save();
    expect(component.invalidField()).toBe('otel-endpoint');
    http.expectNone('/api/observability');
  }
  component.state.configuration.endpoint = defaults.endpoint;
  component.state.configuration.sample_ratio = -1;
  await component.save();
  expect(component.invalidField()).toBe('otel-sampling');
  component.state.configuration.sample_ratio = 1;
  component.state.configuration.service_name = '1invalid';
  await component.save();
  expect(component.invalidField()).toBe('otel-service');
  http.verify();
});

it('isolates unsaved configuration between projects', async () => {
  const store = TestBed.inject(BuilderProjectsService);
  const http = TestBed.inject(HttpTestingController);
  store.projects.set([{ id: 1, name: 'One', summary: '' }, { id: 2, name: 'Two', summary: '' }]);
  store.select(1);
  const first = TestBed.createComponent(ObservabilityComponent);
  http.expectOne('/api/observability').flush({ revision: 0, configuration: defaults });
  await first.whenStable();
  first.componentInstance.state.configuration.service_name = 'draft-one';
  first.destroy();
  store.select(2);
  const second = TestBed.createComponent(ObservabilityComponent);
  http.expectOne('/api/observability').flush({ revision: 0, configuration: defaults });
  await second.whenStable();
  expect(second.componentInstance.state.configuration.service_name).toBe('api-builder');
  store.select(1);
  const restored = TestBed.createComponent(ObservabilityComponent);
  expect(restored.componentInstance.state.configuration.service_name).toBe('draft-one');
  http.verify();
});
