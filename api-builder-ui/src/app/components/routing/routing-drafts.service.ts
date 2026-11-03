import { RouteType } from '../../interfaces/route-type.interface';
import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { BuilderProjectsService } from '../../services/builder-projects.service';

export type RouteOperation = 'list' | 'get' | 'create' | 'update' | 'delete' | 'sell';
export type RouteAccess = 'authenticated' | 'public';
export const operationMethods = {
  list: 'GET', get: 'GET', create: 'POST', update: 'PATCH', delete: 'DELETE', sell: 'POST',
} as const;
export interface RouteDraft {
  id: number;
  operation: RouteOperation | null;
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE' | null;
  path: string;
  entity: string;
  access: RouteAccess;
  type: RouteType;
  prompt: string;
}

export function normalizeRoutePath(path: string): string {
  return path.trim().replace(/\/+$/, '') || '/';
}

export function routeShape(path: string): string {
  return normalizeRoutePath(path).replace(/\{[A-Za-z_][A-Za-z0-9_]*\}/g, '{}');
}

@Injectable({ providedIn: 'root' })
export class RoutingDraftsService {
  private readonly drafts = signal<RouteDraft[]>([]);
  readonly routes = this.drafts.asReadonly();
  private nextId = 1;
  private readonly http = inject(HttpClient);
  private readonly seededEntities = new Set<number>();
  private readonly slugs = new Map<string, number>();
  readonly catalogError = signal('');
  private readonly catalogErrors = new Map<number, string>();

  readonly entityNames = signal<string[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  private revision = 0;
  private readonly projectId = inject(BuilderProjectsService).activeId();
  private get options() { return this.projectId ? { headers: { 'X-Project-ID': String(this.projectId) } } : {}; }

  async loadEntities(): Promise<void> {
    if (this.loading() || this.saving()) return;
    this.loading.set(true);
    this.catalogError.set('');
    try {
      const result = await firstValueFrom(this.http.get<{ routes: RouteDraft[]; revision: number; entities?: string[] }>('/api/endpoints', this.options));
      this.drafts.set(result.routes);
      this.entityNames.set(result.entities ?? [...new Set(result.routes.map(route => route.entity))]);
      this.revision = result.revision;
      this.nextId = Math.max(0, ...result.routes.map(route => route.id)) + 1;
    } catch {
      this.catalogError.set('Could not load endpoints. Retry before editing.');
    } finally { this.loading.set(false); }
  }

  restore(routes: RouteDraft[]): void { this.drafts.set(routes); }

  async persist(): Promise<boolean> {
    if (this.saving() || this.loading()) return false;
    this.saving.set(true);
    this.catalogError.set('');
    try {
      const result = await firstValueFrom(this.http.put<{ revision: number }>('/api/endpoints', {
        routes: this.routes(), revision: this.revision,
      }, this.options));
      this.revision = result.revision;
      return true;
    } catch {
      this.catalogError.set('Could not save endpoints. Your edits remain here. Retry, or reload if another tab changed them.');
      return false;
    } finally { this.saving.set(false); }
  }

  ensureEntityRoutes(entities: { id: number; name: string }[]): void {
    for (const entity of entities) {
      if (this.seededEntities.has(entity.id)) continue;
      this.catalogErrors.delete(entity.id);
      const slug = entity.name.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
      if (!slug || (this.slugs.has(slug) && this.slugs.get(slug) !== entity.id)) {
        this.catalogErrors.set(entity.id, `Choose a unique URL-safe name for ${entity.name} to create its routes.`);
        continue;
      }
      const operations = Object.keys(operationMethods).filter(operation => operation !== 'sell') as RouteOperation[];
      if (operations.some((operation) => this.routes().some((route) => routeShape(route.path) === `/${slug}/${operation}`))) {
        this.catalogErrors.set(entity.id, `Existing paths conflict with default routes for ${entity.name}.`);
        continue;
      }
      this.slugs.set(slug, entity.id);
      this.seededEntities.add(entity.id);
      for (const operation of operations) {
        this.save({ operation, method: operationMethods[operation], path: `/${slug}/${operation}`,
          entity: entity.name, access: 'authenticated', prompt: '' }, null);
      }
    }
    this.catalogError.set([...this.catalogErrors.values()].join(' '));
  }

  save(draft: Omit<RouteDraft, 'id' | 'type'> & { type?: RouteType }, id: number | null): void {
    const normalized = { ...draft, type: draft.type ?? draft.access };
    if (id === null) {
      this.drafts.update((routes) => [...routes, { ...normalized, id: this.nextId++ }]);
    } else {
      this.drafts.update((routes) => routes.map((route) => route.id === id ? { ...normalized, id } : route));
    }
  }

  renameEntity(previous: string, name: string): void {
    // Keep configured URLs stable when changing an entity's display name.
    this.drafts.update((routes) => routes.map((route) => route.entity === previous ? { ...route, entity: name } : route));
  }

  removeEntity(entity: { id: number; name: string }): void {
    this.drafts.update((routes) => routes.filter((route) => route.entity !== entity.name));
    this.seededEntities.delete(entity.id);
    for (const [slug, id] of this.slugs) if (id === entity.id) this.slugs.delete(slug);
    this.catalogErrors.delete(entity.id);
    this.catalogError.set([...this.catalogErrors.values()].join(' '));
  }

  remove(id: number): void {
    this.drafts.update((routes) => routes.filter((route) => route.id !== id));
  }
}
