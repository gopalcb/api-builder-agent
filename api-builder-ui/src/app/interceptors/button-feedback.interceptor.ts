import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { defer, finalize } from 'rxjs';
import { ButtonFeedbackService } from '../services/button-feedback.service';

export const buttonFeedbackInterceptor: HttpInterceptorFn = (request, next) => {
  const complete = inject(ButtonFeedbackService).requestStarted();
  return defer(() => next(request)).pipe(finalize(complete));
};
