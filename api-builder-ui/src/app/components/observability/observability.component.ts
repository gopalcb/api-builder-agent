import { Component, ElementRef, HostListener, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { firstValueFrom, timeout } from 'rxjs';
import { WoCardComponent } from '../../../theme/components';
import { BuilderProjectsService } from '../../services/builder-projects.service';

export interface ObservabilityConfiguration {
  enabled: boolean;
  service_name: string;
  service_namespace: string;
  environment: string;
  endpoint: string;
  sample_ratio: number;
  exclude_health: boolean;
}
interface Snapshot { revision: number; configuration: ObservabilityConfiguration; }
interface Draft { configuration: ObservabilityConfiguration; revision: number; baseline: string; loaded: boolean; }

@Component({
  imports: [FormsModule, WoCardComponent],
  templateUrl: './observability.component.html',
  styleUrl: './observability.component.css',
})
export class ObservabilityComponent {
  private readonly http = inject(HttpClient);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  readonly state = inject(BuilderProjectsService).scope<Draft>(ObservabilityComponent, () => ({
    configuration: { enabled: false, service_name: 'api-builder', service_namespace: 'local', environment: 'development', endpoint: 'http://127.0.0.1:4318/v1/traces', sample_ratio: 1, exclude_health: true },
    revision: 0, baseline: '', loaded: false,
  }));
  readonly busy = signal(false);
  readonly error = signal('');
  readonly invalidField = signal('');
  readonly status = signal('');
  readonly discard = signal(false);
  readonly traceId = signal('');
  readonly setupCommand = 'docker compose -f compose.observability.yaml up -d';
  get dirty(): boolean { return this.state.loaded && JSON.stringify(this.state.configuration) !== this.state.baseline; }
  get canTest(): boolean { return this.state.loaded && !!this.state.revision && this.state.configuration.enabled && !this.dirty && !this.busy(); }

  constructor() { if (!this.state.loaded) void this.load(); }

  @HostListener('window:beforeunload', ['$event'])
  protectDraft(event: BeforeUnloadEvent): void {
    if (this.dirty) { event.preventDefault(); event.returnValue = ''; }
  }

  async load(force = false): Promise<void> {
    if (this.busy()) return;
    if (this.dirty && !force) { this.discard.set(true); return; }
    this.busy.set(true); this.error.set('');
    try {
      const data = await firstValueFrom(this.http.get<Snapshot>('/api/observability').pipe(timeout(15000)));
      this.accept(data);
      this.discard.set(false);
      this.status.set(data.revision ? 'Saved configuration loaded.' : 'Local defaults loaded. Enable tracing and save to start.');
    } catch { this.error.set('Could not load observability. Retry; your draft is preserved.'); }
    finally { this.busy.set(false); }
  }

  accept(data: Snapshot): void {
    this.state.configuration = { ...data.configuration };
    this.state.revision = data.revision;
    this.state.baseline = JSON.stringify(this.state.configuration);
    this.state.loaded = true;
    this.invalidField.set('');
    this.traceId.set('');
  }

  async save(): Promise<void> {
    if (this.busy() || !this.state.loaded) return;
    this.invalidField.set(''); this.error.set('');
    const config = this.state.configuration;
    const namePattern = /^[A-Za-z][A-Za-z0-9._-]{0,79}$/;
    let field = '';
    let message = '';
    for (const [key, id, label] of [['service_name', 'otel-service', 'Service name'], ['service_namespace', 'otel-namespace', 'Service namespace'], ['environment', 'otel-environment', 'Environment']] as const) {
      if (!namePattern.test(config[key]) || (key === 'environment' && config[key].length > 40)) {
        field = id; message = `${label} must start with a letter and use up to ${key === 'environment' ? 40 : 80} letters, numbers, dots, underscores or hyphens.`; break;
      }
    }
    if (!field) {
      const endpoint = /^http:\/\/(?:localhost|127\.0\.0\.1|\[::1\]):([0-9]{1,5})\/v1\/traces$/.exec(config.endpoint);
      if (!endpoint || +endpoint[1] < 1 || +endpoint[1] > 65535) {
        field = 'otel-endpoint'; message = 'Use a local HTTP endpoint with a port and /v1/traces, for example http://127.0.0.1:4318/v1/traces.';
      } else if (typeof config.sample_ratio !== 'number' || !Number.isFinite(config.sample_ratio) || config.sample_ratio < 0 || config.sample_ratio > 1) {
        field = 'otel-sampling'; message = 'Sampling ratio must be a number from 0 to 1. Use 1 to capture every new trace.';
      }
    }
    if (field) {
      this.invalidField.set(field); this.error.set(message);
      this.host.nativeElement.querySelector<HTMLElement>(`#${field}`)?.focus();
      return;
    }
    this.busy.set(true);
    try {
      const data = await firstValueFrom(this.http.put<Snapshot>('/api/observability', { revision: this.state.revision, configuration: { ...config } }).pipe(timeout(15000)));
      this.accept(data);
      this.status.set(`Revision ${data.revision} saved. ${data.configuration.enabled ? 'Tracing applies to subsequent requests for this project.' : 'Tracing is disabled for subsequent requests for this project.'} Rebuild to update generated artifacts.`);
    } catch (error) {
      this.error.set(error instanceof HttpErrorResponse && error.status === 409 ? 'Configuration changed elsewhere. Reload before saving; your draft is preserved.' : 'Save failed. Your draft is preserved; retry.');
    } finally { this.busy.set(false); }
  }

  async testTrace(): Promise<void> {
    if (!this.canTest) return;
    this.busy.set(true); this.error.set(''); this.traceId.set(''); this.status.set('Sending a test trace…');
    try {
      const result = await firstValueFrom(this.http.post<{ trace_id: string; message: string }>('/api/observability/test', { revision: this.state.revision }).pipe(timeout(15000)));
      this.traceId.set(result.trace_id);
      this.status.set('Collector accepted the test trace. Open it in Jaeger to inspect it.');
    } catch (error) {
      this.status.set('');
      this.error.set(error instanceof HttpErrorResponse && error.status === 409 ? 'Configuration changed elsewhere. Reload before testing.' : 'Test trace could not be exported. Check that the local collector is running and the saved endpoint is correct, then retry.');
    } finally { this.busy.set(false); }
  }
}
