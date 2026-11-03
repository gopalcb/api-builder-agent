import { Component, ElementRef, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { firstValueFrom, timeout } from 'rxjs';
import { WoCardComponent } from '../../../theme/components';
import { SelectComponent } from '../select/select.component';
import { BuilderProjectsService } from '../../services/builder-projects.service';

interface Policy { kind: string; path: string; method: string; access: string; ttl_seconds: number; api_type: string; query_keys: string[]; }
interface Preset { id: string; label: string; description: string; ttl_seconds: number; }
interface Snapshot { revision: number; configuration: Policy | null; presets: Preset[]; }
interface Draft { policy: Policy; revision: number; baseline: string; presets: Preset[]; loaded: boolean; confirmed: boolean; queries: string; }

@Component({
  imports: [FormsModule, WoCardComponent, SelectComponent],
  templateUrl: './caching.component.html',
  styleUrl: './caching.component.css',
})
export class CachingComponent {
  private readonly http = inject(HttpClient);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  readonly state = inject(BuilderProjectsService).scope<Draft>(CachingComponent, () => ({
    policy: { kind: 'route', path: '/catalog', method: 'GET', access: 'public', ttl_seconds: 60, api_type: 'http', query_keys: [] },
    revision: 0, baseline: '', presets: [], loaded: false, confirmed: false, queries: '',
  }));
  readonly busy = signal(false);
  readonly error = signal('');
  readonly invalidField = signal('');
  readonly status = signal('');
  readonly discard = signal(false);
  readonly apiTypes = [{ value: 'http', label: 'HTTP API' }, { value: 'rest', label: 'REST API' }];
  get options() { return this.state.presets.map(p => ({ value: p.id, label: p.label })); }
  get selected() { return this.state.presets.find(p => p.id === this.state.policy.kind); }
  get dirty() { return JSON.stringify(this.policy()) !== this.state.baseline; }

  constructor() { if (!this.state.loaded) void this.load(); }

  policy(): Policy {
    return { ...this.state.policy, query_keys: this.state.queries.split(',').map(key => key.trim()).filter(Boolean) };
  }

  choose(kind: string): void {
    const preset = this.state.presets.find(p => p.id === kind);
    if (!preset || this.busy()) return;
    this.state.policy = { ...this.state.policy, kind, ttl_seconds: preset.ttl_seconds, api_type: kind === 'gateway' ? 'rest' : this.state.policy.api_type };
    this.status.set('Template applied to your draft. Save to persist it.');
  }

  async load(force = false): Promise<void> {
    if (this.busy()) return;
    if (this.state.loaded && this.dirty && !force) { this.discard.set(true); return; }
    this.busy.set(true); this.error.set('');
    try {
      const data = await firstValueFrom(this.http.get<Snapshot>('/api/caching').pipe(timeout(15000)));
      this.accept(data);
      this.discard.set(false);
      this.status.set(data.configuration ? 'Saved configuration loaded.' : 'Choose a template to configure caching.');
    } catch { this.error.set('Could not load caching. Retry; your draft is preserved.'); }
    finally { this.busy.set(false); }
  }

  accept(data: Snapshot): void {
    this.invalidField.set('');
    this.state.presets = data.presets;
    this.state.revision = data.revision;
    this.state.policy = data.configuration ?? { kind: 'route', path: '/catalog', method: 'GET', access: 'public', ttl_seconds: 60, api_type: 'http', query_keys: [] };
    this.state.queries = this.state.policy.query_keys.join(', ');
    this.state.baseline = JSON.stringify(this.state.policy);
    this.state.confirmed = !!data.configuration;
    this.state.loaded = true;
  }

  async save(): Promise<void> {
    if (this.busy() || !this.state.loaded) return;
    const policy = this.policy();
    this.invalidField.set('');
    let field = '';
    if (!/^\/(?:[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*)?$/.test(policy.path) || policy.path.length > 200) field = 'cache-path';
    else if (!Number.isInteger(policy.ttl_seconds) || policy.ttl_seconds < 1 || policy.ttl_seconds > 3600) field = 'cache-ttl';
    else if (policy.query_keys.length > 10 || new Set(policy.query_keys).size !== policy.query_keys.length || policy.query_keys.some(key => !/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(key))) field = 'cache-query';
    else if (!this.state.confirmed) field = 'cache-public';
    if (field) {
      this.invalidField.set(field);
      this.error.set('Enter a literal /route/path, TTL 1–3600, up to 10 unique query names, and confirm the route is public.');
      this.host.nativeElement.querySelector<HTMLElement>(`#${field}`)?.focus();
      return;
    }
    if (policy.kind === 'gateway' && policy.api_type !== 'rest') {
      this.invalidField.set('cache-api');
      this.error.set('API Gateway caching requires a REST API.');
      this.host.nativeElement.querySelector<HTMLElement>('#cache-api')?.focus();
      return;
    }
    this.busy.set(true); this.error.set('');
    try {
      const result = await firstValueFrom(this.http.put<Snapshot>('/api/caching', { revision: this.state.revision, configuration: policy }).pipe(timeout(15000)));
      this.accept(result);
      this.status.set(`Revision ${result.revision} saved. Export to integrate the cache.`);
    } catch (error) {
      this.error.set(error instanceof HttpErrorResponse && error.status === 409 ? 'Configuration changed elsewhere. Reload before saving; your draft is preserved.' : 'Save failed. Your draft is preserved; retry.');
    } finally { this.busy.set(false); }
  }

  async export(): Promise<void> {
    if (this.busy() || this.dirty || !this.state.revision) return;
    this.busy.set(true); this.error.set('');
    try {
      const blob = await firstValueFrom(this.http.post('/api/caching/export', { revision: this.state.revision }, { responseType: 'blob' }).pipe(timeout(15000)));
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `caching-${this.state.revision}.zip`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      this.status.set('Template exported. Runtime integration is required to enable caching.');
    } catch { this.error.set('Export failed or the saved revision changed. Reload and retry.'); }
    finally { this.busy.set(false); }
  }
}
