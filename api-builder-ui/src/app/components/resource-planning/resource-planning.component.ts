import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, computed, effect, inject, signal, untracked, viewChild } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { timeout } from 'rxjs';
import { Vflow, VflowComponent } from 'ngx-vflow';
import { WoCardComponent } from '../../../theme/components';
import { BuilderProjectsService } from '../../services/builder-projects.service';
import { SelectComponent } from '../select/select.component';
import { InfrastructureEntity, InfrastructureProposal, infrastructureGraph } from './infrastructure.model';

@Component({
  imports: [WoCardComponent, FormsModule, SelectComponent, Vflow],
  templateUrl: './resource-planning.component.html',
  styleUrl: './resource-planning.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ResourcePlanningComponent {
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  readonly state = inject(BuilderProjectsService).scope(ResourcePlanningComponent, () => ({
    environment: signal('dev'), requirements: '', proposal: signal<InfrastructureProposal | null>(null), generatedFor: '',
  }));
  readonly proposalNeedsRefresh = signal(!!this.state.proposal());
  readonly platforms = [{ value: 'aws', label: 'Amazon Web Services' }];
  readonly modes = [{ value: 'serverless', label: 'Serverless deployment' }, { value: 'containerized', label: 'Containerized deployment', disabled: true }];
  readonly environments = [{ value: 'dev', label: 'Development' }, { value: 'staging', label: 'Staging' }, { value: 'prod', label: 'Production' }];
  readonly entities = signal<InfrastructureEntity[]>([]);
  readonly loading = signal(false);
  readonly loadError = signal('');
  readonly busy = signal(false);
  readonly error = signal('');
  readonly status = signal('');
  readonly selectedId = signal('cloudfront');
  readonly flow = viewChild(VflowComponent);
  private readonly canvas = viewChild<ElementRef<HTMLElement>>('canvas');
  readonly graph = computed(() => infrastructureGraph(this.entities(), this.state.environment(), this.state.proposal()));
  readonly selected = computed(() => this.graph().resources.find(resource => resource.id === this.selectedId()) ?? this.graph().resources[0]);
  readonly connections = computed(() => this.graph().relationships.filter(edge => edge.source === this.selected().id || edge.target === this.selected().id));
  readonly includedCount = computed(() => this.graph().resources.filter(resource => resource.status === 'Included').length);
  readonly connectionSettings = { validator: () => false };
  get changedSinceProposal() { return this.state.proposal() && (this.proposalNeedsRefresh() || this.state.generatedFor !== this.requestKey()); }

  constructor() {
    this.loadEntities();
    effect((onCleanup) => {
      const canvas = this.canvas()?.nativeElement;
      const flow = this.flow();
      if (!canvas || !flow || typeof ResizeObserver === 'undefined') return;
      let frame = 0;
      const observer = new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => flow.fitView({ padding: 0.08 }));
      });
      observer.observe(canvas);
      onCleanup(() => { observer.disconnect(); cancelAnimationFrame(frame); });
    });
    effect((onCleanup) => {
      this.graph();
      const flow = this.flow();
      if (!flow?.initialized()) return;
      const frame = requestAnimationFrame(() => untracked(() => flow.fitView({ padding: 0.08 })));
      onCleanup(() => cancelAnimationFrame(frame));
    });
  }

  loadEntities(): void {
    if (this.loading() || this.busy()) return;
    this.loading.set(true);
    this.loadError.set('');
    this.http.get<{ entities: InfrastructureEntity[] }>('/api/entities').pipe(timeout(15000), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: ({ entities }) => { this.entities.set(entities); this.loading.set(false); },
      error: () => { this.loadError.set('Could not load entities. Retry to build the complete resource plan.'); this.loading.set(false); },
    });
  }

  generate(): void {
    if (this.busy() || this.loading() || this.loadError()) return;
    if (this.state.requirements.length > 4000) { this.error.set('Keep requirements under 4,000 characters.'); return; }
    this.busy.set(true);
    this.error.set('');
    this.status.set('The agent is drafting and reviewing your infrastructure…');
    const key = this.requestKey();
    this.http.post<{ proposal: InfrastructureProposal }>('/api/generate-infrastructure-plan', {
      platform: 'aws', deployment_mode: 'serverless', environment: this.state.environment(), requirements: this.state.requirements.trim(),
    }).pipe(timeout(240000), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: ({ proposal }) => {
        this.state.proposal.set(proposal);
        this.state.generatedFor = key;
        this.proposalNeedsRefresh.set(false);
        this.busy.set(false);
        this.status.set('Proposal ready for review. No AWS resources have been created.');
      },
      error: () => {
        this.busy.set(false);
        this.status.set('');
        this.error.set('Could not generate a proposal. Check the backend and local agent sign-in, then retry. Your inputs and previous proposal are preserved.');
      },
    });
  }

  fit(): void { this.flow()?.fitView({ padding: 0.08 }); }
  zoom(factor: number): void { const flow = this.flow(); if (flow) flow.zoomTo(Math.max(0.2, Math.min(1.8, flow.viewport().zoom * factor))); }
  select(id: string): void { this.selectedId.set(id); }
  resourceName(id: string): string { const resource = this.graph().resources.find(item => item.id === id); return resource ? `${resource.service} · ${resource.name}` : id; }
  private requestKey(): string { return JSON.stringify([this.state.environment(), this.state.requirements.trim(), this.entities()]); }
}
