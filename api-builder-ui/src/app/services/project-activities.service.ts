import { Injectable, signal } from '@angular/core';

export interface ProjectActivity { id: string; projectId: number; action: string; status: 'interaction' | 'running' | 'success' | 'failure'; time: string; }
@Injectable({ providedIn: 'root' })
export class ProjectActivitiesService {
  readonly entries = signal<ProjectActivity[]>([]);
  readonly storageError = signal(false);
  private readonly key = 'api-builder.activities.v1';
  constructor() {
    try {
      const saved = JSON.parse(localStorage.getItem(this.key) || '[]');
      if (Array.isArray(saved)) this.entries.set(saved.filter(item => item && Number.isInteger(item.projectId) && typeof item.id === 'string' && typeof item.action === 'string' && typeof item.time === 'string' && ['interaction', 'running', 'success', 'failure'].includes(item.status)).slice(0, 500));
    } catch { this.storageError.set(true); }
  }
  record(projectId: number | null, action: string, status: ProjectActivity['status'] = 'interaction'): void {
    if (!projectId) return;
    this.entries.update(entries => [{ id: crypto.randomUUID(), projectId, action: action.slice(0, 120), status, time: new Date().toISOString() }, ...entries].slice(0, 500));
    try { localStorage.setItem(this.key, JSON.stringify(this.entries())); this.storageError.set(false); }
    catch { this.storageError.set(true); }
  }
}
