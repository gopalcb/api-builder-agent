import { Component, ElementRef, Input, ViewChild, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { WoSpinnerComponent, WoTextInputComponent } from '../../../theme/components';
import { WoIconComponent } from '../../../theme/icon.component';
import { DEFAULT_CONNECTION, LocalConnection, LocalConnectionService } from '../../services/local-connection.service';
import { BuilderProjectsService } from '../../services/builder-projects.service';
import { ProjectActionsService } from '../../services/project-actions.service';

@Component({
  selector: 'app-local-settings',
  imports: [ReactiveFormsModule, WoTextInputComponent, WoSpinnerComponent, WoIconComponent],
  templateUrl: './local-settings.component.html',
  styleUrl: './local-settings.component.css',
})
export class LocalSettingsComponent {
  readonly connection = inject(LocalConnectionService);
  readonly projects = inject(BuilderProjectsService);
  readonly actions = inject(ProjectActionsService);
  @Input() disabled = false;
  @ViewChild('dialog', { static: true }) dialog!: ElementRef<HTMLDialogElement>;
  @ViewChild('trigger', { static: true }) trigger!: ElementRef<HTMLButtonElement>;
  readonly busy = signal(false);
  readonly saving = signal(false);
  readonly submitted = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly discard = signal(false);
  readonly runningApi = signal(false);
  readonly form = new FormGroup({
    direct: new FormControl(false, { nonNullable: true }),
    port: new FormControl('5000', { nonNullable: true }),
  });
  private initial = { direct: false, port: '5000' };

  constructor() {
    this.form.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => {
      this.error.set('');
      this.notice.set('');
      this.discard.set(false);
      this.form.controls.port.setValidators(this.form.controls.direct.value
        ? [Validators.required, Validators.pattern(/^[0-9]+$/), Validators.min(1), Validators.max(65535)] : []);
      this.form.controls.port.updateValueAndValidity({ emitEvent: false });
    });
  }

  open(): void {
    if (this.disabled || this.busy()) return;
    const settings = this.connection.settings();
    this.initial = { direct: settings.direct, port: String(settings.port) };
    this.form.reset(this.initial);
    this.submitted.set(false);
    this.discard.set(false);
    this.dialog.nativeElement.showModal();
  }

  candidate(): LocalConnection {
    return { direct: this.form.controls.direct.value, port: Number(this.form.controls.port.value) };
  }

  address(): string {
    try { return this.connection.address(this.candidate()); }
    catch { return 'Enter a valid local port.'; }
  }

  reset(): void {
    this.form.reset({ direct: DEFAULT_CONNECTION.direct, port: String(DEFAULT_CONNECTION.port) });
    this.submitted.set(false);
  }

  async runCurrentApi(): Promise<void> {
    const project = this.projects.activeProject();
    if (!project || this.busy() || this.runningApi()) return;
    this.runningApi.set(true);
    this.busy.set(true);
    this.error.set('');
    this.notice.set('');
    try {
      const message = await this.actions.runCurrent(project);
      if (message) this.notice.set(message);
      else this.error.set(this.actions.errors()[project.id] || 'Could not start the current API.');
    } finally {
      this.busy.set(false);
      this.runningApi.set(false);
    }
  }

  requestClose(): void {
    if (this.busy()) return;
    const current = this.form.getRawValue();
    if (current.direct !== this.initial.direct || current.port !== this.initial.port) {
      this.discard.set(true);
      return;
    }
    this.close();
  }

  close(): void {
    this.dialog.nativeElement.close();
    this.trigger.nativeElement.focus();
  }

  async test(save = false): Promise<void> {
    if (this.busy()) return;
    this.submitted.set(true);
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      this.dialog.nativeElement.querySelector<HTMLInputElement>('#local-backend-port')?.focus();
      return;
    }
    this.busy.set(true);
    this.saving.set(save);
    this.error.set('');
    this.notice.set('');
    this.discard.set(false);
    try {
      if (save) await this.connection.apply(this.candidate());
      else {
        await this.connection.check(this.candidate());
        this.notice.set('Connected to API Builder. These settings have not been saved.');
      }
    } catch (error) {
      this.error.set(error instanceof Error && error.name === 'Error' ? error.message
        : 'Could not connect. Check that API Builder is running at this address, then try again.');
    } finally { this.busy.set(false); this.saving.set(false); }
  }
}
