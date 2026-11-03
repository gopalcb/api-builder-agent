import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { RbacComponent } from './rbac.component';
import { emptyConfiguration } from './rbac.service';

function setup() {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const fixture = TestBed.createComponent(RbacComponent);
  const http = TestBed.inject(HttpTestingController);
  http.expectOne('/api/rbac').flush({ revision: 0, configuration: null });
  fixture.detectChanges();
  return { fixture, component: fixture.componentInstance, http };
}

it('imports routes, requires missing methods, saves a reviewed matrix and preserves navigation drafts', () => {
  const { fixture, component, http } = setup();
  component.routing.save({ path: '/orders', method: null, operation: null, entity: '', access: 'authenticated', prompt: '' }, null);
  component.importDrafts();
  component.save();
  expect(component.error()).toContain('HTTP method');
  http.expectNone('/api/rbac');
  component.setMethod(0, 'GET');
  component.roleName.setValue('reader'); component.groupName.setValue('readers'); component.addRole();
  component.toggleGrant('reader', 'GET /orders', true);
  component.save();
  const request = http.expectOne('/api/rbac');
  expect(request.request.method).toBe('PUT');
  expect(request.request.body.configuration.grants).toEqual([{ role: 'reader', route: 'GET /orders' }]);
  request.flush({ revision: 1, configuration: request.request.body.configuration });
  expect(component.dirty()).toBe(false);
  expect(component.canExport()).toBe(true);
  component.setIdentity('client_id', 'abc123');
  component.roleName.setValue('unfinished'); component.groupName.setValue('unfinished-group');
  component.error.set('Preserve this error');
  fixture.destroy();
  const next = TestBed.createComponent(RbacComponent);
  expect(next.componentInstance.configuration().identity.client_id).toBe('abc123');
  expect(next.componentInstance.dirty()).toBe(true);
  expect(next.componentInstance.roleName.value).toBe('unfinished');
  expect(next.componentInstance.groupName.value).toBe('unfinished-group');
  expect(next.componentInstance.error()).toBe('Preserve this error');
  http.expectNone('/api/rbac');
  next.destroy(); http.verify();
});

it('preserves edits on save conflicts and generation failure, and distinguishes an unsaved proposal', () => {
  const { fixture, component, http } = setup();
  const configuration = emptyConfiguration();
  configuration.routes = [{ method: 'GET', path: '/orders', key: 'GET /orders', access: 'authenticated' }];
  component.change(configuration);
  component.prompt.setValue('Readers can read orders');
  component.generate();
  http.expectOne('/api/rbac/generate').flush({ error: 'Generation timed out' }, { status: 504, statusText: 'Timeout' });
  expect(component.configuration()).toEqual(configuration);
  expect(component.busy()).toBe('');
  component.generate();
  http.expectOne('/api/rbac/generate').flush({ revision: 0, configuration: { ...configuration, notes: 'Proposal' } });
  expect(component.dirty()).toBe(true);
  expect(component.canExport()).toBe(false);
  component.save();
  http.expectOne('/api/rbac').flush({ error: 'Conflict' }, { status: 409, statusText: 'Conflict' });
  expect(component.error()).toContain('edits are preserved');
  expect(component.configuration().notes).toBe('Proposal');
  component.requestReload();
  expect(component.reloadRequested()).toBe(true);
  fixture.destroy(); http.verify();
});

it('blocks export after source drift and cleans up removed role grants', () => {
  const { fixture, component, http } = setup();
  component.routing.save({ path: '/orders', method: 'GET', operation: 'list', entity: '', access: 'authenticated', prompt: '' }, null);
  component.importDrafts();
  component.roleName.setValue('reader'); component.groupName.setValue('readers'); component.addRole();
  component.toggleGrant('reader', 'GET /orders', true);
  component.removeRole('reader');
  expect(component.configuration().grants).toEqual([]);
  component.routing.save({ path: '/new', method: 'GET', operation: 'list', entity: '', access: 'authenticated', prompt: '' }, null);
  expect(component.sourceChanged()).toBe(true);
  component.save();
  http.expectNone('/api/rbac');
  expect(component.error()).toContain('Source drafts changed');
  fixture.destroy(); http.verify();
});

it('shows load recovery and actual preview results without claiming AWS enforcement', () => {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const fixture = TestBed.createComponent(RbacComponent);
  const component = fixture.componentInstance;
  const http = TestBed.inject(HttpTestingController);
  http.expectOne('/api/rbac').flush({}, { status: 500, statusText: 'Failure' });
  fixture.detectChanges();
  expect(fixture.nativeElement.textContent).toContain('Retry loading');
  component.load();
  http.expectOne('/api/rbac').flush({ revision: 0, configuration: null });
  component.setPreviewRoute('GET /unknown');
  component.preview();
  http.expectOne('/api/rbac/preview').flush({ decision: 'deny', public: false, mode: 'configuration-preview' });
  expect(component.decision()).toContain('Deny');
  expect(component.decision()).toContain('not an AWS decision');
  fixture.destroy(); http.verify();
});
