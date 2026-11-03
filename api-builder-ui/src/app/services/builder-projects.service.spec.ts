import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { BuilderProjectsService } from './builder-projects.service';
import { projectGuard } from '../guards/project.guard';
import { projectInterceptor } from '../interceptors/project.interceptor';
import { HttpClient } from '@angular/common/http';

it('blocks configuration without a catalog and restores valid selection with scoped requests', async () => {
  localStorage.setItem('api-builder.active-project', '999');
  TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient(withInterceptors([projectInterceptor])), provideHttpClientTesting()] });
  const http = TestBed.inject(HttpTestingController);
  const store = TestBed.inject(BuilderProjectsService);
  const blocked = TestBed.runInInjectionContext(() => projectGuard({} as never, {} as never));
  http.expectOne('/api/projects').flush({}, { status: 503, statusText: 'Unavailable' });
  expect(TestBed.inject(Router).serializeUrl(await blocked as never)).toBe('/api-builder/projects');
  expect(store.activeProject()).toBeNull();
  const loading = store.load();
  http.expectOne('/api/projects').flush({ projects: [{ id: 1, name: 'Default', summary: 'Default project' }], default_project_id: 1 });
  await loading;
  expect(store.activeProject()?.id).toBe(1);
  const saving = store.create('Second', 'Another project');
  http.expectOne('/api/projects').flush({ project: { id: 2, name: 'Second', summary: 'Another project' } });
  expect(await saving).toBe(true);
  expect(store.activeProject()?.id).toBe(1);
  expect(store.orderedProjects().map(project => project.id)).toEqual([1, 2]);
  store.select(2);
  expect(store.orderedProjects().map(project => project.id)).toEqual([2, 1]);
  expect(store.projects().map(project => project.id)).toEqual([1, 2]);
  TestBed.inject(HttpClient).get('/api/entities').subscribe();
  const request = http.expectOne('/api/entities');
  expect(request.request.headers.get('X-Project-ID')).toBe('2');
  request.flush({ entities: [] });
  http.verify();
  localStorage.removeItem('api-builder.active-project');
});

it('scopes infrastructure generation to the active project and rejects requests without one', () => {
  TestBed.configureTestingModule({ providers: [provideHttpClient(withInterceptors([projectInterceptor])), provideHttpClientTesting()] });
  const http = TestBed.inject(HttpTestingController);
  const client = TestBed.inject(HttpClient);
  const projects = TestBed.inject(BuilderProjectsService);
  let status = 0;
  client.post('/api/generate-infrastructure-plan', {}).subscribe({ error: error => status = error.status });
  expect(status).toBe(400);
  http.expectNone('/api/generate-infrastructure-plan');
  projects.projects.set([{ id: 3, name: 'First', summary: '' }, { id: 7, name: 'Second', summary: '' }]);
  for (const id of [3, 7]) {
    projects.activeId.set(id);
    client.post('/api/generate-infrastructure-plan', { platform: 'aws', deployment_mode: 'serverless', environment: 'dev', requirements: '' }).subscribe();
    const pending = http.expectOne('/api/generate-infrastructure-plan');
    expect(pending.request.headers.get('X-Project-ID')).toBe(String(id));
    pending.flush({ proposal: {} });
  }
  http.verify();
});
