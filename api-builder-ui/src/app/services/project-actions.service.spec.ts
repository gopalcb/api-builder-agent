import { vi } from 'vitest';
import { ProjectBuildActionsComponent } from '../components/project-build-actions/project-build-actions.component';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ProjectActionsService } from './project-actions.service';
import { BuilderProjectsService } from './builder-projects.service';
import { ProjectActivitiesService } from './project-activities.service';

it('tracks real pending, successful and failed actions separately by project and records outcomes', async () => {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const http = TestBed.inject(HttpTestingController);
  const actions = TestBed.inject(ProjectActionsService);
  const projects = TestBed.inject(BuilderProjectsService);
  const activities = TestBed.inject(ProjectActivitiesService);
  const first = { id: 91, name: 'First', summary: 'Test' };
  const second = { id: 92, name: 'Second', summary: 'Test' };
  projects.projects.set([first, second]);
  projects.select(91);
  const fixture = TestBed.createComponent(ProjectBuildActionsComponent);
  fixture.componentInstance.shownProjectId = first.id;
  const pending = actions.run(first, 'test');
  expect(actions.results()[91].status).toBe('running');
  expect(actions.busy()).toBe(true);
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelector('progress')).not.toBeNull();
  await actions.run(second, 'test');
  http.expectNone('/api/projects/92/test');
  http.expectOne('/api/projects/91/test').flush({ project: first, message: 'Checks passed.' });
  await pending;
  expect(actions.results()[91].status).toBe('success');
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelector('progress')).toBeNull();
  expect(fixture.nativeElement.textContent).toContain('success');
  projects.select(92);
  fixture.componentInstance.shownProjectId = second.id;
  const failing = actions.run(second, 'build');
  http.expectOne(request => request.url.includes('/build/logs/')).flush({ entries: [], cursor: 0, more: false });
  http.expectOne('/api/projects/92/build').flush({ error: 'Build failed.' }, { status: 500, statusText: 'Error' });
  await failing;
  expect(actions.results()[92]).toMatchObject({ status: 'failure', message: 'Build failed.' });
  expect(actions.results()[91].status).toBe('success');
  expect(actions.busy()).toBe(false);
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('Build failed.');
  expect(activities.entries().filter(item => item.projectId === 92).map(item => item.status).slice(0, 2)).toEqual(['failure', 'running']);
  http.verify();
});


it('dismisses completed test results after five seconds without hiding a newer running test', async () => {
  vi.useFakeTimers();
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const actions = TestBed.inject(ProjectActionsService);
  const http = TestBed.inject(HttpTestingController);
  const project = { id: 93, name: 'Timed', summary: 'Test' };
  try {
    const first = actions.run(project, 'test');
    http.expectOne('/api/projects/93/test').flush({ project, message: 'Passed' });
    await first;
    vi.advanceTimersByTime(4999);
    expect(actions.results()[93].status).toBe('success');
    vi.advanceTimersByTime(1);
    expect(actions.results()[93]).toBeUndefined();
    const failing = actions.run(project, 'test');
    http.expectOne('/api/projects/93/test').flush({}, { status: 500, statusText: 'Error' });
    await failing;
    vi.advanceTimersByTime(5000);
    expect(actions.results()[93]).toBeUndefined();
    const completed = actions.run(project, 'test');
    http.expectOne('/api/projects/93/test').flush({ project, message: 'Passed' });
    await completed;
    vi.advanceTimersByTime(4000);
    const rerun = actions.run(project, 'test');
    vi.advanceTimersByTime(2000);
    expect(actions.results()[93].status).toBe('running');
    http.expectOne('/api/projects/93/test').flush({ project, message: 'Passed again' });
    await rerun;
    vi.advanceTimersByTime(5000);
    expect(actions.results()[93]).toBeUndefined();
    http.verify();
  } finally { vi.useRealTimers(); }
});

it('drains final build logs and stops polling after completion', async () => {
  vi.useFakeTimers();
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const actions = TestBed.inject(ProjectActionsService);
  const http = TestBed.inject(HttpTestingController);
  const project = { id: 94, name: 'Logs', summary: 'Test' };
  const pending = actions.run(project, 'build');
  const build = http.expectOne('/api/projects/94/build');
  expect(build.request.body.run_id).toMatch(/^[a-f0-9-]{36}$/);
  http.expectOne(request => request.url.includes('/build/logs/')).flush({ entries: [{ event: 'project.build.started' }], cursor: 10, more: false });
  build.flush({ project, message: 'Built.' });
  await pending;
  vi.advanceTimersByTime(750);
  http.expectOne(request => request.url.endsWith('?cursor=10')).flush({ entries: [{ event: 'project.build.completed' }], cursor: 20, more: true });
  vi.advanceTimersByTime(1);
  http.expectOne(request => request.url.endsWith('?cursor=20')).flush({ entries: [], cursor: 20, more: false });
  vi.advanceTimersByTime(3000);
  expect(actions.buildLogs().map(entry => entry.event)).toEqual(['project.build.started', 'project.build.completed']);
  http.verify();
  vi.useRealTimers();
});

it('renders the requested workflow steps from build milestones and completes them on success', () => {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const actions = TestBed.inject(ProjectActionsService);
  const projects = TestBed.inject(BuilderProjectsService);
  projects.projects.set([{ id: 95, name: 'Workflow', summary: 'Test' }]);
  actions.logProjectId.set(95);
  actions.results.set({ 95: { label: 'Project build', status: 'running', message: 'Working…' } });
  actions.buildLogs.set([
    { timestamp: '', level: 'INFO', event: 'build.render.completed' },
    { timestamp: '', level: 'INFO', event: 'build.agent_implementation.started' },
    { timestamp: '', level: 'INFO', event: 'build.runtime_tests_checked' },
  ]);

  const fixture = TestBed.createComponent(ProjectBuildActionsComponent);
  fixture.componentInstance.shownProjectId = 95;
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelector('.build-log-output .build-workflow')).toBeNull();
  const steps = Array.from(fixture.nativeElement.querySelectorAll('.build-workflow-step') as NodeListOf<HTMLElement>);
  expect(steps.map(step => step.textContent?.trim())).toEqual([
    '✓Create plan', '·✓Split work', '·✓Delegate parallel agents', '·✓Loop: test', '·Loop: build', '·✓Loop: validate', '·✓Create documents',
  ]);

  actions.results.set({ 95: { label: 'Project build', status: 'success', message: 'Built.' } });
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelectorAll('.build-workflow-step-complete')).toHaveLength(7);
});
