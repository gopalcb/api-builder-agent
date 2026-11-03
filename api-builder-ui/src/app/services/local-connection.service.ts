import { ButtonFeedbackService } from './button-feedback.service';
import { HttpBackend, HttpClient } from '@angular/common/http';
import { Injectable, InjectionToken, inject, signal } from '@angular/core';
import { finalize, firstValueFrom, timeout } from 'rxjs';

export interface LocalConnection { direct: boolean; port: number; }
export const DEFAULT_CONNECTION: LocalConnection = { direct: false, port: 5000 };
export const CONNECTION_STORAGE_KEY = 'api-builder.local-connection';
export const CONNECTION_BROWSER = new InjectionToken('Connection browser', {
  providedIn: 'root',
  factory: () => ({
    origin: location.origin,
    hostname: location.hostname,
    protocol: location.protocol,
    read: () => localStorage.getItem(CONNECTION_STORAGE_KEY),
    write: (value: string) => localStorage.setItem(CONNECTION_STORAGE_KEY, value),
    reload: () => location.assign('/api-builder/projects'),
  }),
});

export function isBuilderRequest(url: string): boolean {
  return /^\/api\/(?:health|projects|entities|entity-configurations|endpoints|load-testing|project-documents|rbac|caching|observability|generate-search-configuration|generate-infrastructure-plan|create-entity|generate-entity-attributes)(?:[/?]|$)/.test(url);
}

@Injectable({ providedIn: 'root' })
export class LocalConnectionService {
  private readonly feedback = inject(ButtonFeedbackService);
  readonly browser = inject(CONNECTION_BROWSER);
  private readonly http = new HttpClient(inject(HttpBackend));
  readonly canConnectDirectly = ['localhost', '127.0.0.1', '[::1]'].includes(this.browser.hostname)
    && ['http:', 'https:'].includes(this.browser.protocol);
  private readonly current = signal<LocalConnection>(this.restore());
  readonly settings = this.current.asReadonly();

  normalize(value: unknown): LocalConnection {
    if (!value || typeof value !== 'object' || !('direct' in value) || typeof value.direct !== 'boolean') {
      throw new Error('Choose a valid connection mode.');
    }
    if (!value.direct) return { ...DEFAULT_CONNECTION };
    if (!this.canConnectDirectly) throw new Error('Direct connections are available when API Builder is opened on localhost.');
    const port = 'port' in value ? value.port : null;
    if (typeof port !== 'number' || !Number.isInteger(port) || port < 1 || port > 65535) {
      throw new Error('Enter a whole port number from 1 to 65535.');
    }
    return { direct: true, port };
  }

  private restore(): LocalConnection {
    try {
      const saved = this.browser.read();
      return saved ? this.normalize(JSON.parse(saved)) : { ...DEFAULT_CONNECTION };
    } catch { return { ...DEFAULT_CONNECTION }; }
  }

  url(path: string, candidate = this.settings()): string {
    const settings = this.normalize(candidate);
    return settings.direct ? `${this.browser.protocol}//${this.browser.hostname}:${settings.port}${path}` : path;
  }

  address(candidate = this.settings()): string {
    return new URL(this.url('/api', candidate), this.browser.origin).href;
  }

  swaggerUrl(projectId: number): string {
    const settings = this.settings();
    return `/swagger/index.html?project=${projectId}${settings.direct ? `&port=${settings.port}` : ''}`;
  }

  async check(candidate: LocalConnection): Promise<void> {
    const settings = this.normalize(candidate);
    const complete = this.feedback.requestStarted();
    const response = await firstValueFrom(this.http.get<{ service?: string; status?: string }>(
      this.url('/api/health', settings), { withCredentials: true },
    ).pipe(timeout(10000), finalize(complete)));
    if (response?.service !== 'api-builder' || response.status !== 'ok') {
      throw new Error('This address did not identify itself as a ready API Builder backend.');
    }
  }

  async apply(candidate: LocalConnection): Promise<void> {
    const settings = this.normalize(candidate);
    await this.check(settings);
    try { this.browser.write(JSON.stringify(settings)); }
    catch { throw new Error('Settings could not be saved in this browser. Allow site storage and try again.'); }
    this.current.set(settings);
    this.browser.reload();
  }
}
