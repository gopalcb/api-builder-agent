import { vi } from 'vitest';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { LoadTestingComponent } from './load-testing.component';
import { BuilderProjectsService } from '../../services/builder-projects.service';

const configuration = { prompt: 'Test all read endpoints', host: 'http://127.0.0.1:8080', users: 2, spawnRate: 1, duration: 5, waitMin: 0, waitMax: 1 };
const report = { id: 'saved', status: 'passed', startedAt: '2026-11-02T10:00:00Z', completedAt: '2026-11-02T10:00:05Z', codeUpdated: false,
  configuration, endpoints: ['/product/list'], metrics: { requests: 42, failures: 0, p95: 12, rps: 8.4 },
  statistics: [{ path: '/product/list', requests: 42, failures: 0, average: 9, p95: 12, rps: 8.4 }] };

function setup() {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const projects = TestBed.inject(BuilderProjectsService);
  projects.projects.set([{ id: 91, name: 'First', summary: '' }, { id: 92, name: 'Second', summary: '' }]);
  projects.select(91);
  const fixture = TestBed.createComponent(LoadTestingComponent);
  const http = TestBed.inject(HttpTestingController);
  return { fixture, http, projects, component: fixture.componentInstance };
}

afterEach(() => vi.useRealTimers());

it('loads the latest project report and real date with no mock metrics', () => {
  const { fixture, http } = setup();
  const request = http.expectOne('/api/load-testing');
  expect(request.request.headers.get('X-Project-ID')).toBe('91');
  request.flush({ configuration, run: report, report });
  fixture.detectChanges();
  expect(fixture.nativeElement.textContent).toContain('42');
  expect(fixture.nativeElement.textContent).toContain('Nov 2, 2026');
  expect(fixture.nativeElement.textContent).toContain('/product/list');
  expect(fixture.nativeElement.textContent).not.toContain('Mock report');
  expect(fixture.nativeElement.textContent).toContain('Run load testing');
  http.verify();
});

it('starts, polls and preserves project context until destruction', () => {
  vi.useFakeTimers();
  const { fixture, http, component, projects } = setup();
  http.expectOne('/api/load-testing').flush({ configuration, run: report, report });
  component.start();
  component.start();
  const post = http.expectOne('/api/load-testing');
  expect(post.request.method).toBe('POST');
  expect(post.request.body).toEqual(configuration);
  projects.select(92);
  post.flush({ run: { ...report, id: 'new', status: 'running' } });
  expect(component.report()?.id).toBe('saved');
  expect(component.running()).toBe(true);
  vi.advanceTimersByTime(1000);
  const poll = http.expectOne('/api/load-testing');
  expect(poll.request.headers.get('X-Project-ID')).toBe('91');
  poll.flush({ configuration, run: report, report: { ...report, id: 'new' } });
  expect(component.running()).toBe(false);
  expect(component.report()?.id).toBe('new');
  component.load();
  http.expectOne('/api/load-testing').flush({ configuration, run: { ...report, status: 'running' }, report });
  fixture.destroy();
  vi.advanceTimersByTime(2000);
  http.expectNone('/api/load-testing');
  http.verify();
});

it('shows empty, validation and server failures without fabricated results', () => {
  const { fixture, http, component } = setup();
  http.expectOne('/api/load-testing').flush({ configuration: null, run: null, report: null });
  fixture.detectChanges();
  expect(fixture.nativeElement.textContent).toContain('No load testing record yet');
  component.state.configuration.users = 101;
  component.start();
  expect(component.error()).toContain('100');
  http.expectNone('/api/load-testing');
  component.state.configuration.users = 2;
  component.start();
  http.expectOne('/api/load-testing').flush({ error: 'Docker is unavailable' }, { status: 500, statusText: 'Error' });
  expect(component.running()).toBe(false);
  expect(component.report()).toBeNull();
  expect(component.error()).toBe('Docker is unavailable');
  http.verify();
});

it('resumes a running saved job on initial page load', () => {
  vi.useFakeTimers();
  const { fixture, http, component } = setup();
  http.expectOne('/api/load-testing').flush({ configuration, run: { ...report, status: 'running' }, report });
  expect(component.running()).toBe(true);
  vi.advanceTimersByTime(1500);
  http.expectOne('/api/load-testing').flush({ configuration, run: report, report });
  expect(component.running()).toBe(false);
  fixture.destroy();
  http.verify();
});


it('retries initial loading without losing saved settings, then preserves edited drafts', () => {
  const { fixture, http, component } = setup();
  http.expectOne('/api/load-testing').flush({}, { status: 503, statusText: 'Unavailable' });
  expect(component.ready()).toBe(false);
  component.start();
  http.expectNone('/api/load-testing');
  component.load();
  http.expectOne('/api/load-testing').flush({ configuration, run: report, report });
  expect(component.state.configuration).toEqual(configuration);
  expect(component.ready()).toBe(true);
  component.state.configuration = { ...configuration, users: 7 };
  component.load();
  http.expectOne('/api/load-testing').flush({ configuration, run: report, report });
  expect(component.state.configuration.users).toBe(7);
  fixture.destroy();
  http.verify();
});

it('shows interrupted current status and older report without inventing absent metrics', () => {
  const { fixture, http, component } = setup();
  http.expectOne('/api/load-testing').flush({ configuration, run: { ...report, id: 'interrupted', status: 'interrupted' }, report });
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelector('.load-badge').textContent).toContain('interrupted');
  expect(fixture.nativeElement.textContent).toContain('previous saved report');
  component.load();
  http.expectOne('/api/load-testing').flush({ configuration, run: { ...report, status: 'failed' }, report: { ...report, status: 'failed', metrics: {}, statistics: [] } });
  fixture.detectChanges();
  expect(fixture.nativeElement.textContent).toContain('No measured requests');
  expect(fixture.nativeElement.querySelector('.load-metrics')).toBeNull();
  fixture.destroy();
  http.verify();
});
