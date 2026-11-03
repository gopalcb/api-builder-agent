import { TestBed } from '@angular/core/testing';
import { AuthenticationComponent } from './authentication.component';
import { AuthenticationDraftsService, authProviders, fieldsFor } from './authentication-drafts.service';
import { safeReturnPath } from '../../services/auth.service';
import { routes } from '../../app.routes';
import { authGuard } from '../../guards/auth.guard';

it('guards the configuration route and preserves it after sign-in', () => {
  expect(routes.find(route => route.path === 'api-builder/authentication')?.canActivate).toContain(authGuard);
  expect(safeReturnPath('/api-builder/authentication')).toBe('/api-builder/authentication');
});

for (const provider of authProviders) {
  it(`validates and saves only ${provider.label} fields`, () => {
    const store = TestBed.inject(AuthenticationDraftsService);
    store.provider.set(provider);
    const form = store.forms.get(provider.value)!;
    store.save();
    expect(store.saved()[provider.value]).toBeUndefined();
    const values: Record<string, string> = {
      clientId: ' example-client ', redirectUri: 'http://localhost:4200/auth/callback',
      authorizationUrl: 'https://identity.example.com/authorize', tokenUrl: 'https://identity.example.com/token',
      issuer: provider.value === 'cognito' ? 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Example' : 'https://identity.example.com',
      domain: 'https://login.example.com', audience: '', scopes: provider.value === 'oauth2' ? '' : 'openid profile email',
    };
    for (const field of fieldsFor(provider)) form.controls[field.key].setValue(values[field.key]);
    expect(form.valid).toBe(true);
    store.save();
    expect(store.saved()[provider.value]['clientId']).toBe('example-client');
    expect(Object.keys(store.saved()[provider.value])).toEqual(fieldsFor(provider).map(field => field.key));
    for (const bad of ['http://app.example.com/callback', 'https://user:password@app.example.com', 'https://app.example.com/#token', 'javascript:alert(1)', 'https:example.com', 'https://example.com/path with space']) {
      form.controls['redirectUri'].setValue(bad);
      expect(form.invalid).toBe(true);
    }
    form.controls['redirectUri'].setValue(values['redirectUri']);
    form.controls['clientId'].setValue('   ');
    expect(form.invalid).toBe(true);
    if (provider.value !== 'oauth2') {
      form.controls['scopes'].setValue('profile email');
      expect(form.controls['scopes'].invalid).toBe(true);
    }
    if (provider.value === 'cognito') {
      form.controls['issuer'].setValue('https://login.example.com');
      expect(form.controls['issuer'].invalid).toBe(true);
    }
  });
}

it('keeps edits across provider switches and component recreation, with inline errors and focus', () => {
  const fixture = TestBed.createComponent(AuthenticationComponent);
  fixture.detectChanges();
  const component = fixture.componentInstance;
  document.body.appendChild(fixture.nativeElement);
  component.save();
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelector('#auth-authorizationUrl').getAttribute('aria-invalid')).toBe('true');
  expect(document.activeElement?.id).toBe('auth-authorizationUrl');
  component.form.controls['clientId'].setValue('retained-client');
  component.selectProvider('oidc');
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelector('#auth-authorizationUrl')).toBeNull();
  expect(fixture.nativeElement.querySelector('#auth-issuer')).not.toBeNull();
  component.selectProvider('oauth2');
  expect(component.form.controls['clientId'].value).toBe('retained-client');
  fixture.destroy();
  const next = TestBed.createComponent(AuthenticationComponent);
  next.detectChanges();
  expect(next.componentInstance.form.controls['clientId'].value).toBe('retained-client');
});
