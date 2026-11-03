import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CONNECTION_BROWSER, DEFAULT_CONNECTION, LocalConnectionService } from './local-connection.service';
import { localConnectionInterceptor } from '../interceptors/local-connection.interceptor';
import { projectInterceptor } from '../interceptors/project.interceptor';
import { BuilderProjectsService } from './builder-projects.service';

function setup(saved: string | null = null) {
  const browser = { origin: 'http://localhost:4200', hostname: 'localhost', protocol: 'http:',
    read: () => saved, write: vi.fn(), reload: vi.fn() };
  TestBed.configureTestingModule({ providers: [
    provideHttpClient(withInterceptors([projectInterceptor, localConnectionInterceptor])),
    provideHttpClientTesting(), { provide: CONNECTION_BROWSER, useValue: browser },
  ] });
  return { browser, service: TestBed.inject(LocalConnectionService), http: TestBed.inject(HttpTestingController) };
}

it('keeps default proxy routes and rejects corrupt or invalid saved values', () => {
  const { service, http } = setup('{"direct":true,"port":70000}');
  expect(service.settings()).toEqual(DEFAULT_CONNECTION);
  expect(service.url('/api/projects')).toBe('/api/projects');
  expect(service.swaggerUrl(12)).toBe('/swagger/index.html?project=12');
  expect(() => service.normalize({ direct: true, port: 2.5 })).toThrow('whole port');
  expect(() => service.normalize({ direct: true, port: '5001' })).toThrow('whole port');
  http.verify();
});

it('routes owned APIs with project context and cookies without rewriting unrelated requests', () => {
  const { service, http } = setup('{"direct":true,"port":5001}');
  const projects = TestBed.inject(BuilderProjectsService);
  projects.projects.set([{ id: 8, name: 'Sample', summary: '' }]);
  projects.activeId.set(8);
  const client = TestBed.inject(HttpClient);
  client.get('/api/entities').subscribe();
  const request = http.expectOne('http://localhost:5001/api/entities');
  expect(request.request.withCredentials).toBe(true);
  expect(request.request.headers.get('X-Project-ID')).toBe('8');
  request.flush({ entities: [] });
  for (const url of ['/api/session', '/api/projects-other', 'https://example.com/api/projects']) {
    client.get(url).subscribe();
    http.expectOne(url).flush({});
  }
  expect(service.swaggerUrl(8)).toBe('/swagger/index.html?project=8&port=5001');
  http.verify();
});

it('checks a candidate independently and saves only a verified ready backend', async () => {
  const { service, browser, http } = setup('{"direct":true,"port":5001}');
  const candidate = { direct: true, port: 5002 };
  const failed = service.apply(candidate);
  http.expectOne('http://localhost:5002/api/health').flush({ status: 'ok', service: 'something-else' });
  await expect(failed).rejects.toThrow('did not identify');
  expect(browser.write).not.toHaveBeenCalled();
  expect(service.settings().port).toBe(5001);
  const saving = service.apply(candidate);
  const check = http.expectOne('http://localhost:5002/api/health');
  expect(check.request.withCredentials).toBe(true);
  expect(check.request.headers.has('X-Project-ID')).toBe(false);
  check.flush({ status: 'ok', service: 'api-builder' });
  await saving;
  expect(browser.write).toHaveBeenCalledWith(JSON.stringify(candidate));
  expect(browser.reload).toHaveBeenCalledOnce();
  expect(service.settings()).toEqual(candidate);
  http.verify();
});

it('preserves current settings and avoids reload on failed checks or blocked storage', async () => {
  const { service, browser, http } = setup();
  const disconnected = service.apply({ direct: true, port: 5002 });
  http.expectOne('http://localhost:5002/api/health').error(new ProgressEvent('error'));
  await expect(disconnected).rejects.toBeDefined();
  expect(browser.write).not.toHaveBeenCalled();
  browser.write.mockImplementation(() => { throw new Error('blocked'); });
  const saving = service.apply({ direct: true, port: 5002 });
  http.expectOne('http://localhost:5002/api/health').flush({ status: 'ok', service: 'api-builder' });
  await expect(saving).rejects.toThrow('Allow site storage');
  expect(browser.reload).not.toHaveBeenCalled();
  expect(service.settings()).toEqual(DEFAULT_CONNECTION);
  http.verify();
});

it('refuses direct localhost mode from a hosted site', () => {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(),
    { provide: CONNECTION_BROWSER, useValue: { origin: 'https://example.com', hostname: 'example.com', protocol: 'https:',
      read: () => '{"direct":true,"port":5001}', write: vi.fn(), reload: vi.fn() } },
  ] });
  const service = TestBed.inject(LocalConnectionService);
  expect(service.canConnectDirectly).toBe(false);
  expect(service.settings()).toEqual(DEFAULT_CONNECTION);
  expect(() => service.normalize({ direct: true, port: 5001 })).toThrow('localhost');
});


it.each([false, true])('sends project context for every observability action in direct mode %s', (direct) => {
  const { http } = setup(JSON.stringify({ direct, port: 5001 }));
  const projects = TestBed.inject(BuilderProjectsService);
  projects.projects.set([{ id: 8, name: 'Sample', summary: '' }]);
  projects.activeId.set(8);
  const client = TestBed.inject(HttpClient);
  for (const [method, path] of [['GET', '/api/observability'], ['PUT', '/api/observability'], ['POST', '/api/observability/test']]) {
    client.request(method, path, { body: method === 'GET' ? undefined : { revision: 1 } }).subscribe();
    const request = http.expectOne(direct ? `http://localhost:5001${path}` : path);
    expect(request.request.method).toBe(method);
    expect(request.request.headers.get('X-Project-ID')).toBe('8');
    expect(request.request.withCredentials).toBe(direct);
    request.flush({});
  }
  client.get('/api/observability-other').subscribe();
  const unrelated = http.expectOne('/api/observability-other');
  expect(unrelated.request.headers.has('X-Project-ID')).toBe(false);
  unrelated.flush({});
  http.verify();
});

it('blocks observability requests without an active project', () => {
  const { http } = setup();
  let status = 0;
  TestBed.inject(HttpClient).get('/api/observability').subscribe({ error: error => status = error.status });
  expect(status).toBe(400);
  http.expectNone('/api/observability');
  http.verify();
});
