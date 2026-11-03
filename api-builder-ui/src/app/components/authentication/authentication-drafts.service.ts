import { Injectable, signal } from '@angular/core';
import { FormControl, FormGroup, ValidatorFn, Validators } from '@angular/forms';

export interface AuthField {
  key: string;
  label: string;
  hint: string;
  placeholder: string;
  required: boolean;
  kind?: 'url' | 'origin' | 'issuer' | 'callback' | 'scopes';
}
export interface AuthProvider {
  value: string;
  label: string;
  description: string;
  fields: AuthField[];
}
const field = (key: string, label: string, placeholder: string, hint = '', kind?: AuthField['kind'], required = true): AuthField =>
  ({ key, label, placeholder, hint, kind, required });

export const authProviders: AuthProvider[] = [
  { value: 'oauth2', label: 'OAuth 2.0', description: 'Authorize access to an API. For user sign-in, choose OpenID Connect or a provider preset.', fields: [
    field('authorizationUrl', 'Authorization URL', 'https://identity.example.com/authorize', '', 'url'),
    field('tokenUrl', 'Token URL', 'https://identity.example.com/token', '', 'url'),
  ] },
  { value: 'oidc', label: 'OpenID Connect', description: 'Configure user sign-in with an OpenID Connect provider.', fields: [
    field('issuer', 'Issuer URL', 'https://identity.example.com', 'Use the exact issuer published by your provider.', 'issuer'),
  ] },
  { value: 'auth0', label: 'Auth0', description: 'Configure an Auth0 single-page application.', fields: [
    field('domain', 'Auth0 domain URL', 'https://your-tenant.auth0.com', 'Tenant domain or configured custom domain, including https://.', 'origin'),
    field('audience', 'API audience', 'https://api.example.com', 'Optional. The API identifier configured in Auth0.', undefined, false),
  ] },
  { value: 'cognito', label: 'AWS Cognito', description: 'Configure a Cognito user-pool app client without a client secret.', fields: [
    field('issuer', 'User-pool issuer URL', 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Example', 'Copy the issuer for your user pool, not the managed login domain.', 'issuer'),
    field('domain', 'Login domain URL', 'https://your-domain.auth.us-east-1.amazoncognito.com', 'Managed login domain or configured custom domain.', 'origin'),
  ] },
];

export function fieldsFor(provider: AuthProvider): AuthField[] {
  return [
    ...provider.fields,
    field('clientId', 'Client ID', 'Application client ID'),
    field('redirectUri', 'Callback URL', 'https://app.example.com/auth/callback', 'Register this exact URL in your provider. HTTP is allowed only for loopback development.', 'callback'),
    field('scopes', 'Scopes', provider.value === 'oauth2' ? 'api:read' : 'openid profile email', 'Separate scopes with spaces.', 'scopes', provider.value !== 'oauth2'),
  ];
}

export function fieldValidator(field: AuthField, provider: string): ValidatorFn {
  return (control) => {
    const value = String(control.value).trim();
    if (!value) return field.required ? { required: true } : null;
    if (field.kind === 'scopes') {
      return /^[\x21\x23-\x5B\x5D-\x7E]+(?: +[\x21\x23-\x5B\x5D-\x7E]+)*$/.test(value)
        && (provider === 'oauth2' || value.split(/ +/).includes('openid')) ? null : { scopes: true };
    }
    if (!field.kind) return null;
    if (!/^https?:\/\//.test(value) || /\s/.test(value)) return { url: true };
    let url: URL;
    try { url = new URL(value); } catch { return { url: true }; }
    const loopback = field.kind === 'callback' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if ((url.protocol !== 'https:' && !(loopback && url.protocol === 'http:')) || url.username || url.password || url.hash) return { url: true };
    if (field.kind === 'origin' && (url.pathname !== '/' || url.search)) return { origin: true };
    if (field.kind === 'issuer' && url.search) return { issuer: true };
    if (provider === 'cognito' && field.key === 'issuer'
      && !/^https:\/\/cognito-idp\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?\/[a-z0-9-]+_[A-Za-z0-9]+$/.test(value)) return { issuer: true };
    return null;
  };
}

@Injectable({ providedIn: 'root' })
export class AuthenticationDraftsService {
  readonly provider = signal(authProviders[0]);
  readonly forms = new Map(authProviders.map(provider => [provider.value, new FormGroup(
    Object.fromEntries(fieldsFor(provider).map(field => [field.key, new FormControl(
      field.key === 'scopes' && provider.value !== 'oauth2' ? 'openid profile email' : '',
      { nonNullable: true, validators: [fieldValidator(field, provider.value), Validators.maxLength(2048)] },
    )])),
  )]));
  readonly saved = signal<Record<string, Record<string, string>>>({});

  save(): void {
    const provider = this.provider().value;
    const form = this.forms.get(provider)!;
    if (form.invalid) return;
    const values = Object.fromEntries(Object.entries(form.getRawValue()).map(([key, value]) => [key, value.trim()]));
    this.saved.update(saved => ({ ...saved, [provider]: values }));
    form.reset(values);
  }
}
