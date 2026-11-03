import { WoIconComponent } from '../../../theme/icon.component';
import { RouteType, routeTypes, isSearchRouteType } from '../../interfaces/route-type.interface';
import { projectDraftProviders } from '../../services/project-draft.providers';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { WoCardComponent, WoTextInputComponent } from '../../../theme/components';
import { SelectComponent } from '../select/select.component';
import {
  normalizeRoutePath, RouteDraft, RouteOperation, operationMethods, routeShape, RoutingDraftsService,
} from './routing-drafts.service';

@Component({
  providers: projectDraftProviders,
  imports: [WoIconComponent, ReactiveFormsModule, WoCardComponent, WoTextInputComponent, SelectComponent],
  templateUrl: './routing.component.html',
  styleUrl: './routing.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RoutingComponent {
  readonly store = inject(RoutingDraftsService);
  readonly routes = this.store.routes;
  readonly groups = computed(() => {
    const groups = new Map<string, RouteDraft[]>();
    for (const route of this.routes()) {
      const entries = groups.get(route.entity) ?? [];
      entries.push(route);
      groups.set(route.entity, entries);
    }
    return Array.from(groups, ([entity, routes]) => ({ entity, routes }));
  });
  readonly editingId = signal<number | null>(null);
  readonly submitted = signal(false);
  readonly announcement = signal('');
  readonly typeOptions = routeTypes;
  readonly entity = new FormControl('', { nonNullable: true, validators: [Validators.required] });
  readonly entityOptions = computed(() => this.store.entityNames().map(value => ({ value, label: value })));
  readonly operationOptions = Object.keys(operationMethods).map(value => ({ value, label: value[0].toUpperCase() + value.slice(1) }));
  readonly operation = new FormControl<RouteOperation>('create', { nonNullable: true });
  readonly routeType = new FormControl<RouteType>('authenticated', { nonNullable: true });
  readonly path = new FormControl('', {
    nonNullable: true,
    validators: [(control) => this.validatePath(control.value)],
  });
  readonly prompt = new FormControl('', { nonNullable: true, validators: [Validators.maxLength(4000)] });
  readonly form = new FormGroup({ entity: this.entity, type: this.routeType, path: this.path, prompt: this.prompt });

  constructor() {
    this.store.loadEntities();
  }

  get pathError(): string {
    if (this.path.hasError('required')) return 'Route path is required.';
    if (this.path.hasError('searchFormat')) return 'Search routes use letters, numbers, hyphens or underscores, for example /products/search.';
    if (this.path.hasError('duplicate')) return 'A route with this path already exists.';
    return 'Use letters, numbers, hyphens, underscores and optional {id}, for example /product/{id}/sell.';
  }

  readonly isSearchType = isSearchRouteType;

  typeLabel(type: RouteType): string { return routeTypes.find(option => option.value === type)!.label; }

  setType(value: string): void {
    if (routeTypes.some(option => option.value === value)) {
      this.routeType.setValue(value as RouteType);
      this.path.updateValueAndValidity();
    }
  }

  async saveRoute(): Promise<void> {
    if (this.store.loading() || this.store.saving()) return;
    this.submitted.set(true);
    this.path.updateValueAndValidity();
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const original = this.routes().find((route) => route.id === this.editingId());
    const path = normalizeRoutePath(this.path.value);
    const prefix = path.split('/')[1];
    const entity = this.entity.value || original?.entity || this.routes().find((route) => route.path.split('/')[1] === prefix && route.entity)?.entity || '';
    const previous = this.routes();
    this.store.save({
      operation: isSearchRouteType(this.routeType.value) ? null : this.operation.value,
      method: isSearchRouteType(this.routeType.value) ? 'POST' : operationMethods[this.operation.value],
      path, entity, type: this.routeType.value,
      access: this.routeType.value === 'public' ? 'public' : this.routeType.value === 'authenticated' ? 'authenticated' : original?.access ?? 'authenticated',
      prompt: this.prompt.value.trim(),
    }, this.editingId());
    this.form.disable();
    const saved = await this.store.persist();
    this.form.enable();
    if (!saved) { this.store.restore(previous); return; }
    this.cancelEdit();
    this.announcement.set(`${original ? 'Updated' : 'Added'} endpoint ${path}. Saved.`);
  }

  editRoute(route: RouteDraft): void {
    this.editingId.set(route.id);
    this.entity.setValue(route.entity);
    this.operation.setValue(route.operation ?? 'create');
    this.form.reset({ entity: route.entity, type: route.type, path: route.path, prompt: route.prompt });
    this.path.updateValueAndValidity();
    this.submitted.set(false);
    this.announcement.set(`Editing endpoint ${route.path}.`);
  }

  cancelEdit(): void {
    this.editingId.set(null);
    this.form.reset({ type: 'authenticated', path: '', prompt: '' });
    this.entity.setValue('');
    this.operation.setValue('create');
    this.submitted.set(false);
  }

  async removeRoute(route: RouteDraft): Promise<void> {
    if (this.store.loading() || this.store.saving()) return;
    const previous = this.routes();
    this.store.remove(route.id);
    if (!await this.store.persist()) { this.store.restore(previous); return; }
    if (this.editingId() === route.id) this.cancelEdit();
    this.path.updateValueAndValidity();
    this.announcement.set(`Removed endpoint ${route.path}.`);
  }

  private validatePath(value: string): Record<string, boolean> | null {
    const path = value.trim();
    if (!path) return { required: true };
    if (path.length > 250 || !/^\/(?:[A-Za-z0-9_-]+|\{id\})(?:\/(?:[A-Za-z0-9_-]+|\{id\}))*\/?$/.test(path)) return { format: true };
    if (isSearchRouteType(this.routeType.value) && !/^\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+$/.test(normalizeRoutePath(path))) return { searchFormat: true };
    if (this.routes().some((route) => route.id !== this.editingId() && routeShape(route.path) === routeShape(path))) return { duplicate: true };
    return null;
  }
}
