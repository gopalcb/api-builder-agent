import { WoIconComponent } from '../../../theme/icon.component';
import { projectDraftProviders } from '../../services/project-draft.providers';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Observable, timeout } from 'rxjs';
import { WoCardComponent, WoTextInputComponent, WoSpinnerComponent } from '../../../theme/components';
import { SelectComponent } from '../select/select.component';
import { AuthenticationDraftsService } from '../authentication/authentication-drafts.service';
import { RoutingDraftsService } from '../routing/routing-drafts.service';
import { RbacConfiguration, RbacRole, RbacService, emptyConfiguration } from './rbac.service';

@Component({
  providers: projectDraftProviders,
  selector: 'app-rbac',
  imports: [WoIconComponent, FormsModule, ReactiveFormsModule, WoCardComponent, WoTextInputComponent, WoSpinnerComponent, SelectComponent],
  templateUrl: './rbac.component.html', styleUrl: './rbac.component.css',
})
export class RbacComponent {
  private readonly api = inject(RbacService);
  private readonly destroyRef = inject(DestroyRef);
  readonly routing = inject(RoutingDraftsService);
  readonly authentication = inject(AuthenticationDraftsService);
  readonly configuration = signal<RbacConfiguration>(emptyConfiguration());
  readonly revision = signal(0);
  readonly busy = signal('');
  readonly loaded = signal(false);
  readonly error = signal('');
  readonly announcement = signal('');
  readonly baseline = signal('');
  readonly importedSource = signal<string | null>(null);
  readonly reloadRequested = signal(false);
  readonly prompt = new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(4000)] });
  readonly roleName = new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.pattern(/^[a-z][a-z0-9_-]{0,39}$/)] });
  readonly groupName = new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.pattern(/^[A-Za-z0-9_-]{1,64}$/)] });
  readonly submittedRole = signal(false);
  readonly selectedRoles = signal<string[]>([]);
  readonly previewRoute = signal('');
  readonly decision = signal('');
  readonly methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'].map(value => ({ value, label: value }));
  readonly dirty = computed(() => JSON.stringify(this.configuration()) !== this.baseline());
  readonly sourceFingerprint = computed(() => JSON.stringify({ routes: this.routing.routes(), identity: this.authentication.saved()['cognito'] ?? null }));
  readonly sourceChanged = computed(() => this.importedSource() !== null && this.importedSource() !== this.sourceFingerprint());
  readonly routeOptions = computed(() => this.configuration().routes.filter(route => route.method).map(route => ({ value: route.key, label: route.key })));
  readonly unresolved = computed(() => this.configuration().routes.some(route => !route.method));
  readonly canExport = computed(() => this.loaded() && this.revision() > 0 && !this.busy() && !this.dirty() && !this.sourceChanged()
    && !this.unresolved() && !this.configuration().questions.length && this.configuration().routes.length > 0);

  constructor() {
    const session = this.api.session;
    if (session) {
      this.configuration.set(session.configuration);
      this.revision.set(session.revision);
      this.baseline.set(session.baseline);
      this.importedSource.set(session.importedSource);
      this.prompt.setValue(session.prompt);
      this.roleName.setValue(session.roleName); this.groupName.setValue(session.groupName);
      this.submittedRole.set(session.submittedRole); this.error.set(session.error); this.announcement.set(session.announcement);
      this.loaded.set(true);
    } else this.load();
    this.destroyRef.onDestroy(() => {
      if (this.loaded()) this.api.session = {
        configuration: this.configuration(), revision: this.revision(), baseline: this.baseline(),
        importedSource: this.importedSource(), prompt: this.prompt.value,
        roleName: this.roleName.value, groupName: this.groupName.value, submittedRole: this.submittedRole(),
        error: this.error(), announcement: this.announcement(),
      };
    });
  }

  load(): void {
    this.perform(this.api.load(), 'Loading configuration', snapshot => {
      const configuration = snapshot.configuration ?? emptyConfiguration();
      this.configuration.set(configuration);
      this.revision.set(snapshot.revision);
      this.baseline.set(JSON.stringify(configuration));
      this.loaded.set(true);
      this.importedSource.set(null);
      this.reloadRequested.set(false);
      this.decision.set('');
    });
  }

  requestReload(): void {
    if (this.dirty()) this.reloadRequested.set(true);
    else this.load();
  }

  change(update: Partial<RbacConfiguration>): void {
    this.configuration.update(value => ({ ...value, ...update }));
    this.decision.set('');
    this.announcement.set('Unsaved changes');
  }

  setIdentity(field: 'user_pool_id' | 'client_id', value: string): void {
    this.change({ identity: { ...this.configuration().identity, [field]: value.trim() } });
  }

  importDrafts(): void {
    const auth = this.authentication.saved()['cognito'];
    const current = this.configuration();
    const routes = this.routing.routes().map(route => {
      const retained = current.routes.find(item => item.path === route.path);
      const method = route.method ?? retained?.method ?? '';
      return { key: `${method} ${route.path}`, method, path: route.path, access: route.access };
    });
    const grants = current.grants.filter(grant => routes.some(route => route.key === grant.route && route.access !== 'public'));
    this.change({ routes, grants, cases: [], identity: auth ? {
      provider: 'cognito', user_pool_id: auth['issuer'].split('/').pop() ?? '', client_id: auth['clientId'],
    } : current.identity });
    this.importedSource.set(this.sourceFingerprint());
    this.announcement.set('Imported current drafts. Review permissions and save this snapshot.');
  }

  setMethod(index: number, method: string): void {
    const routes = this.configuration().routes.map((route, position) => position === index ? { ...route, method, key: `${method} ${route.path}` } : route);
    this.change({ routes, grants: this.configuration().grants.filter(grant => routes.some(route => route.key === grant.route)), cases: [] });
  }

  addRole(): void {
    this.submittedRole.set(true);
    if (this.roleName.invalid || this.groupName.invalid) return;
    const id = this.roleName.value;
    const group = this.groupName.value;
    if (this.configuration().roles.some(role => role.id === id || role.group === group)) {
      this.error.set('Role IDs and group names must be unique.');
      return;
    }
    this.change({ roles: [...this.configuration().roles, { id, group, description: '', create_group: false }] });
    this.roleName.reset(); this.groupName.reset(); this.submittedRole.set(false); this.error.set('');
  }

  updateRole(index: number, field: 'description' | 'group' | 'create_group', value: string | boolean): void {
    const roles = this.configuration().roles.map((role, position) => position === index ? { ...role, [field]: value } as RbacRole : role);
    this.change({ roles });
  }

  removeRole(id: string): void {
    const configuration = this.configuration();
    this.change({ roles: configuration.roles.filter(role => role.id !== id), grants: configuration.grants.filter(grant => grant.role !== id), cases: [] });
    this.selectedRoles.update(roles => roles.filter(role => role !== id));
  }

  hasGrants(route: string): boolean { return this.configuration().grants.some(grant => grant.route === route); }

  granted(role: string, route: string): boolean { return this.configuration().grants.some(grant => grant.role === role && grant.route === route); }
  toggleGrant(role: string, route: string, checked: boolean): void {
    const grants = this.configuration().grants.filter(grant => !(grant.role === role && grant.route === route));
    if (checked) grants.push({ role, route });
    this.change({ grants, cases: [] });
  }
  selectPreviewRole(role: string, checked: boolean): void {
    this.selectedRoles.update(roles => checked ? [...roles, role] : roles.filter(value => value !== role));
    this.decision.set('');
  }
  setPreviewRoute(route: string): void { this.previewRoute.set(route); this.decision.set(''); }

  resolveQuestion(index: number): void { this.change({ questions: this.configuration().questions.filter((_, position) => position !== index) }); }

  ready(): boolean {
    if (this.unresolved()) { this.error.set('Select an HTTP method for every imported route.'); return false; }
    if (this.sourceChanged()) { this.error.set('Source drafts changed. Import them again and review permissions.'); return false; }
    return true;
  }

  generate(): void {
    this.prompt.markAsTouched();
    if (this.prompt.invalid || !this.prompt.value.trim() || !this.ready()) return;
    this.perform(this.api.generate(this.configuration(), this.revision(), this.prompt.value), 'Generating proposal', snapshot => {
      this.change(snapshot.configuration!);
      this.announcement.set('Proposal ready. Review roles and grants before saving.');
    });
  }

  save(): void {
    if (!this.ready()) return;
    this.perform(this.api.save(this.configuration(), this.revision()), 'Saving configuration', snapshot => {
      this.configuration.set(snapshot.configuration!);
      this.baseline.set(JSON.stringify(snapshot.configuration));
      this.revision.set(snapshot.revision);
      this.announcement.set(`Configuration saved · revision ${snapshot.revision}. Not deployed.`);
    });
  }

  preview(): void {
    if (!this.ready()) return;
    this.perform(this.api.preview(this.configuration(), this.revision(), this.selectedRoles(), this.previewRoute()), 'Previewing access', result => {
      this.decision.set(`${result.decision === 'allow' ? 'Allow' : 'Deny'}${result.public ? ' · public route' : ''} · configuration preview, not an AWS decision`);
    });
  }

  download(): void {
    if (!this.canExport()) return;
    this.perform(this.api.export(this.revision()), 'Preparing download', blob => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `rbac-revision-${this.revision()}.zip`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      this.announcement.set('AWS configuration exported. Deploy and attach authorization before enforcing access.');
    });
  }

  private perform<T>(request: Observable<T>, label: string, success: (value: T) => void): void {
    this.busy.set(label); this.error.set('');
    request.pipe(timeout(150000), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => { success(value); this.busy.set(''); },
      error: (error: HttpErrorResponse) => {
        this.busy.set('');
        this.error.set(error.status === 409 ? 'The saved configuration changed. Your edits are preserved; reload to use the latest revision.'
          : typeof error.error?.error === 'string' ? error.error.error : 'The request failed. Check the backend connection and retry; your edits are preserved.');
      },
    });
  }
}
