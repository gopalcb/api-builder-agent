import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { throwError } from 'rxjs';
import { BuilderProjectsService } from '../services/builder-projects.service';

export const projectInterceptor: HttpInterceptorFn = (request, next) => {
  if (!/^\/api\/(entity-configurations(?:\/|$)|endpoints(?:\/|$)|load-testing(?:\/|$)|project-documents(?:\/|$)|entities(?:\/|$)|rbac(?:\/|$)|caching(?:\/|$)|observability(?:\/|$)|generate-search-configuration$|generate-infrastructure-plan$)/.test(request.url)) return next(request);
  const project = inject(BuilderProjectsService).activeProject();
  if (!project) return throwError(() => new HttpErrorResponse({ status: 400, error: { error: 'Select an active project first.' } }));
  if (request.headers.has('X-Project-ID')) return next(request);
  return next(request.clone({ setHeaders: { 'X-Project-ID': String(project.id) } }));
};
