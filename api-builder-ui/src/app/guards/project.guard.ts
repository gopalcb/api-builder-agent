import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { BuilderProjectsService } from '../services/builder-projects.service';

export const projectGuard: CanActivateFn = async () => {
  const projects = inject(BuilderProjectsService);
  const router = inject(Router);
  return await projects.load() && !!projects.activeProject() || router.parseUrl('/api-builder/projects');
};
