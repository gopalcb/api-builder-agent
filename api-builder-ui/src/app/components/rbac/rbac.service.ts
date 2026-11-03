import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

export interface RbacRoute { key: string; method: string; path: string; access: 'public' | 'authenticated'; }
export interface RbacRole { id: string; description: string; group: string; create_group: boolean; }
export interface RbacConfiguration {
  schema_version: number;
  identity: { provider: 'cognito'; user_pool_id: string; client_id: string };
  routes: RbacRoute[];
  roles: RbacRole[];
  grants: { role: string; route: string }[];
  notes: string;
  questions: string[];
  cases: { roles: string[]; route: string; expected: 'allow' | 'deny' }[];
}
export interface RbacSnapshot { revision: number; configuration: RbacConfiguration | null; }
export const emptyConfiguration = (): RbacConfiguration => ({
  schema_version: 1, identity: { provider: 'cognito', user_pool_id: '', client_id: '' },
  routes: [], roles: [], grants: [], notes: '', questions: [], cases: [],
});

@Injectable({ providedIn: 'root' })
export class RbacService {
  session: { configuration: RbacConfiguration; revision: number; baseline: string; importedSource: string | null; prompt: string; roleName: string; groupName: string; submittedRole: boolean; error: string; announcement: string } | null = null;
  private readonly http = inject(HttpClient);
  load() { return this.http.get<RbacSnapshot>('/api/rbac'); }
  save(configuration: RbacConfiguration, revision: number) {
    return this.http.put<RbacSnapshot>('/api/rbac', { configuration, revision });
  }
  generate(configuration: RbacConfiguration, revision: number, prompt: string) {
    return this.http.post<RbacSnapshot>('/api/rbac/generate', { configuration, revision, prompt });
  }
  preview(configuration: RbacConfiguration, revision: number, roles: string[], route: string) {
    return this.http.post<{ decision: 'allow' | 'deny'; public: boolean; mode: string }>('/api/rbac/preview', { configuration, revision, roles, route });
  }
  export(revision: number) { return this.http.post('/api/rbac/export', { revision }, { responseType: 'blob' }); }
}
