import { LocalConnectionService } from '../../services/local-connection.service';
import { DatePipe } from '@angular/common';
import { AutoScrollLogsDirective } from '../../directives/auto-scroll-logs.directive';
import { Component, ElementRef, ViewChild, computed, inject } from '@angular/core';
import { BuilderProjectsService } from '../../services/builder-projects.service';
import { ProjectActionsService } from '../../services/project-actions.service';
import { WoIconComponent } from '../../../theme/icon.component';

@Component({
  selector: 'app-project-build-actions',
  imports: [WoIconComponent, DatePipe, AutoScrollLogsDirective],
  templateUrl: './project-build-actions.component.html',
  styleUrl: './project-build-actions.component.css',
  styles: [':host { display: block; min-width: 0; } .project-build-actions { display: flex; justify-content: center; gap: 8px; } .project-swagger-link { display: inline-flex; gap: 4px; align-items: center; border: 1px solid var(--wo-border); border-radius: 4px; background: white; color: var(--wo-ink); text-decoration: none; } .project-build-notice { max-width: 360px; text-align: center; font-size: 11px; margin: 8px 0 0; }'],
})
export class ProjectBuildActionsComponent {
  private readonly workflowDefinition = [
    { label: 'Create plan', match: (events: string[]) => events.some(event => event.startsWith('build.render.')) },
    { label: 'Split work', match: (events: string[]) => events.includes('build.render.completed') || events.some(event => event.startsWith('build.agent_implementation.')) },
    { label: 'Delegate parallel agents', match: (events: string[]) => events.some(event => event.startsWith('build.agent_implementation.')) || events.some(event => event.startsWith('build.validate_and_test.')) },
    { label: 'Loop: test', match: (events: string[]) => events.includes('build.runtime_tests_checked') },
    { label: 'Loop: build', match: (events: string[]) => events.some(event => event.startsWith('build.archive.')) || events.some(event => event.startsWith('build.persist.')) },
    { label: 'Loop: validate', match: (events: string[]) => events.includes('build.syntax_validated') || events.includes('build.health_checked') || events.includes('build.runtime_tests_checked') },
    { label: 'Create documents', match: (events: string[]) => events.includes('build.render.completed') },
  ] as const;

  @ViewChild('logsDialog') private logsDialog!: ElementRef<HTMLDialogElement>;
  shownProjectId: number | null = null;
  shownProjectName = '';
  readonly workflowSteps = computed(() => {
    const projectId = this.actions.logProjectId();
    const result = this.actions.results()[projectId ?? 0];
    const events = this.actions.buildLogs().map(entry => entry.event);
    const allComplete = result?.status === 'success';
    const completed = this.workflowDefinition.map(step => allComplete || step.match(events));
    const activeIndex = result?.status === 'running' ? completed.findIndex(done => !done) : -1;

    return this.workflowDefinition.map((step, index) => ({
      label: step.label,
      completed: completed[index],
      active: index === activeIndex,
    }));
  });

  openLogs(): void {
    const project = this.projects.activeProject();
    if (!project) return;
    this.shownProjectId = project.id;
    this.shownProjectName = project.name;
    this.logsDialog.nativeElement.showModal();
  }

  run(operation: 'build' | 'test'): void {
    const project = this.projects.activeProject();
    if (!project || this.actions.busy()) return;
    this.openLogs();
    void this.actions.run(project, operation);
  }

  readonly connection = inject(LocalConnectionService);
  readonly projects = inject(BuilderProjectsService);
  readonly actions = inject(ProjectActionsService);
}
