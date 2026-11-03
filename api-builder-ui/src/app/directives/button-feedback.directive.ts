import { Directive, ElementRef, OnDestroy, inject } from '@angular/core';
import { ButtonFeedbackService } from '../services/button-feedback.service';

@Directive({ selector: '[appButtonFeedback]' })
export class ButtonFeedbackDirective implements OnDestroy {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly feedback = inject(ButtonFeedbackService);
  private readonly clicked = (event: Event): void => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest('button');
    if (button instanceof HTMLButtonElement && this.host.contains(button)) this.feedback.start(button);
  };

  constructor() { this.host.addEventListener('click', this.clicked, true); }
  ngOnDestroy(): void {
    this.host.removeEventListener('click', this.clicked, true);
    this.feedback.clear();
  }
}
