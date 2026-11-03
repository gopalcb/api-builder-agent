import { projectGuard } from './guards/project.guard';
import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';
export const routes: Routes = [
  { path: 'api-builder/observability', data: { section: 'workspace', title: 'Observability & Tracing' }, canActivate: [authGuard, projectGuard], loadComponent: () => import('./components/observability/observability.component').then(m => m.ObservabilityComponent) },
  { path: 'api-builder/activities', data: { section: 'workspace', title: 'Project activities' }, canActivate: [authGuard, projectGuard], loadComponent: () => import('./components/project-activities/project-activities.component').then(m => m.ProjectActivitiesComponent) },
  { path: 'api-builder/settings', data: { section: 'settings', title: 'Settings' }, canActivate: [authGuard, projectGuard], loadComponent: () => import('./components/preferences/preferences.component').then(m => m.PreferencesComponent) },
  { path: 'api-builder/docs', data: { section: 'workspace', title: 'Documents', inlineProjectTitle: true }, canActivate: [authGuard, projectGuard], canDeactivate: [(component: { canLeave: () => boolean | Promise<boolean> }) => component.canLeave()], loadComponent: () => import('./components/project-docs/project-docs.component').then(m => m.ProjectDocsComponent) },
  { path: 'api-builder/load-testing', data: { section: 'workspace', title: 'Load testing' }, canActivate: [authGuard, projectGuard], loadComponent: () => import('./components/load-testing/load-testing.component').then(m => m.LoadTestingComponent) },
  { path: 'api-builder/caching', data: { section: 'workspace', title: 'Caching' }, canActivate: [authGuard, projectGuard], loadComponent: () => import('./components/caching/caching.component').then(m => m.CachingComponent) },
  ...['infrastructure'].map((page) => ({
    path: `api-builder/${page}`,
    data: { section: 'workspace', title: page === 'caching' ? 'Caching' : 'Infrastructure', page },
    canActivate: [authGuard, projectGuard],
    loadComponent: () => import('./components/resource-planning/resource-planning.component').then(m => m.ResourcePlanningComponent),
  })),
  { path: 'api-builder/projects', data: { section: 'workspace', title: 'Manage your projects' }, canActivate: [authGuard], loadComponent: () => import('./components/projects/projects.component').then(m => m.ProjectsComponent) },
  {
    path: 'api-builder/rbac',
    data: { section: 'workspace', title: 'Configure role permissions' },
    canActivate: [authGuard, projectGuard],
    loadComponent: () => import('./components/rbac/rbac.component').then(m => m.RbacComponent),
  },
  {
    path: 'api-builder/vector-search',
    data: { section: 'workspace', title: 'Configure vector search' },
    canActivate: [authGuard, projectGuard],
    loadComponent: () => import('./components/vector-search/vector-search.component').then(m => m.VectorSearchComponent),
  },
  {
    path: 'api-builder/authentication',
    data: { section: 'workspace', title: 'Configure authentication' },
    canActivate: [authGuard, projectGuard],
    loadComponent: () => import('./components/authentication/authentication.component').then(m => m.AuthenticationComponent),
  },
  {
    path: 'api-builder/routing',
    data: { section: 'workspace', title: 'Configure your routes' },
    canActivate: [authGuard, projectGuard],
    loadComponent: () => import('./components/routing/routing.component').then(m => m.RoutingComponent),
  },
  { path: 'api-builder', pathMatch: 'full', redirectTo: 'api-builder/projects' },
  { path: 'work-organizer/entities', pathMatch: 'full', redirectTo: 'api-builder/entity-config' },
  {
    path: 'api-builder/entity-config',
    data: { section: 'workspace', title: 'Design your entities' },
    canActivate: [authGuard, projectGuard],
    loadComponent: () => import('./components/entities/entities.component').then(m => m.EntitiesComponent),
  },
  ...['login', 'auth/callback', 'denied', 'signed-out'].map((path) => ({
    path: `work-organizer/${path}`,
    data: { title: 'Account', authMode: path === 'auth/callback' ? 'callback' : path },
    loadComponent: () => import('./components/auth/auth.component').then((m) => m.AuthComponent),
  })),
  {
    path: '',
    pathMatch: 'full',
    redirectTo: 'api-builder/projects',
  },
  {
    path: 'work-organizer',
    pathMatch: 'full',
    redirectTo: 'api-builder/projects',
  },
  {
    path: 'work-organizer/workspace/overview',
    pathMatch: 'full',
    redirectTo: 'work-organizer/workspace/project-tracker',
  },
  {
    path: 'work-organizer/workspace/project-tracker',
    data: { section: 'workspace', title: 'Project Tracker' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/project-tracker/project-tracker.component').then(
        (m) => m.ProjectTrackerComponent,
      ),
  },
  {
    path: 'work-organizer/workspace/project-tracker/new',
    data: { section: 'workspace', title: 'Create work item' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/work-item/work-item.component').then((m) => m.WorkItemComponent),
  },
  {
    path: 'work-organizer/workspace/project-tracker/:id',
    data: { section: 'workspace', title: 'Work item details' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/work-item/work-item.component').then((m) => m.WorkItemComponent),
  },
  {
    path: 'work-organizer/workspace/documents',
    data: { section: 'workspace', title: 'Documents' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/documents/documents.component').then((m) => m.DocumentsComponent),
  },
  {
    path: 'work-organizer/workspace/merger-agent',
    data: { section: 'workspace', title: 'Merger agent' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/merger-agent/merger-agent.component').then(
        (m) => m.MergerAgentComponent,
      ),
  },
  {
    path: 'work-organizer/workspace/messages',
    data: { section: 'workspace', title: 'Messages' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/messages/messages.component').then((m) => m.MessagesComponent),
  },
  ...['tasks', 'activity'].map((path) => ({
    path: `work-organizer/workspace/${path}`,
    redirectTo: 'work-organizer/workspace/project-tracker',
    pathMatch: 'full' as const,
  })),
  {
    path: 'work-organizer/analytics',
    pathMatch: 'full',
    redirectTo: 'work-organizer/analytics/gh-portfolio',
  },
  {
    path: 'work-organizer/analytics/gh-portfolio',
    data: { section: 'analytics', title: 'GH Portfolio' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/portfolio-analytics/portfolio-analytics.component').then(
        (m) => m.PortfolioAnalyticsComponent,
      ),
  },
  {
    path: 'work-organizer/design-system/components',
    data: { section: 'design-system', title: 'Cards & buttons' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/components/components.component').then((m) => m.ComponentsComponent),
  },
  {
    path: 'work-organizer/design-system/grid',
    data: { section: 'design-system', title: 'Responsive grid' },
    canActivate: [authGuard],
    loadComponent: () => import('./components/grid/grid.component').then((m) => m.GridComponent),
  },
  {
    path: 'work-organizer/design-system/forms',
    data: { section: 'design-system', title: 'Forms & inputs' },
    canActivate: [authGuard],
    loadComponent: () => import('./components/forms/forms.component').then((m) => m.FormsComponent),
  },
  {
    path: 'work-organizer/design-system/loading',
    data: { section: 'design-system', title: 'Loading states' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/loading/loading.component').then((m) => m.LoadingComponent),
  },
  {
    path: 'work-organizer/settings/preferences',
    data: { section: 'settings', title: 'Preferences' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/preferences/preferences.component').then((m) => m.PreferencesComponent),
  },
  {
    path: '**',
    data: { section: 'workspace', title: 'Page not found' },
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/not-found/not-found.component').then((m) => m.NotFoundComponent),
  },
];
