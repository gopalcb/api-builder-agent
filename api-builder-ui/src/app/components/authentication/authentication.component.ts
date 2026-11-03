import { WoIconComponent } from '../../../theme/icon.component';
import { projectDraftProviders } from '../../services/project-draft.providers';
import { ChangeDetectionStrategy, Component, ElementRef, computed, inject, signal } from '@angular/core';
import { ReactiveFormsModule } from '@angular/forms';
import { WoCardComponent, WoTextInputComponent } from '../../../theme/components';
import { SelectComponent } from '../select/select.component';
import { AuthField, AuthenticationDraftsService, authProviders, fieldsFor } from './authentication-drafts.service';

@Component({
  providers: projectDraftProviders,
  imports: [WoIconComponent, ReactiveFormsModule, WoCardComponent, WoTextInputComponent, SelectComponent],
  templateUrl: './authentication.component.html',
  styleUrl: './authentication.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuthenticationComponent {
  readonly store = inject(AuthenticationDraftsService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  readonly providers = authProviders;
  readonly provider = this.store.provider;
  readonly fields = computed(() => fieldsFor(this.provider()));
  readonly submitted = signal(false);
  readonly announcement = signal('');
  readonly saved = computed(() => this.store.saved()[this.provider().value]);
  get form() { return this.store.forms.get(this.provider().value)!; }

  selectProvider(value: string): void {
    const provider = this.providers.find(provider => provider.value === value);
    if (!provider) return;
    this.provider.set(provider);
    this.submitted.set(false);
    this.announcement.set('');
  }

  error(field: AuthField): string {
    const control = this.form.controls[field.key];
    if (control.hasError('required')) return `${field.label} is required.`;
    if (control.hasError('maxlength')) return 'Enter no more than 2048 characters.';
    if (field.kind === 'scopes') return this.provider().value === 'oauth2'
      ? 'Use space-separated scopes without quotes or backslashes.'
      : 'Include openid and separate scopes with spaces, without quotes or backslashes.';
    if (field.kind === 'origin') return 'Enter an HTTPS domain URL without a path, query, credentials or fragment.';
    if (this.provider().value === 'cognito' && field.key === 'issuer') return 'Use https://cognito-idp.<region>.amazonaws.com/<user-pool-id> (or amazonaws.com.cn).';
    return field.kind === 'callback' ? 'Use an HTTPS callback URL (or HTTP on localhost), without credentials or a fragment.'
      : 'Use an HTTPS URL without credentials or a fragment; issuer URLs cannot have a query.';
  }

  save(): void {
    this.submitted.set(true);
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      this.announcement.set('Check the highlighted fields.');
      const invalid = this.fields().find(field => this.form.controls[field.key].invalid)!;
      this.host.nativeElement.querySelector<HTMLInputElement>(`#auth-${invalid.key}`)?.focus();
      return;
    }
    this.store.save();
    this.submitted.set(false);
    this.announcement.set(`${this.provider().label} draft saved for this session.`);
  }
}
