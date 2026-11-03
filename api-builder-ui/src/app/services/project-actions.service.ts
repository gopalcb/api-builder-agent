import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ProjectActivitiesService } from './project-activities.service';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { firstValueFrom, timeout } from 'rxjs';
import { BuilderProject, BuilderProjectsService } from './builder-projects.service';

export interface BuildLog { timestamp: string; level: string; event: string; function?: string; agent?: string; step?: string; duration_ms?: number; error_type?: string; }
interface BuildLogSession { projectId: number; runId: string; cursor: number; finished: boolean; timer?: ReturnType<typeof setTimeout>; }

@Injectable({ providedIn: 'root' })
export class ProjectActionsService {
  private readonly destroyRef = inject(DestroyRef);
  private logSession?: BuildLogSession;
  readonly buildLogs = signal<BuildLog[]>([]);
  readonly buildLogsError = signal('');
  readonly logProjectId = signal<number | null>(null);
  private readonly dismissTimers = new Map<number, ReturnType<typeof setTimeout>>();
  private readonly cleanup = inject(DestroyRef).onDestroy(() => {
    for (const timer of this.dismissTimers.values()) clearTimeout(timer);
    clearTimeout(this.logSession?.timer);
  });
  private readonly http = inject(HttpClient);
  readonly projects = inject(BuilderProjectsService);
  private readonly activities = inject(ProjectActivitiesService);
  readonly results = signal<Record<number, { label: string; status: 'running' | 'success' | 'failure'; message: string }>>({});
  readonly busy = signal(false);
  readonly operation = signal('');
  readonly notices = signal<Record<number, string>>({});
  readonly errors = signal<Record<number, string>>({});

  private start(id: number, operation: string): boolean {
    if (this.busy()) return false;
    clearTimeout(this.dismissTimers.get(id));
    this.dismissTimers.delete(id);
    this.activities.record(id, operation, 'running');
    this.results.update(values => ({...values, [id]: { label: operation === 'test' ? 'Project test' : operation === 'build' ? 'Project build' : operation === 'github' ? 'GitHub publication' : 'Project download', status: 'running', message: operation === 'test' ? 'Checking project source, configuration and starter health…' : operation === 'build' ? 'Implementing the saved configuration with the agent, then checking the API in Docker…' : 'Working…' }}));
    this.busy.set(true);
    this.operation.set(operation);
    this.errors.update(values => ({...values, [id]: ''}));
    this.notices.update(values => ({...values, [id]: ''}));
    return true;
  }

  private failed(id: number, error: unknown): void {
    this.errors.update(values => ({...values, [id]: error instanceof HttpErrorResponse && typeof error.error?.error === 'string' ? error.error.error : 'The action was not confirmed. Please try again.'}));
    this.activities.record(id, this.operation(), 'failure');
    this.results.update(values => ({...values, [id]: { ...values[id], status: 'failure', message: this.errors()[id] }}));
    this.dismissTestResult(id);
    if (error instanceof HttpErrorResponse && error.status === 409) this.projects.projects.update(projects => projects.map(project => project.id === id ? {...project, build_ready: false} : project));
  }

  private completed(id: number, message: string): void {
    this.activities.record(id, this.operation(), 'success');
    this.results.update(values => ({...values, [id]: { ...values[id], status: 'success', message }}));
    this.dismissTestResult(id);
  }

  private dismissTestResult(id: number): void {
    if (this.operation() !== 'test') return;
    const result = this.results()[id];
    this.dismissTimers.set(id, setTimeout(() => {
      this.results.update(values => {
        if (values[id] !== result) return values;
        const next = { ...values };
        delete next[id];
        return next;
      });
      this.dismissTimers.delete(id);
    }, 5000));
  }

  async run(project: BuilderProject, operation: 'test' | 'build'): Promise<void> {
    if (!this.start(project.id, operation)) return;
    const session = operation === 'build' ? this.startBuildLogs(project.id) : undefined;
    try {
      const result = await firstValueFrom(this.http.post<{ project: BuilderProject; message: string }>(`/api/projects/${project.id}/${operation}`, session ? { run_id: session.runId } : {}).pipe(timeout(operation === 'build' ? 600000 : 60000)));
      this.projects.projects.update(projects => projects.map(item => item.id === project.id ? result.project : item));
      this.notices.update(values => ({...values, [project.id]: result.message}));
      this.completed(project.id, result.message);
    } catch (error) { this.failed(project.id, error); }
    finally {
      if (session) session.finished = true;
      this.busy.set(false);
    }
  }

  private startBuildLogs(projectId: number): BuildLogSession {
    clearTimeout(this.logSession?.timer);
    const session: BuildLogSession = { projectId, runId: crypto.randomUUID(), cursor: 0, finished: false };
    this.logSession = session;
    this.logProjectId.set(projectId);
    this.buildLogs.set([]);
    this.buildLogsError.set('');
    this.readBuildLogs(session);
    return session;
  }

  private readBuildLogs(session: BuildLogSession): void {
    const finalRead = session.finished;
    this.http.get<{ entries: BuildLog[]; cursor: number; more: boolean }>(
      `/api/projects/${session.projectId}/build/logs/${session.runId}?cursor=${session.cursor}`,
    ).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        if (this.logSession !== session) return;
        session.cursor = result.cursor;
        this.buildLogs.update(entries => [...entries, ...result.entries].slice(-500));
        this.buildLogsError.set('');
        if (!finalRead || result.more) session.timer = setTimeout(() => this.readBuildLogs(session), result.more ? 0 : 750);
      },
      error: () => {
        if (this.logSession !== session) return;
        this.buildLogsError.set('Build logs are temporarily unavailable.');
        if (!finalRead) session.timer = setTimeout(() => this.readBuildLogs(session), 1500);
      },
    });
  }

  async download(project: BuilderProject): Promise<void> {
    if (!this.start(project.id, 'download')) return;
    try {
      const data = await firstValueFrom(this.http.get(`/api/projects/${project.id}/download`, {responseType: 'blob'}).pipe(timeout(30000)));
      const url = URL.createObjectURL(data);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = (project.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 32) || 'api-project') + '.zip';
      anchor.click();
      this.completed(project.id, 'Project ZIP download prepared.');
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { this.failed(project.id, error); }
    finally { this.busy.set(false); }
  }

  async runCurrent(project: BuilderProject): Promise<string> {
    if (!this.start(project.id, 'run')) return '';
    try {
      const result = await firstValueFrom(this.http.post<{ project: BuilderProject; message: string }>(`/api/projects/${project.id}/run`, {}).pipe(timeout(360000)));
      this.projects.projects.update(projects => projects.map(item => item.id === project.id ? result.project : item));
      this.completed(project.id, result.message);
      return result.message;
    } catch (error) { this.failed(project.id, error); return ''; }
    finally { this.busy.set(false); }
  }

  async publish(project: BuilderProject, configuration: {owner: string; name: string; token: string; create: boolean}): Promise<boolean> {
    if (!this.start(project.id, 'github')) return false;
    try {
      const { repository } = await firstValueFrom(this.http.post<{repository: {owner: string; name: string; url: string}}>(`/api/projects/${project.id}/github`, configuration).pipe(timeout(180000)));
      this.projects.projects.update(projects => projects.map(item => item.id === project.id ? {...item, repository} : item));
      this.notices.update(values => ({...values, [project.id]: 'Project pushed to GitHub.'}));
      this.completed(project.id, 'Project pushed to GitHub.');
      return true;
    } catch (error) { this.failed(project.id, error); return false; }
    finally { this.busy.set(false); }
  }
}
