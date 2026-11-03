import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Vflow } from 'ngx-vflow';
import { VflowMocks, VflowMockComponent } from 'ngx-vflow/testing';
import { ResourcePlanningComponent } from './resource-planning.component';
import { BuilderProjectsService } from '../../services/builder-projects.service';

const proposal = { summary: 'Proposed async resources', services: { sqs: true, sns: false, redis: false }, recommendations: ['Review IAM'], requirements: ['Choose region'] };

describe('Infrastructure planning', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    TestBed.overrideComponent(VflowMockComponent, { set: { template: '' } });
    TestBed.overrideComponent(ResourcePlanningComponent, { remove: { imports: [Vflow] }, add: { imports: [VflowMocks] } });
  });
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('shows defaults, builds entity functions and preserves a proposal on agent failure', () => {
    const fixture = TestBed.createComponent(ResourcePlanningComponent);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/entities').flush({ entities: [{ id: 3, name: 'Customer' }] });
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('#infra-platform')?.textContent).toContain('Amazon Web Services');
    expect(root.querySelector('#infra-mode')?.textContent).toContain('Serverless deployment');
    const disabledMode = root.querySelector<HTMLButtonElement>('[role=option][aria-disabled=true]');
    expect(disabledMode?.disabled).toBe(true);
    expect(disabledMode?.textContent?.trim()).toBe('Containerized deployment');
    expect(root.textContent).toContain('Customer-3-dev-handler');
    const component = fixture.componentInstance;
    component.state.requirements = 'Process uploads asynchronously';
    component.generate();
    component.generate();
    const request = http.expectOne('/api/generate-infrastructure-plan');
    expect(request.request.body).toEqual({ platform: 'aws', deployment_mode: 'serverless', environment: 'dev', requirements: 'Process uploads asynchronously' });
    request.flush({ proposal });
    fixture.detectChanges();
    expect(component.graph().nodes.some(node => node.id === 'sqs')).toBe(true);
    component.state.environment.set('prod');
    fixture.detectChanges();
    expect(root.textContent).toContain('Proposal needs refresh');
    component.generate();
    http.expectOne('/api/generate-infrastructure-plan').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(component.state.proposal()).toEqual(proposal);
    expect(component.state.requirements).toBe('Process uploads asynchronously');
    expect(component.busy()).toBe(false);
    expect(component.error()).toContain('previous proposal are preserved');
  });

  it('retries entity failures without fabricating entity resources', () => {
    const fixture = TestBed.createComponent(ResourcePlanningComponent);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/entities').flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    fixture.componentInstance.generate();
    http.expectNone('/api/generate-infrastructure-plan');
    expect(fixture.nativeElement.textContent).toContain('Retry entities');
    fixture.componentInstance.loadEntities();
    http.expectOne('/api/entities').flush({ entities: [] });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Add entities in Entity config');
  });

  it('keeps drafts scoped by project and cancels a pending generation on departure', () => {
    const projects = TestBed.inject(BuilderProjectsService);
    projects.projects.set([{ id: 1, name: 'One', summary: '' }, { id: 2, name: 'Two', summary: '' }]);
    projects.activeId.set(1);
    const http = TestBed.inject(HttpTestingController);
    const first = TestBed.createComponent(ResourcePlanningComponent);
    http.expectOne('/api/entities').flush({ entities: [] });
    first.componentInstance.state.requirements = 'One only';
    first.componentInstance.state.proposal.set(proposal);
    first.componentInstance.generate();
    const pending = http.expectOne('/api/generate-infrastructure-plan');
    first.destroy();
    expect(pending.cancelled).toBe(true);
    projects.activeId.set(2);
    const second = TestBed.createComponent(ResourcePlanningComponent);
    http.expectOne('/api/entities').flush({ entities: [] });
    expect(second.componentInstance.state.requirements).toBe('');
    second.destroy();
    projects.activeId.set(1);
    const restored = TestBed.createComponent(ResourcePlanningComponent);
    http.expectOne('/api/entities').flush({ entities: [] });
    expect(restored.componentInstance.state.requirements).toBe('One only');
    expect(restored.componentInstance.busy()).toBe(false);
    expect(restored.componentInstance.proposalNeedsRefresh()).toBe(true);
    expect(restored.componentInstance.changedSinceProposal).toBe(true);
  });
});
