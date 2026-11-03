import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { FormControl, FormGroup, Validators } from '@angular/forms';
import { normalizeRoutePath, RoutingDraftsService } from '../routing/routing-drafts.service';

export { searchTypes } from '../../interfaces/route-type.interface';
export interface SearchConfiguration {
  summary: string;
  source: string;
  fields: string[];
  embedding: { model: string; dimensions: string; chunking: string } | null;
  ranking: 'none' | 'lexical' | 'vector' | 'rrf';
  request: string;
  response: string;
  steps: string[];
  requirements: string[];
}
export interface SearchDraft {
  id: number;
  type: string;
  path: string;
  prompt: string;
  configuration: SearchConfiguration;
}

@Injectable({ providedIn: 'root' })
export class VectorSearchService {
  private readonly http = inject(HttpClient);
  readonly routing = inject(RoutingDraftsService);
  readonly drafts = signal<SearchDraft[]>([]);
  readonly editingId = signal<number | null>(null);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly status = signal('');
  readonly submitted = signal(false);
  private nextId = 1;
  readonly type = new FormControl('semantic', { nonNullable: true });
  readonly path = new FormControl('', { nonNullable: true, validators: [control => {
    const path = normalizeRoutePath(control.value.trim());
    if (!control.value.trim()) return { required: true };
    if (path.length > 250 || !/^\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+$/.test(path)) return { format: true };
    if (!this.routing.routes().some(route => route.path === path && route.type === this.type.value)) return { routeType: true };
    if (this.drafts().some(draft => draft.id !== this.editingId() && draft.path === path)) return { duplicate: true };
    return null;
  }] });
  readonly prompt = new FormControl('', { nonNullable: true, validators: [Validators.pattern(/\S/), Validators.required, Validators.maxLength(4000)] });
  readonly form = new FormGroup({ type: this.type, path: this.path, prompt: this.prompt });

  accessLabel(path: string): string {
    const route = this.routing.routes().find(route => route.path === path);
    return route ? route.access === 'public' ? 'Public' : 'Authenticated' : 'Route removed';
  }

  get routeOptions() {
    return this.routing.routes().filter(route => route.type === this.type.value)
      .map(route => ({ value: route.path, label: route.path }));
  }

  reconcilePath(): void {
    if (!this.busy() && this.path.value && !this.routeOptions.some(option => option.value === this.path.value)) this.path.setValue('');
    this.path.updateValueAndValidity();
  }

  setType(value: string): void {
    if (this.busy()) return;
    this.type.setValue(value);
    this.reconcilePath();
  }

  setPath(value: string): void {
    if (this.busy() || !this.routeOptions.some(option => option.value === value)) return;
    this.path.setValue(value);
    this.path.markAsTouched();
  }

  generate(): void {
    if (this.busy()) return;
    this.submitted.set(true);
    this.path.updateValueAndValidity();
    this.form.markAllAsTouched();
    if (this.form.invalid) return;
    const request = { type: this.type.value, path: normalizeRoutePath(this.path.value.trim()), prompt: this.prompt.value.trim() };
    const editingId = this.editingId();
    this.busy.set(true);
    this.error.set('');
    this.status.set('Generating and reviewing your configuration…');
    this.form.disable();
    this.http.post<{ configuration: SearchConfiguration }>('/api/generate-search-configuration', request).subscribe({
      next: ({ configuration }) => {
        if (!this.routing.routes().some(route => route.path === request.path && route.type === request.type)) {
          this.finish();
          this.reconcilePath();
          this.status.set('');
          this.error.set('The selected route was removed or its type changed. Choose a current route and generate again.');
          return;
        }
        const draft = { ...request, configuration, id: editingId ?? this.nextId++ };
        this.drafts.update(drafts => editingId === null ? [...drafts, draft] : drafts.map(item => item.id === editingId ? draft : item));
        this.finish();
        this.reset();
        this.status.set(`Configuration generated for ${draft.path}. Review setup requirements before implementation.`);
      },
      error: (error) => {
        this.finish();
        this.status.set('');
        this.error.set(error.status === 504 ? 'Generation timed out. Your inputs and previous configuration are preserved. Retry generation.'
          : 'Could not generate the configuration. Check the backend and local Codex sign-in, then retry. Your inputs are preserved.');
      },
    });
  }

  edit(draft: SearchDraft): void {
    if (this.busy()) return;
    this.editingId.set(draft.id);
    this.form.reset({ type: draft.type, path: draft.path, prompt: draft.prompt });
    this.reconcilePath();
    this.submitted.set(false);
    this.error.set('');
    this.status.set(`Editing ${draft.path}.`);
  }

  remove(draft: SearchDraft): void {
    if (this.busy()) return;
    this.drafts.update(drafts => drafts.filter(item => item.id !== draft.id));
    if (this.editingId() === draft.id) this.reset();
    this.path.updateValueAndValidity();
    this.status.set(`Removed configuration draft ${draft.path}.`);
  }

  reset(): void {
    if (this.busy()) return;
    this.editingId.set(null);
    this.form.reset({ type: this.type.value, path: '', prompt: '' });
    this.status.set('');
    this.submitted.set(false);
    this.error.set('');
  }

  private finish(): void {
    this.busy.set(false);
    this.form.enable();
  }
}
