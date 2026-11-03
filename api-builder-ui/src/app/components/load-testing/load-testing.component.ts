import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { WoCardComponent } from '../../../theme/components';
import { WoIconComponent } from '../../../theme/icon.component';
import { BuilderProjectsService } from '../../services/builder-projects.service';
import { ProjectActivitiesService } from '../../services/project-activities.service';
import { AutoScrollLogsDirective } from '../../directives/auto-scroll-logs.directive';

interface LoadConfiguration {
  prompt: string; host: string; users: number; spawnRate: number; duration: number; waitMin: number; waitMax: number;
}
interface Metrics { path: string; requests: number; failures: number; average: number; rps: number; p50: number; p90: number; p95: number; p99: number; }
interface LoadRun { id: string; status: string; startedAt: string; completedAt?: string; error?: string; codeUpdated: boolean; endpoints: string[]; }
interface LoadReport extends LoadRun { metrics: Partial<Metrics>; statistics: Metrics[]; configuration: LoadConfiguration; }
interface LoadState { configuration: LoadConfiguration | null; run: LoadRun | null; report: LoadReport | null; logs?: string[]; }

@Component({
  imports: [FormsModule, WoCardComponent, WoIconComponent, DatePipe, DecimalPipe, AutoScrollLogsDirective],
  templateUrl: './load-testing.component.html',
  styleUrl: './load-testing.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoadTestingComponent {
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  private readonly activities = inject(ProjectActivitiesService);
  private readonly projectId = inject(BuilderProjectsService).activeId();
  private readonly options = { headers: { 'X-Project-ID': String(this.projectId) } };
  private poll?: ReturnType<typeof setTimeout>;
  readonly state = { configuration: { prompt: 'Test all read endpoints', host: 'http://127.0.0.1:8080', users: 10, spawnRate: 1, duration: 300, waitMin: 1, waitMax: 3 }, baseline: '' };
  readonly loading = signal(true);
  readonly ready = signal(false);
  readonly running = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly report = signal<LoadReport | null>(null);
  readonly run = signal<LoadRun | null>(null);
  readonly logs = signal<string[]>([]);
  get dirty(): boolean { return JSON.stringify(this.state.configuration) !== this.state.baseline; }

  constructor() {
    this.destroyRef.onDestroy(() => clearTimeout(this.poll));
    this.load();
  }

  load(): void {
    clearTimeout(this.poll);
    this.error.set('');
    if (!this.ready()) this.loading.set(true);
    this.http.get<LoadState>('/api/load-testing', this.options).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        if (!this.ready() && result.configuration) {
          this.state.configuration = result.configuration;
          this.state.baseline = JSON.stringify(result.configuration);
        }
        this.loading.set(false);
        this.ready.set(true);
        this.report.set(result.report);
        this.run.set(result.run);
        this.logs.set(result.logs ?? []);
        this.running.set(result.run?.status === 'running');
        if (result.run?.error) this.error.set(result.run.error);
        if (this.running()) this.poll = setTimeout(() => this.load(), 1500);
      },
      error: (error: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(error.error?.error || 'Could not load the latest report. Retry to check the run status.');
      },
    });
  }

  private validation(config: LoadConfiguration): string {
    if (!config || typeof config.prompt !== 'string' || !config.prompt.trim() || config.prompt.length > 4000) return 'Describe all endpoints or the specific endpoints to test.';
    if (typeof config.host !== 'string') return 'Enter a valid target URL.';
    try {
      const url = new URL(config.host);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return 'Enter an HTTP or HTTPS target URL without credentials, query parameters or fragments.';
    } catch { return 'Enter a valid target URL.'; }
    if (!Number.isInteger(config.users) || config.users < 1 || config.users > 100) return 'Concurrent users must be between 1 and 100.';
    if (!Number.isFinite(config.spawnRate) || config.spawnRate < 0.1 || config.spawnRate > 100) return 'Spawn rate must be between 0.1 and 100 users per second.';
    if (!Number.isInteger(config.duration) || config.duration < 1 || config.duration > 3600) return 'Duration must be between 1 and 3,600 seconds.';
    if (![config.waitMin, config.waitMax].every(value => Number.isFinite(value) && value >= 0 && value <= 300) || config.waitMin > config.waitMax) return 'Wait times must be between 0 and 300 seconds, with minimum no greater than maximum.';
    return '';
  }

  start(): void {
    if (!this.ready() || this.running()) return;
    this.notice.set('');
    const configuration = { ...this.state.configuration, prompt: this.state.configuration.prompt.trim(), host: this.state.configuration.host.trim() };
    this.error.set(this.validation(configuration));
    if (this.error()) return;
    this.running.set(true);
    this.http.post<{ run: LoadRun }>('/api/load-testing', configuration, this.options).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.state.configuration = configuration;
        this.state.baseline = JSON.stringify(configuration);
        this.run.set(result.run);
        this.notice.set(result.run.codeUpdated ? 'Load testing code generated. Running in Docker…' : 'Reusing load testing code. Running in Docker…');
        this.activities.record(this.projectId, 'Load testing started', 'success');
        this.poll = setTimeout(() => this.load(), 1000);
      },
      error: (error: HttpErrorResponse) => {
        this.running.set(false);
        this.error.set(error.error?.error || 'Could not start load testing. Retry status before starting again.');
        if (error.status === 409) this.load();
      },
    });
  }
}
