import { DatePipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { WoCardComponent } from '../../../theme/components';
import { BuilderProjectsService } from '../../services/builder-projects.service';
import { ProjectActivitiesService } from '../../services/project-activities.service';
@Component({
  imports: [DatePipe, WoCardComponent],
  templateUrl: './project-activities.component.html',
  styles: [':host { display: block; } .activity-row { display: grid; grid-template-columns: 160px 1fr 100px; gap: 16px; padding: 12px; background: white; border: 1px solid var(--wo-border); border-radius: 4px; font-size: 11px; } .activity-status { text-align: right; text-transform: capitalize; } time { color: var(--wo-muted); }'],
})
export class ProjectActivitiesComponent {
  readonly activities = inject(ProjectActivitiesService);
  readonly projects = inject(BuilderProjectsService);
  readonly entries = computed(() => this.activities.entries().filter(entry => entry.projectId === this.projects.activeId()));
}
