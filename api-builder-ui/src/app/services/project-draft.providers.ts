import { inject, Provider, Type } from '@angular/core';
import { BuilderProjectsService } from './builder-projects.service';
import { RoutingDraftsService } from '../components/routing/routing-drafts.service';
import { AuthenticationDraftsService } from '../components/authentication/authentication-drafts.service';
import { VectorSearchService } from '../components/vector-search/vector-search.service';
import { RbacService } from '../components/rbac/rbac.service';

function projectState<T>(token: Type<T>, create: () => T): T {
  const projects = inject(BuilderProjectsService);
  return projects.activeProject() ? projects.scope(token, create) : inject(token, { skipSelf: true });
}

// Component providers run on each page entry; cached route injectors must not pin a project.
export const projectDraftProviders: Provider[] = [
  { provide: RoutingDraftsService, useFactory: () => projectState(RoutingDraftsService, () => new RoutingDraftsService()) },
  { provide: AuthenticationDraftsService, useFactory: () => projectState(AuthenticationDraftsService, () => new AuthenticationDraftsService()) },
  { provide: VectorSearchService, useFactory: () => projectState(VectorSearchService, () => new VectorSearchService()) },
  { provide: RbacService, useFactory: () => projectState(RbacService, () => new RbacService()) },
];
