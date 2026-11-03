import { TestBed } from '@angular/core/testing';
import { ButtonFeedbackService } from './button-feedback.service';
import { vi } from 'vitest';

it('keeps feedback on the clicked button through its request and clears local actions without tracking background work', () => {
  vi.useFakeTimers();
  const feedback = TestBed.inject(ButtonFeedbackService);
  const first = document.createElement('button');
  const second = document.createElement('button');
  first.textContent = 'Save';
  second.textContent = 'Open';
  try {
    feedback.start(first);
    const complete = feedback.requestStarted();
    vi.advanceTimersByTime(400);
    expect(first.querySelector('.button-click-spinner')).not.toBeNull();
    feedback.start(second);
    vi.advanceTimersByTime(1);
    const backgroundComplete = feedback.requestStarted();
    vi.advanceTimersByTime(400);
    expect(second.querySelector('.button-click-spinner')).toBeNull();
    expect(first.querySelector('.button-click-spinner')).not.toBeNull();
    complete();
    vi.runAllTimers();
    backgroundComplete();
    expect(first.querySelector('.button-click-spinner')).toBeNull();
    expect(first.textContent).toBe('Save');
    first.disabled = true;
    feedback.start(first);
    expect(first.querySelector('.button-click-spinner')).toBeNull();
  } finally { feedback.clear(); vi.useRealTimers(); }
});
