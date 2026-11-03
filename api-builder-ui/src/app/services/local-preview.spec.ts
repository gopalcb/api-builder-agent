import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, UrlTree } from '@angular/router';
import { vi } from 'vitest';
import { AuthService, isLocalPreview, LOCAL_PREVIEW, safeReturnPath } from './auth.service';
import { authGuard } from '../guards/auth.guard';

describe('Local development preview', () => {
  afterEach(() => vi.restoreAllMocks());

  it('accepts the canonical entity return path and rejects external paths', () => {
    expect(safeReturnPath('/api-builder/entity-config')).toBe('/api-builder/entity-config');
    expect(safeReturnPath('/api-builder/routing')).toBe('/api-builder/routing');
    expect(safeReturnPath('//example.com')).toBe('/api-builder/projects');
  });

  it('is restricted to development builds on loopback hosts', () => {
    for (const hostname of ['localhost', '127.0.0.1', '[::1]']) {
      expect(isLocalPreview(true, hostname)).toBe(true);
      expect(isLocalPreview(false, hostname)).toBe(false);
    }
    expect(isLocalPreview(true, 'example.com')).toBe(false);
    expect(isLocalPreview(true, 'localhost.example.com')).toBe(false);
  });

  it('opens local routes without fetching auth configuration or creating a session', async () => {
    TestBed.configureTestingModule({ providers: [provideRouter([]), { provide: LOCAL_PREVIEW, useValue: true }] });
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const auth = TestBed.inject(AuthService);
    await auth.initialize();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(auth.ready()).toBe(true);
    expect(auth.hasSession()).toBe(false);
    expect(auth.identity()).toBeNull();
    expect(TestBed.runInInjectionContext(() => authGuard({} as never, { url: '/api-builder/entity-config' } as never))).toBe(true);
  });

  it('still redirects unauthenticated users when preview is disabled', () => {
    TestBed.configureTestingModule({ providers: [provideRouter([]), { provide: LOCAL_PREVIEW, useValue: false }] });
    const result = TestBed.runInInjectionContext(() => authGuard({} as never, { url: '/api-builder/entity-config' } as never));
    expect(result).toBeInstanceOf(UrlTree);
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/work-organizer/login?returnTo=%2Fapi-builder%2Fentity-config');
  });
});
