import { Injectable, RendererFactory2, inject } from '@angular/core';

interface Feedback {
  button: HTMLButtonElement;
  spinner: HTMLElement;
  started: number;
  requests: number;
  timer?: ReturnType<typeof setTimeout>;
}

@Injectable({ providedIn: 'root' })
export class ButtonFeedbackService {
  private readonly renderer = inject(RendererFactory2).createRenderer(null, null);
  private readonly active = new Map<HTMLButtonElement, Feedback>();
  private current: Feedback | null = null;

  start(button: HTMLButtonElement): void {
    if (button.disabled || button.getAttribute('aria-disabled') === 'true') return;
    let feedback = this.active.get(button);
    if (!feedback) {
      const spinner = this.renderer.createElement('span') as HTMLElement;
      this.renderer.addClass(spinner, 'button-click-spinner');
      this.renderer.setAttribute(spinner, 'aria-hidden', 'true');
      this.renderer.appendChild(button, spinner);
      feedback = { button, spinner, started: Date.now(), requests: 0 };
      this.active.set(button, feedback);
    }
    clearTimeout(feedback.timer);
    feedback.started = Date.now();
    this.current = feedback;
    const clicked = feedback;
    // Actions subscribe during the click dispatch; background requests are excluded.
    setTimeout(() => {
      if (this.current === clicked) this.current = null;
      this.settle(clicked);
    }, 0);
  }

  requestStarted(): () => void {
    const feedback = this.current;
    if (!feedback) return () => undefined;
    feedback.requests++;
    clearTimeout(feedback.timer);
    let completed = false;
    return () => {
      if (completed) return;
      completed = true;
      feedback.requests--;
      this.settle(feedback);
    };
  }

  clear(): void {
    for (const feedback of this.active.values()) this.remove(feedback);
    this.current = null;
  }

  private settle(feedback: Feedback): void {
    if (feedback.requests || !this.active.has(feedback.button)) return;
    clearTimeout(feedback.timer);
    feedback.timer = setTimeout(() => this.remove(feedback), Math.max(0, 350 - (Date.now() - feedback.started)));
  }

  private remove(feedback: Feedback): void {
    clearTimeout(feedback.timer);
    if (feedback.spinner.parentNode === feedback.button) this.renderer.removeChild(feedback.button, feedback.spinner);
    this.active.delete(feedback.button);
  }
}
