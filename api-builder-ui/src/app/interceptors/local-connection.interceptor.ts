import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { isBuilderRequest, LocalConnectionService } from '../services/local-connection.service';

export const localConnectionInterceptor: HttpInterceptorFn = (request, next) => {
  if (!isBuilderRequest(request.url)) return next(request);
  const connection = inject(LocalConnectionService);
  if (!connection.settings().direct) return next(request);
  return next(request.clone({ url: connection.url(request.url), withCredentials: true }));
};
