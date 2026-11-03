import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom, timeout } from 'rxjs';

export interface BuilderProject { id: number; name: string; summary: string; build_ready?: boolean; repository?: {owner: string; name: string; url: string} | null; }

@Injectable({ providedIn: 'root' })
export class BuilderProjectsService {
  private readonly http = inject(HttpClient);
  readonly projects = signal<BuilderProject[]>([]);
  readonly activeId = signal<number | null>(null);
  readonly activeProject = computed(() => this.projects().find(project => project.id === this.activeId()) ?? null);
  readonly orderedProjects = computed(() => {
    const active = this.activeId();
    return [...this.projects()].sort((a, b) => Number(b.id === active) - Number(a.id === active));
  });
  readonly loading = signal(false);
  readonly error = signal('');
  private loaded = false;
  private pending: Promise<boolean> | null = null;
  private readonly scopes = new Map<number, Map<unknown, unknown>>();

  load(): Promise<boolean> {
    if (this.loaded) return Promise.resolve(!!this.activeProject());
    if (this.pending) return this.pending;
    this.pending = this.fetchProjects().finally(() => this.pending = null);
    return this.pending;
  }

  private async fetchProjects(): Promise<boolean> {
    this.loading.set(true);
    this.error.set('');
    try {
      const result = await firstValueFrom(this.http.get<{ projects: BuilderProject[]; default_project_id: number | null }>('/api/projects').pipe(timeout(15000)));
      this.projects.set(result.projects);
      let remembered = 0;
      try { remembered = Number(localStorage.getItem('api-builder.active-project')); } catch { /* Storage is optional. */ }
      this.activeId.set(null);
      this.select(result.projects.some(project => project.id === remembered) ? remembered : result.default_project_id);
      this.loaded = true;
      return !!this.activeProject();
    } catch {
      this.activeId.set(null);
      this.error.set('Could not load projects. Retry before configuring a project.');
      return false;
    } finally { this.loading.set(false); }
  }

  select(id: number | null): void {
    if (!this.projects().some(project => project.id === id)) return;
    this.activeId.set(id);
    try { localStorage.setItem('api-builder.active-project', String(id)); } catch { /* Selection still works for this session. */ }
  }

  async activate(id: number): Promise<boolean> {
    if (!this.projects().some(project => project.id === id)) return false;
    this.select(id);
    try {
      await firstValueFrom(this.http.post(`/api/projects/${id}/run`, {}).pipe(timeout(360000)));
      return true;
    } catch {
      return false;
    }
  }

  async create(name: string, summary: string): Promise<boolean> {
    if (this.loading()) return false;
    this.loading.set(true);
    this.error.set('');
    try {
      const { project } = await firstValueFrom(this.http.post<{ project: BuilderProject }>('/api/projects', { name: name.trim(), summary: summary.trim() }).pipe(timeout(15000)));
      this.projects.update(projects => [...projects, project]);
      if (!this.activeProject()) this.select(project.id);
      return true;
    } catch (error) {
      this.error.set(error instanceof HttpErrorResponse && error.status === 409 ? 'A project with this name already exists.' : 'Could not save the project. Your inputs are preserved; try again.');
      return false;
    } finally { this.loading.set(false); }
  }

  async update(id: number, name: string, summary: string): Promise<boolean> {
    if (this.loading()) return false;
    this.loading.set(true);
    this.error.set('');
    try {
      const { project } = await firstValueFrom(this.http.put<{ project: BuilderProject }>(`/api/projects/${id}`, { name: name.trim(), summary: summary.trim() }).pipe(timeout(15000)));
      this.projects.update(projects => projects.map(item => item.id === id ? project : item));
      return true;
    } catch (error) {
      this.error.set(error instanceof HttpErrorResponse && error.status === 409 ? 'A project with this name already exists.' : 'Could not update the project. Your inputs are preserved.');
      return false;
    } finally { this.loading.set(false); }
  }

  async remove(id: number): Promise<boolean> {
    if (this.loading()) return false;
    this.loading.set(true);
    this.error.set('');
    try {
      await firstValueFrom(this.http.delete(`/api/projects/${id}`).pipe(timeout(15000)));
      this.projects.update(projects => projects.filter(project => project.id !== id));
      this.scopes.delete(id);
      if (this.activeId() === id) {
        this.activeId.set(null);
        this.select(this.projects()[0]?.id ?? null);
      }
      return true;
    } catch {
      this.error.set('Could not delete the project. Try again.');
      return false;
    } finally { this.loading.set(false); }
  }

  scope<T>(key: unknown, create: () => T): T {
    const id = this.activeProject()?.id ?? 0;
    let scope = this.scopes.get(id);
    if (!scope) { scope = new Map(); this.scopes.set(id, scope); }
    if (!scope.has(key)) scope.set(key, create());
    return scope.get(key) as T;
  }
}
