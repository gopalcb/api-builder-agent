import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { SelectComponent } from './select.component';

it('exposes disabled options but never emits them through clicks or keyboard', () => {
  const fixture = TestBed.createComponent(SelectComponent);
  const select = fixture.componentInstance;
  select.options = [{ value: 'serverless', label: 'Serverless' }, { value: 'container', label: 'Container', disabled: true }, { value: 'future', label: 'Future' }];
  select.value = 'serverless';
  fixture.detectChanges();
  const emit = vi.spyOn(select.valueChange, 'emit');
  select.choose('container');
  expect(emit).not.toHaveBeenCalled();
  const buttons = fixture.nativeElement.querySelectorAll('[role=option]');
  expect(buttons[1].disabled).toBe(true);
  expect(buttons[1].getAttribute('aria-disabled')).toBe('true');
  select.open = true;
  select.key(new KeyboardEvent('keydown', { key: 'ArrowDown' }));
  expect(select.active).toBe(2);
  select.key(new KeyboardEvent('keydown', { key: 'ArrowUp' }));
  expect(select.active).toBe(0);
  select.key(new KeyboardEvent('keydown', { key: 'End' }));
  expect(select.active).toBe(2);
  select.active = 1;
  select.key(new KeyboardEvent('keydown', { key: 'Enter' }));
  expect(emit).not.toHaveBeenCalled();
});
