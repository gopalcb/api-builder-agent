import { Component, Input, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ProjectActionsService } from '../../services/project-actions.service';
import { BuilderProjectsService } from '../../services/builder-projects.service';
import { LocalSettingsComponent } from '../local-settings/local-settings.component';
import { SelectComponent } from '../select/select.component';

@Component({
  selector: 'app-project-selector',
  imports: [SelectComponent, LocalSettingsComponent],
  templateUrl: './project-selector.component.html',
  styles: [':host { display: flex; align-items: center; gap: 8px; width: 320px; max-width: 100%; min-width: 0; } wo-select { flex: 1; min-width: 0; }'],
})
export class ProjectSelectorComponent {
  readonly projects = inject(BuilderProjectsService);
  readonly actions = inject(ProjectActionsService);
  private readonly router = inject(Router);
  @Input() disabled = false;
  @Input() onSelect?: (value: string) => Promise<void>;
  readonly changing = signal(false);
  readonly options = computed(() => this.projects.orderedProjects().map(project => ({ value: String(project.id), label: project.name })));
  readonly value = computed(() => String(this.projects.activeId() ?? ''));

  async choose(value: string): Promise<void> {
    if (this.changing() || this.disabled || value === this.value()) return;
    this.changing.set(true);
    try {
      if (this.onSelect) { await this.onSelect(value); return; }
      const route = this.router.url;
      if (route.startsWith('/api-builder/projects')) { this.projects.select(Number(value)); return; }
      if (!await this.router.navigateByUrl('/api-builder/projects', { skipLocationChange: true })) return;
      this.projects.select(Number(value));
      await this.router.navigateByUrl(route, { replaceUrl: true });
    } finally { this.changing.set(false); }
  }
}
