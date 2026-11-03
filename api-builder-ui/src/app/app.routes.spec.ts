import { RoutingComponent } from './components/routing/routing.component';
import { Vflow } from 'ngx-vflow';
import { VflowMocks, VflowMockComponent } from 'ngx-vflow/testing';
import { ResourcePlanningComponent } from './components/resource-planning/resource-planning.component';
import { ProjectSelectorComponent } from './components/project-selector/project-selector.component';
import { By } from '@angular/platform-browser';
import { ProjectDocsComponent } from './components/project-docs/project-docs.component';
import { BuilderProjectsService } from './services/builder-projects.service';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { RoutingDraftsService } from './components/routing/routing-drafts.service';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { routes } from './app.routes';
import { AppComponent } from './components/app/app.component';
import { AuthService } from './services/auth.service';

// jsdom has no SVG layout or ResizeObserver; navigation uses the library's official render mocks.
beforeEach(() => {
  TestBed.overrideComponent(VflowMockComponent, { set: { template: '' } });
  TestBed.overrideComponent(ResourcePlanningComponent, { remove: { imports: [Vflow] }, add: { imports: [VflowMocks] } });
});

it('opens Projects first and keeps configuration scoped to the active project', async () => {
  TestBed.configureTestingModule({
    providers: [
      provideRouter(routes), provideHttpClient(), provideHttpClientTesting(),
      {
        provide: AuthService,
        useValue: { localPreview: true, allowed: signal(false), hasSession: () => false },
      },
    ],
  });
  const fixture = TestBed.createComponent(AppComponent);
  fixture.detectChanges();
  const router = TestBed.inject(Router);
  const http = TestBed.inject(HttpTestingController);
  await router.navigateByUrl('/api-builder');
  fixture.detectChanges();
  http.expectOne('/api/projects').flush({ projects: [{ id: 1, name: 'Default', summary: 'Existing configuration' }, { id: 2, name: 'Second', summary: 'Isolated project' }], default_project_id: 1 });
  await fixture.whenStable();
  fixture.detectChanges();
  expect(router.url).toBe('/api-builder/projects');
  expect(fixture.nativeElement.querySelector('.wo-header-nav a').textContent.trim()).toBe('Projects');
  const projects = TestBed.inject(BuilderProjectsService);
  expect(projects.activeProject()?.id).toBe(1);
  await router.navigateByUrl('/api-builder/entity-config');
  await fixture.whenStable();
  fixture.detectChanges();
  http.expectOne('/api/entities').flush({ entities: [{ id: 1, name: 'Customer' }] });
  http.expectOne('/api/entity-configurations/1').flush({ prompt: '', revision: 0, attributes: [] });
  expect(router.url).toBe('/api-builder/entity-config');
  const links = fixture.nativeElement.querySelectorAll('.wo-header-nav a');
  expect(links.length).toBe(fixture.componentInstance.headerNavigation.length);
  expect(links[1].textContent.trim()).toBe('Entity config');
  expect(links[1].getAttribute('aria-current')).toBe('page');
  expect(fixture.nativeElement.querySelector('input#entity-name')).not.toBeNull();
  links[2].click();
  await fixture.whenStable();
  fixture.detectChanges();
  http.expectOne('/api/endpoints').flush({ routes: projects.scope<RoutingDraftsService>(RoutingDraftsService, () => { throw new Error('Missing state'); }).routes(), revision: 0 });
  await fixture.whenStable();
  fixture.detectChanges();
  expect(router.url).toBe('/api-builder/routing');
  expect(links[2].getAttribute('aria-current')).toBe('page');
  expect(fixture.nativeElement.querySelector('h1').textContent.trim()).toBe('Configure your routes');
  const root = fixture.nativeElement as HTMLElement;
  const fill = (id: string, value: string) => {
    const input = root.querySelector<HTMLInputElement>(id)!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  };
  const submit = async () => {
    const routing = fixture.debugElement.query(By.directive(RoutingComponent)).componentInstance as RoutingComponent;
    routing.entity.setValue('Customer');
    root.querySelector('.routing-form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    http.expectOne('/api/endpoints').flush({ revision: 1 });
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const store = projects.scope<RoutingDraftsService>(RoutingDraftsService, () => { throw new Error("Missing project routing state"); });
  expect(store.routes().map(route => route.path)).toEqual(['list', 'get', 'create', 'update', 'delete'].map(operation => `/customer/${operation}`));
  fill('#route-path', '/customers');
  fill('#route-prompt', 'Return active customers.');
  await submit();
  expect(root.querySelectorAll('.routing-draft').length).toBe(6);
  root.querySelector<HTMLButtonElement>('[aria-label="Edit /customers"]')!.click();
  fixture.detectChanges();
  fill('#route-path', '/clients');
  await submit();
  expect(root.querySelectorAll('.routing-draft').length).toBe(6);
  expect(root.textContent).toContain('/clients');
  store.remove(store.routes()[0].id);
  store.ensureEntityRoutes([{ id: 1, name: 'Customer' }]);
  expect(store.routes().length).toBe(5);
  expect(store.routes().some(route => route.path === '/customer/list')).toBe(false);
  links[3].click();
  await fixture.whenStable();
  fixture.detectChanges();
  expect(router.url).toBe('/api-builder/authentication');
  expect(links[3].getAttribute('aria-current')).toBe('page');
  expect(root.querySelector('#auth-clientId')).not.toBeNull();
  const searchLink = root.querySelector<HTMLAnchorElement>('a[href="/api-builder/vector-search"]')!;
  searchLink.click();
  await fixture.whenStable();
  fixture.detectChanges();
  expect(router.url).toBe('/api-builder/vector-search');
  expect(searchLink.getAttribute('aria-current')).toBe('page');
  expect(root.querySelector('#search-path')).not.toBeNull();
  links[4].click();
  await fixture.whenStable();
  fixture.detectChanges();
  http.expectOne('/api/rbac').flush({ revision: 0, configuration: null });
  fixture.detectChanges();
  expect(router.url).toBe('/api-builder/rbac');
  expect(links[4].textContent.trim()).toBe('RBAC');
  expect(links[4].getAttribute('aria-current')).toBe('page');
  expect(root.querySelector('#rbac-pool')).not.toBeNull();
  await router.navigateByUrl('/api-builder/projects');
  projects.select(2);
  await router.navigateByUrl('/api-builder/routing');
  await fixture.whenStable();
  http.expectOne('/api/endpoints').flush({ routes: [], revision: 0 });
  await fixture.whenStable();
  fixture.detectChanges();
  fixture.detectChanges();
  expect(root.querySelectorAll('.routing-draft').length).toBe(0);
  await router.navigateByUrl('/api-builder/projects');
  projects.select(1);
  await router.navigateByUrl('/api-builder/routing');
  await fixture.whenStable();
  http.expectOne('/api/endpoints').flush({ routes: store.routes(), revision: 1 });
  await fixture.whenStable();
  fixture.detectChanges();
  expect(root.querySelectorAll('.routing-draft').length).toBe(5);
  expect(root.textContent).toContain('/clients');
  expect(Array.from(links).slice(-3).map(link => (link as HTMLElement).textContent?.trim())).toEqual(['Caching', 'Infrastructure', 'Load testing']);
  for (const page of ['caching', 'infrastructure']) {
    const link = root.querySelector<HTMLAnchorElement>(`a[href="/api-builder/${page}"]`)!;
    link.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(router.url).toBe(`/api-builder/${page}`);
    expect(link.getAttribute('aria-current')).toBe('page');
    if (page === 'caching') {
      http.expectOne('/api/caching').flush({ revision: 0, configuration: null, presets: [{ id: 'route', label: 'Route caching', description: 'Local cache', ttl_seconds: 60 }] });
      await fixture.whenStable();
      fixture.detectChanges();
    }
    if (page === 'infrastructure') {
      http.expectOne('/api/entities').flush({ entities: [{ id: 1, name: 'Customer' }] });
      fixture.detectChanges();
    }
    expect(root.textContent).toContain(page === 'caching' ? 'Configure caching' : 'Plan serverless infrastructure');
  }
  await router.navigateByUrl('/api-builder/load-testing');
  await fixture.whenStable();
  fixture.detectChanges();
  http.expectOne('/api/load-testing').flush({ configuration: null, run: null, report: null });
  expect(root.querySelector('h1')?.textContent).toContain('Load testing');
  expect(root.querySelector('.builder-page-titlebar .builder-page-project')?.textContent).toContain('Default');
  expect(root.querySelector('.wo-header .builder-project-name')).toBeNull();
  await router.navigateByUrl('/api-builder/observability');
  await fixture.whenStable();
  fixture.detectChanges();
  http.expectOne('/api/observability').flush({ revision: 0, configuration: { enabled: false, service_name: 'api-builder', service_namespace: 'local', environment: 'development', endpoint: 'http://127.0.0.1:4318/v1/traces', sample_ratio: 1, exclude_health: true } });
  await fixture.whenStable();
  fixture.detectChanges();
  expect(root.querySelector('h1')?.textContent).toContain('Observability & Tracing');
  expect(root.querySelector('#otel-service')).not.toBeNull();
  root.querySelector<HTMLButtonElement>('.builder-more-trigger')!.click();
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  const moreLinks = root.querySelectorAll('#builder-more-menu a');
  expect(moreLinks[0].textContent).toContain('Observability & Tracing');
  expect(moreLinks[0].getAttribute('aria-current')).toBe('page');
  expect(moreLinks[1].textContent).toContain('Documents');
  expect(root.querySelector('#builder-more-menu a[href*="swagger"]')).toBeNull();
  root.querySelector<HTMLButtonElement>('.builder-more-trigger')!.click();
  fixture.detectChanges();
  await router.navigateByUrl('/api-builder/docs');
  await fixture.whenStable();
  fixture.detectChanges();
  http.expectOne('/api/project-documents').flush({ documents: [{ id: 'overview', filename: 'README.md', category: 'Project', revision: 0, etag: 'test' }] });
  fixture.detectChanges();
  expect(root.querySelector('.tm-documents-layout')).not.toBeNull();
  expect(root.querySelector('.tm-document-item')?.textContent).toContain('Project overview and configuration summary');
  root.querySelector<HTMLButtonElement>('.builder-more-trigger')!.click();
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  expect(root.querySelector('a[href="/api-builder/docs"]')?.getAttribute('aria-current')).toBe('page');
  root.querySelector<HTMLButtonElement>('.builder-more-trigger')!.click();
  fixture.detectChanges();
  const docs = fixture.debugElement.query(By.directive(ProjectDocsComponent)).componentInstance as ProjectDocsComponent;
  await docs.selectProject('2');
  fixture.detectChanges();
  expect(projects.activeId()).toBe(2);
  expect(docs.selected()).toBeNull();
  expect(docs.documents()).toEqual([]);
  http.expectOne('/api/project-documents').flush({ documents: [] });
  fixture.detectChanges();
  expect(root.textContent).toContain('No generated documents yet.');
  expect(root.querySelector('.builder-page-project')).toBeNull();
  projects.select(1);
  await router.navigateByUrl('/api-builder/routing');
  await fixture.whenStable();
  fixture.detectChanges();
  http.expectOne('/api/endpoints').flush({ routes: store.routes(), revision: 1 });
  await fixture.whenStable();
  const selector = fixture.debugElement.query(By.directive(ProjectSelectorComponent)).componentInstance as ProjectSelectorComponent;
  await selector.choose('2');
  await fixture.whenStable();
  fixture.detectChanges();
  http.expectOne('/api/endpoints').flush({ routes: [], revision: 0 });
  await fixture.whenStable();
  fixture.detectChanges();
  expect(router.url).toBe('/api-builder/routing');
  expect(projects.activeId()).toBe(2);
  expect(root.querySelector('.routing-draft')).toBeNull();
  projects.select(1);
  http.verify();

});
