import { AutoScrollLogsDirective } from '../../directives/auto-scroll-logs.directive';
import { WoIconComponent } from '../../../theme/icon.component';
import { projectDraftProviders } from '../../services/project-draft.providers';
import { RoutingDraftsService } from '../routing/routing-drafts.service';
import { DatePipe } from '@angular/common';
import { BuilderProjectsService } from '../../services/builder-projects.service';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ChangeDetectionStrategy, Component, computed, DestroyRef, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { WoCardComponent, WoTextInputComponent } from '../../../theme/components';



interface AgentLog { timestamp: string; level: string; event: string; function?: string; step?: string; agent?: string; duration_ms?: number; error_type?: string; }
interface LogSession { id: string; entityId: number; cursor: number; finished: boolean; timer?: ReturnType<typeof setTimeout>; }

interface EntityDraft {
  id: number;
  name: string;
  definition: FormControl<string>;
  attributes?: { name: string; data_type: string; nullable: boolean; description: string }[];
  revision?: number;
  configurationLoading?: boolean;
  configurationError?: boolean;
  logs?: AgentLog[];
  logsError?: string;
  generationError?: string;
  runId?: string;
}

@Component({
  providers: projectDraftProviders,
  imports: [AutoScrollLogsDirective, DatePipe, WoIconComponent, ReactiveFormsModule, WoCardComponent, WoTextInputComponent],
  templateUrl: './entities.component.html',
  styleUrl: './entities.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EntitiesComponent {
  readonly entities = signal<EntityDraft[]>([]);
  readonly selectedId = signal<number | null>(null);
  readonly selectedEntities = computed(() => {
    const entities = this.entities();
    const selected = entities.find(entity => entity.id === this.selectedId()) ?? entities.at(-1);
    return selected ? [selected] : [];
  });
  readonly editingId = signal<number | null>(null);
  readonly deleting = signal<EntityDraft | null>(null);
  @ViewChild('attributeDialog') private attributeDialog!: ElementRef<HTMLDialogElement>;
  @ViewChild('deleteDialog') private deleteDialog!: ElementRef<HTMLDialogElement>;
  private readonly host: ElementRef<HTMLElement> = inject(ElementRef);
  readonly submitted = signal(false);
  readonly announcement = signal('');
  readonly generating = signal<number | null>(null);
  readonly generationError = signal('');
  readonly attributeSaving = signal(false);
  readonly attributeError = signal('');
  readonly editingAttribute = signal<{ entityId: number; index: number } | null>(null);
  readonly attributeTypes = ['string', 'text', 'integer', 'float', 'decimal', 'boolean', 'date', 'datetime', 'uuid', 'json'];
  readonly attributeForm = new FormGroup({
    name: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.pattern(/^[A-Za-z][A-Za-z0-9_]{0,99}$/)] }),
    data_type: new FormControl('string', { nonNullable: true }),
    required: new FormControl(true, { nonNullable: true }),
  });
  readonly name = new FormControl('', {
    nonNullable: true,
    validators: [
      Validators.maxLength(100),
      (control) => !control.value.trim() ? { required: true } : null,
      (control) => this.entities().some(
        (entity) => entity.id !== this.editingId() && entity.name.toLowerCase() === control.value.trim().toLowerCase(),
      ) ? { duplicate: true } : null,
    ],
  });
  readonly createForm = new FormGroup({ name: this.name });
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly loadError = signal(false);
  readonly saveError = signal('');
  private readonly routeDrafts = inject(RoutingDraftsService);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  private readonly projectId = inject(BuilderProjectsService).activeId();
  private readonly projectOptions = { headers: { 'X-Project-ID': String(this.projectId) } };
  private readonly logSessions = new Map<number, LogSession>();

  constructor() {
    this.destroyRef.onDestroy(() => this.logSessions.forEach(session => clearTimeout(session.timer)));
    this.loadEntities();
  }

  loadEntities(): void {
    if (this.loading()) return;
    this.loading.set(true);
    this.loadError.set(false);
    this.http.get<{ entities: { id: number; name: string }[] }>('/api/entities')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ entities }) => {
          this.routeDrafts.ensureEntityRoutes(entities);
          this.entities.set(entities.map((entity) => ({
            ...entity, definition: new FormControl('', { nonNullable: true }),
          })));
          for (const entity of this.entities()) this.loadDefinition(entity);
          this.loading.set(false);
        },
        error: () => {
          this.loadError.set(true);
          this.loading.set(false);
        },
      });
  }

  loadDefinition(entity: EntityDraft): void {
    this.entities.update(items => items.map(item => item.id === entity.id ? { ...item, configurationLoading: true, configurationError: false } : item));
    this.http.get<{ prompt: string; revision: number; attributes: NonNullable<EntityDraft['attributes']> }>(`/api/entity-configurations/${entity.id}`)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (result) => {
          entity.definition.setValue(result.prompt);
          this.entities.update(items => items.map(item => item.id === entity.id ? { ...item, ...result, configurationLoading: false, configurationError: false } : item));
        },
        error: () => {
          this.entities.update(items => items.map(item => item.id === entity.id ? { ...item, configurationLoading: false, configurationError: true } : item));
        },
      });
  }

  generate(entity: EntityDraft): void {
    if (this.generating() !== null || this.attributeSaving() || this.editingAttribute() || entity.configurationLoading || entity.configurationError || !entity.definition.value.trim()) return;
    this.generating.set(entity.id);
    this.generationError.set('');
    clearTimeout(this.logSessions.get(entity.id)?.timer);
    const session: LogSession = { id: crypto.randomUUID(), entityId: entity.id, cursor: 0, finished: false };
    this.logSessions.set(entity.id, session);
    this.entities.update(items => items.map(item => item.id === entity.id ? { ...item, runId: session.id, logs: [], logsError: '', generationError: '' } : item));
    this.readLogs(session);
    this.http.post<{ revision: number; attributes: NonNullable<EntityDraft['attributes']> }>(`/api/entity-configurations/${entity.id}`, {
      prompt: entity.definition.value.trim(), revision: entity.revision ?? 0, run_id: session.id,
    }, this.projectOptions).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => {
        this.entities.update(items => items.map(item => item.id === entity.id ? { ...item, ...result } : item));
        session.finished = true;
        this.generating.set(null);
        this.announcement.set(`${entity.name} configuration generated and saved.`);
      },
      error: (error) => {
        session.finished = true;
        this.generating.set(null);
        this.generationError.set(error.error?.error ?? 'Generation failed. Your prompt and saved attributes are preserved. Retry.');
        this.entities.update(items => items.map(item => item.id === entity.id ? { ...item, generationError: this.generationError() } : item));
      },
    });
  }

  editAttribute(entity: EntityDraft, index: number): void {
    if (this.attributeSaving() || this.generating() !== null) return;
    const attribute = entity.attributes![index];
    this.attributeForm.setValue({ name: attribute.name, data_type: attribute.data_type, required: !attribute.nullable });
    this.attributeError.set('');
    this.editingAttribute.set({ entityId: entity.id, index });
    this.attributeDialog.nativeElement.showModal();
  }

  get attributeEntity(): EntityDraft | undefined {
    return this.entities().find(entity => entity.id === this.editingAttribute()?.entityId);
  }

  cancelAttributeEdit(): void {
    if (this.attributeSaving()) return;
    this.editingAttribute.set(null);
    this.attributeDialog.nativeElement.close();
    this.attributeError.set('');
  }

  saveAttribute(entity: EntityDraft): void {
    const editing = this.editingAttribute();
    if (!editing || editing.entityId !== entity.id || this.attributeSaving()) return;
    this.attributeForm.markAllAsTouched();
    if (this.attributeForm.invalid) return;
    const value = this.attributeForm.getRawValue();
    if (entity.attributes!.some((attribute, index) => index !== editing.index && attribute.name.toLowerCase() === value.name.toLowerCase())) {
      this.attributeError.set('An attribute with that name already exists.');
      return;
    }
    this.persistAttributes(entity, entity.attributes!.map((attribute, index) => index === editing.index
      ? { ...attribute, name: value.name, data_type: value.data_type, nullable: !value.required } : attribute));
  }

  deleteAttribute(entity: EntityDraft, index: number): void {
    if (this.attributeSaving() || this.generating() !== null || this.editingAttribute()) return;
    this.persistAttributes(entity, entity.attributes!.filter((_, position) => position !== index));
  }

  private persistAttributes(entity: EntityDraft, attributes: NonNullable<EntityDraft['attributes']>): void {
    this.attributeSaving.set(true);
    this.attributeForm.disable({ emitEvent: false });
    this.attributeError.set('');
    this.http.put<{ revision: number; attributes: NonNullable<EntityDraft['attributes']> }>(
      `/api/entity-configurations/${entity.id}`, { revision: entity.revision ?? 0, attributes }, this.projectOptions,
    ).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.entities.update(items => items.map(item => item.id === entity.id ? { ...item, ...result } : item));
        this.attributeSaving.set(false);
        this.attributeForm.enable({ emitEvent: false });
        this.editingAttribute.set(null);
        this.attributeDialog.nativeElement.close();
        this.announcement.set(`${entity.name} attributes saved. Build to implement the updated configuration.`);
      },
      error: error => {
        this.attributeSaving.set(false);
        this.attributeForm.enable({ emitEvent: false });
        this.attributeError.set(error.error?.error ?? 'Could not save attribute changes. Your saved attributes are unchanged.');
      },
    });
  }

  private readLogs(session: LogSession): void {
    if (this.logSessions.get(session.entityId) !== session) return;
    const finalRead = session.finished;
    this.http.get<{ entries: AgentLog[]; cursor: number; more: boolean }>(
      `/api/entity-configurations/${session.entityId}/logs/${session.id}?cursor=${session.cursor}`, this.projectOptions,
    ).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        if (this.logSessions.get(session.entityId) !== session) return;
        session.cursor = result.cursor;
        this.entities.update(items => items.map(item => item.id === session.entityId && item.runId === session.id
          ? { ...item, logs: [...(item.logs ?? []), ...result.entries].slice(-200), logsError: '' } : item));
        if (!finalRead || result.more) session.timer = setTimeout(() => this.readLogs(session), result.more ? 0 : 750);
      },
      error: () => {
        if (this.logSessions.get(session.entityId) !== session) return;
        this.entities.update(items => items.map(item => item.id === session.entityId
          ? { ...item, logsError: 'Agent logs are temporarily unavailable.' } : item));
        if (!finalRead) session.timer = setTimeout(() => this.readLogs(session), 1500);
      },
    });
  }

  createEntity(): void {
    if (this.loading() || this.saving()) return;
    this.submitted.set(true);
    this.name.updateValueAndValidity();
    if (this.name.invalid) {
      this.name.markAsTouched();
      return;
    }

    this.saving.set(true);
    this.saveError.set('');
    this.name.disable();
    const editingId = this.editingId();
    const body = { name: this.name.value.trim() };
    const request = editingId === null
      ? this.http.post<{ entity: { id: number; name: string } }>('/api/entities', body)
      : this.http.put<{ entity: { id: number; name: string } }>(`/api/entities/${editingId}`, body);
    request.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: ({ entity }) => {
        if (editingId !== null) {
          const previous = this.entities().find((item) => item.id === editingId)!;
          this.routeDrafts.renameEntity(previous.name, entity.name);
          this.entities.update((entities) => entities.map((item) => item.id === editingId ? { ...item, name: entity.name } : item));
        } else {
          this.routeDrafts.ensureEntityRoutes([entity]);
          this.entities.update((entities) => [...entities, {
            ...entity, definition: new FormControl('', { nonNullable: true }),
          }]);
        }
        this.selectedId.set(entity.id);
        this.editingId.set(null);
        this.name.reset();
        this.name.enable();
        this.saving.set(false);
        this.submitted.set(false);
        this.announcement.set(`${entity.name} saved. Add its entity definition below.`);
      },
      error: (error) => {
        this.saveError.set(error.status === 409
          ? 'An entity with this name already exists.'
          : 'Could not save the entity. Your name is still here; try again.');
        this.name.enable();
        this.saving.set(false);
      },
    });
  }

  selectEntity(entity: EntityDraft): void {
    if (this.saving()) return;
    this.cancelEdit();
    this.selectedId.set(entity.id);
  }

  editEntity(entity: EntityDraft): void {
    if (this.saving()) return;
    this.selectedId.set(entity.id);
    this.editingId.set(entity.id);
    this.name.setValue(entity.name);
    this.submitted.set(false);
    this.saveError.set('');
    this.host.nativeElement.querySelector<HTMLInputElement>('#entity-name')?.focus();
  }

  cancelEdit(): void {
    this.editingId.set(null);
    this.name.reset();
    this.submitted.set(false);
    this.saveError.set('');
  }

  confirmDelete(entity: EntityDraft): void {
    this.deleting.set(entity);
    this.saveError.set('');
    this.deleteDialog.nativeElement.showModal();
  }

  deleteEntity(): void {
    const entity = this.deleting();
    if (!entity || this.saving()) return;
    this.saving.set(true);
    this.http.delete(`/api/entities/${entity.id}`).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.routeDrafts.removeEntity(entity);
        this.entities.update((entities) => entities.filter((item) => item.id !== entity.id));
        if (this.editingId() === entity.id) this.cancelEdit();
        this.name.updateValueAndValidity();
        this.saving.set(false);
        this.deleting.set(null);
        this.deleteDialog.nativeElement.close();
        this.announcement.set(`${entity.name} deleted.`);
      },
      error: () => {
        this.saving.set(false);
        this.saveError.set('Could not delete the entity. Try again.');
      },
    });
  }

}
