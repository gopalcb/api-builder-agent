import { WoIconComponent } from '../../../theme/icon.component';
import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, ElementRef, HostListener, ViewChild } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { WoCardComponent, WoSpinnerComponent, WoTextInputComponent } from '../../../theme/components';
import { ProjectActionsService } from '../../services/project-actions.service';
import { BuilderProject, BuilderProjectsService } from '../../services/builder-projects.service';

@Component({
  imports: [WoIconComponent, ReactiveFormsModule, WoCardComponent, WoSpinnerComponent, WoTextInputComponent],
  templateUrl: './projects.component.html',
  styleUrl: './projects.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProjectsComponent {
  readonly store = inject(BuilderProjectsService);
  readonly actions = inject(ProjectActionsService);
  readonly editing = signal<number | null>(null);
  readonly openMenu = signal<number | null>(null);
  readonly deleteTarget = signal<BuilderProject | null>(null);
  readonly githubTarget = signal<BuilderProject | null>(null);
  readonly githubSubmitted = signal(false);
  readonly showToken = signal(false);
  @ViewChild('deleteDialog') deleteDialog!: ElementRef<HTMLDialogElement>;
  @ViewChild('githubDialog') githubDialog!: ElementRef<HTMLDialogElement>;
  @ViewChild('projectForm') projectForm!: ElementRef<HTMLFormElement>;
  readonly githubForm = new FormGroup({
    owner: new FormControl('', {nonNullable: true, validators: [Validators.pattern('[A-Za-z0-9][A-Za-z0-9-]{0,38}')]}),
    name: new FormControl('', {nonNullable: true, validators: [Validators.required, Validators.pattern('[A-Za-z0-9][A-Za-z0-9._-]{0,99}')]}),
    token: new FormControl('', {nonNullable: true, validators: [Validators.required, Validators.maxLength(1000)]}),
    create: new FormControl(true, {nonNullable: true}),
  });
  readonly submitted = signal(false);
  readonly saving = signal(false);
  readonly announcement = signal('');
  readonly busy = computed(() => this.store.loading() || this.saving() || this.actions.busy());
  readonly name = new FormControl('', {
    nonNullable: true,
    validators: [
      Validators.maxLength(100),
      (control) => !control.value.trim() ? { required: true } : null,
      (control) => this.store.projects().some(
        (project) => project.id !== this.editing() && project.name.toLowerCase() === control.value.trim().toLowerCase(),
      ) ? { duplicate: true } : null,
    ],
  });
  readonly summary = new FormControl('', {
    nonNullable: true,
    validators: [
      Validators.maxLength(4000),
      (control) => !control.value.trim() ? { required: true } : null,
    ],
  });
  readonly form = new FormGroup({ name: this.name, summary: this.summary });

  constructor() {
    effect(() => {
      if (this.busy()) this.form.disable();
      else this.form.enable();
    });
    void this.store.load();
  }

  async saveProject(): Promise<void> {
    if (this.busy()) return;
    this.submitted.set(true);
    this.name.updateValueAndValidity();
    this.form.markAllAsTouched();
    if (this.form.invalid) return;

    const name = this.name.value.trim();
    this.saving.set(true);
    const id = this.editing();
    const saved = id === null ? await this.store.create(name, this.summary.value.trim()) : await this.store.update(id, name, this.summary.value.trim());
    this.saving.set(false);
    if (!saved) return;

    this.editing.set(null);
    this.form.reset();
    this.submitted.set(false);
    this.announcement.set(`${name} saved.`);
  }

  async selectProject(id: number): Promise<void> {
    if (this.busy()) return;
    const activated = await this.store.activate(id);
    this.announcement.set(activated
      ? `${this.store.activeProject()?.name} is now active and running.`
      : 'The project was selected, but its API could not be started.');
  }

  editProject(project: BuilderProject): void {
    if (this.busy()) return;
    this.openMenu.set(null);
    this.editing.set(project.id);
    this.form.setValue({name: project.name, summary: project.summary});
    this.submitted.set(false);
    this.projectForm.nativeElement.scrollIntoView({block: 'nearest'});
    this.projectForm.nativeElement.querySelector<HTMLInputElement>('input')?.focus();
  }

  cancelEdit(): void {
    this.editing.set(null);
    this.form.reset();
    this.submitted.set(false);
  }

  askDelete(project: BuilderProject): void {
    this.openMenu.set(null);
    this.deleteTarget.set(project);
    this.deleteDialog.nativeElement.showModal();
  }

  async deleteProject(): Promise<void> {
    const project = this.deleteTarget();
    if (!project || this.busy()) return;
    if (!await this.store.remove(project.id)) return;
    if (this.editing() === project.id) this.cancelEdit();
    this.deleteDialog.nativeElement.close();
    this.deleteTarget.set(null);
    this.announcement.set(`${project.name} deleted.`);
  }

  openGithub(project: BuilderProject): void {
    this.openMenu.set(null);
    this.githubTarget.set(project);
    this.githubSubmitted.set(false);
    this.showToken.set(false);
    this.githubForm.reset({owner: project.repository?.owner ?? '', name: project.repository?.name ?? (project.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0,32) || 'api-project'), token: '', create: !project.repository});
    this.githubDialog.nativeElement.showModal();
  }

  closeGithub(): void {
    if (this.actions.busy()) return;
    this.githubForm.controls.token.reset('');
    this.githubDialog.nativeElement.close();
    this.githubTarget.set(null);
  }

  async configureGithub(): Promise<void> {
    const project = this.githubTarget();
    if (!project || this.busy()) return;
    this.githubSubmitted.set(true);
    this.githubForm.markAllAsTouched();
    if (this.githubForm.invalid) return;
    const successful = await this.actions.publish(project, this.githubForm.getRawValue());
    this.githubForm.controls.token.reset('');
    if (successful) this.closeGithub();
  }

  @HostListener('document:keydown.escape')
  closeMenu(): void { this.openMenu.set(null); }

  @HostListener('document:click', ['$event'])
  dismissMenu(event: MouseEvent): void {
    if (!(event.target instanceof Element) || !event.target.closest('.project-more')) this.openMenu.set(null);
  }

}
