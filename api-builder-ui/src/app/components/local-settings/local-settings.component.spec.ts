import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { LocalSettingsComponent } from './local-settings.component';
import { CONNECTION_BROWSER, LocalConnectionService } from '../../services/local-connection.service';

async function setup() {
  TestBed.configureTestingModule({ imports: [LocalSettingsComponent], providers: [
    provideHttpClient(), provideHttpClientTesting(), { provide: CONNECTION_BROWSER, useValue: {
      origin: 'http://localhost:4200', hostname: 'localhost', protocol: 'http:',
      read: () => null, write: vi.fn(), reload: vi.fn(),
    } },
  ] });
  const fixture = TestBed.createComponent(LocalSettingsComponent);
  fixture.detectChanges();
  const component = fixture.componentInstance;
  const dialog = component.dialog.nativeElement;
  dialog.showModal = vi.fn(() => dialog.setAttribute('open', ''));
  dialog.close = vi.fn(() => dialog.removeAttribute('open'));
  component.open();
  fixture.detectChanges();
  expect(fixture.nativeElement.textContent).toContain('Run current API');
  expect(fixture.nativeElement.textContent.indexOf('Run current API')).toBeLessThan(fixture.nativeElement.textContent.indexOf('Reset defaults'));
  return { fixture, component, dialog, service: TestBed.inject(LocalConnectionService) };
}

it('validates the port and preserves unsaved draft until explicitly discarded', async () => {
  const { fixture, component, dialog, service } = await setup();
  const check = vi.spyOn(service, 'check').mockResolvedValue();
  component.form.setValue({ direct: true, port: '70000' });
  fixture.detectChanges();
  await component.test();
  fixture.detectChanges();
  expect(check).not.toHaveBeenCalled();
  expect(fixture.nativeElement.textContent).toContain('Enter a whole port number from 1 to 65535.');
  expect(fixture.nativeElement.querySelector('#local-backend-port').getAttribute('aria-invalid')).toBe('true');
  component.requestClose();
  fixture.detectChanges();
  expect(component.discard()).toBe(true);
  expect(dialog.close).not.toHaveBeenCalled();
  component.discard.set(false);
  expect(component.form.controls.port.value).toBe('70000');
  component.close();
  expect(dialog.close).toHaveBeenCalledOnce();
});

it('tests without saving, resets only the draft, and retains failed input', async () => {
  const { fixture, component, service } = await setup();
  const apply = vi.spyOn(service, 'apply').mockRejectedValue(new Error('Connection unavailable.'));
  const check = vi.spyOn(service, 'check').mockResolvedValue();
  component.form.setValue({ direct: true, port: '5002' });
  await component.test();
  expect(check).toHaveBeenCalledWith({ direct: true, port: 5002 });
  expect(component.notice()).toContain('have not been saved');
  expect(apply).not.toHaveBeenCalled();
  await component.test(true);
  expect(component.error()).toBe('Connection unavailable.');
  expect(component.form.controls.port.value).toBe('5002');
  component.reset();
  fixture.detectChanges();
  expect(component.form.getRawValue()).toEqual({ direct: false, port: '5000' });
  expect(service.settings()).toEqual({ direct: false, port: 5000 });
});

it('prevents duplicate operations and Escape dismissal during a request', async () => {
  const { component, service, dialog } = await setup();
  let finish!: () => void;
  const check = vi.spyOn(service, 'check').mockImplementation(() => new Promise<void>(resolve => finish = resolve));
  const pending = component.test();
  expect(component.busy()).toBe(true);
  await component.test();
  component.requestClose();
  expect(check).toHaveBeenCalledOnce();
  expect(dialog.close).not.toHaveBeenCalled();
  finish();
  await pending;
  expect(component.busy()).toBe(false);
});
