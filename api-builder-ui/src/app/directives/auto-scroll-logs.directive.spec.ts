import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AutoScrollLogsDirective } from './auto-scroll-logs.directive';

@Component({ imports: [AutoScrollLogsDirective], template: '<div appAutoScrollLogs></div>' })
class LogHost {}

it('follows appended logs and scrolls to latest when a hidden drawer reopens', async () => {
  let resize!: ResizeObserverCallback;
  const disconnect = vi.fn();
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: ResizeObserverCallback) { resize = callback; }
    observe() {}
    disconnect = disconnect;
  });
  try {
    const fixture = TestBed.createComponent(LogHost);
    fixture.detectChanges();
    await fixture.whenStable();
    const output: HTMLElement = fixture.nativeElement.querySelector('div');
    Object.defineProperty(output, 'scrollHeight', { value: 900, configurable: true });
    output.append(document.createTextNode('latest log'));
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(output.scrollTop).toBe(900);
    output.scrollTop = 0;
    resize([], {} as ResizeObserver);
    expect(output.scrollTop).toBe(900);
    fixture.destroy();
    expect(disconnect).toHaveBeenCalled();
  } finally { vi.unstubAllGlobals(); }
});
