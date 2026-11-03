import { afterNextRender, DestroyRef, Directive, ElementRef, inject } from '@angular/core';

/** Follow appended execution events after the DOM has rendered, including bounded log lists. */
@Directive({ selector: '[appAutoScrollLogs]' })
export class AutoScrollLogsDirective {
  constructor() {
    const element = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    const observer = new MutationObserver(() => { element.scrollTop = element.scrollHeight; });
    const resizeObserver = typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(() => { element.scrollTop = element.scrollHeight; });
    afterNextRender(() => {
      element.scrollTop = element.scrollHeight;
      resizeObserver?.observe(element);
      observer.observe(element, { childList: true, subtree: true, characterData: true });
    });
    inject(DestroyRef).onDestroy(() => { observer.disconnect(); resizeObserver?.disconnect(); });
  }
}
