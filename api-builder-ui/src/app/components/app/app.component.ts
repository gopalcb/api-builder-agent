import { ButtonFeedbackDirective } from '../../directives/button-feedback.directive';
import { LocalConnectionService } from '../../services/local-connection.service';
import { ProjectActivitiesService } from '../../services/project-activities.service';
import { ProjectBuildActionsComponent } from '../project-build-actions/project-build-actions.component';
import { ProjectSelectorComponent } from '../project-selector/project-selector.component';
import { WoIconComponent } from '../../../theme/icon.component';
import { BuilderProjectsService } from '../../services/builder-projects.service';
import {
  Component,
  ElementRef,
  HostListener,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Title } from '@angular/platform-browser';
import {
  NavigationCancel,
  NavigationEnd,
  NavigationError,
  NavigationStart,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { WoSpinnerComponent } from '../../../theme/components';

import { AuthService } from '../../services/auth.service';

export const navigation = [
  {
    id: 'workspace',
    label: 'Workspace',
    items: [
      { slug: 'project-tracker', label: 'Project Tracker' },
      { slug: 'documents', label: 'Documents' },
      { slug: 'merger-agent', label: 'Merger agent' },
    ],
  },
  {
    id: 'analytics',
    label: 'Analytics',
    items: [{ slug: 'gh-portfolio', label: 'GH Portfolio' }],
  },
  {
    id: 'design-system',
    label: 'Design system',
    items: [
      { slug: 'components', label: 'Cards & buttons' },
      { slug: 'grid', label: 'Responsive grid' },
      { slug: 'forms', label: 'Forms & inputs' },
      { slug: 'loading', label: 'Loading states' },
    ],
  },
  {
    id: 'settings',
    label: 'Settings',
    items: [{ slug: 'preferences', label: 'Preferences' }],
  },
];
@Component({
  selector: 'app-root',
  imports: [ButtonFeedbackDirective,  ProjectBuildActionsComponent, ProjectSelectorComponent, WoIconComponent, RouterLink, RouterLinkActive, RouterOutlet, WoSpinnerComponent],
  templateUrl: './app.component.html',
})
export class AppComponent {
  readonly connection = inject(LocalConnectionService);
  readonly projects = inject(BuilderProjectsService);
  readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly title = inject(Title);
  @ViewChild('pageTitle') pageTitle?: ElementRef<HTMLHeadingElement>;
  readonly headerNavigation = [
    { label: 'Projects', icon: 'folder', path: '/api-builder/projects' },
    { label: 'Entity config', icon: 'entity', path: '/api-builder/entity-config' },
    { label: 'Endpoints', icon: 'route', path: '/api-builder/routing' },
    { label: 'Auth', icon: 'lock', path: '/api-builder/authentication' },
    { label: 'RBAC', icon: 'shield', path: '/api-builder/rbac' },
    { label: 'Vector search', icon: 'search', path: '/api-builder/vector-search' },
    { label: 'Caching', icon: 'cache', path: '/api-builder/caching' },
    { label: 'Infrastructure', icon: 'server', path: '/api-builder/infrastructure' },
    { label: 'Load testing', icon: 'gauge', path: '/api-builder/load-testing' },
  ];
  readonly activities = inject(ProjectActivitiesService);
  readonly moreOpen = signal(false);
  @ViewChild('moreRegion') moreRegion?: ElementRef<HTMLElement>;
  @ViewChild('moreButton') moreButton?: ElementRef<HTMLButtonElement>;

  @HostListener('click', ['$event'])
  recordInteraction(event: Event): void {
    const target = (event.target as HTMLElement).closest('button, a');
    if (!target || target.hasAttribute('disabled')) return;
    const label = target.getAttribute('aria-label') || target.textContent?.trim().replace(/\s+/g, ' ');
    if (label) this.activities.record(this.projects.activeId(), `Clicked ${label.slice(0, 80)}`);
  }

  @HostListener('change', ['$event'])
  recordFieldChange(event: Event): void {
    const field = event.target as HTMLInputElement;
    const label = field.labels?.[0]?.textContent?.trim() || field.getAttribute('aria-label');
    if (label) this.activities.record(this.projects.activeId(), `Changed ${label.slice(0, 80)}`);
  }

  readonly accountOpen = signal(false);
  readonly authPage = signal(false);
  readonly showShell = computed(() => (this.auth.localPreview || this.auth.allowed()) && !this.authPage());
  @ViewChild('accountButton') accountButton?: ElementRef<HTMLButtonElement>;
  @ViewChild('accountRegion') accountRegion?: ElementRef<HTMLElement>;

  @HostListener('document:click', ['$event'])
  dismissOutside(event: MouseEvent): void {
    if (this.moreOpen() && !this.moreRegion?.nativeElement.contains(event.target as Node)) this.moreOpen.set(false);
    if (this.accountOpen() && !this.accountRegion?.nativeElement.contains(event.target as Node)) {
      this.accountOpen.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  dismissAccount(): void {
    if (this.moreOpen()) { this.moreOpen.set(false); this.moreButton?.nativeElement.focus(); }
    if (!this.accountOpen()) {
      return;
    }

    this.accountOpen.set(false);

    this.accountButton?.nativeElement.focus();
  }

  logout(): void {
    this.accountOpen.set(false);

    this.auth.logout();
  }
  readonly section = signal('workspace');
  readonly heading = signal('Overview');
  readonly inlineProjectTitle = signal(false);
  readonly busy = signal(false);
  readonly current = computed(
    () => navigation.find((group) => group.id === this.section()) ?? navigation[0],
  );
  skipToContent(event: Event): void {
    event.preventDefault();

    this.pageTitle?.nativeElement.focus();
  }
  constructor() {
    this.router.events.pipe(takeUntilDestroyed()).subscribe((event) => {
      if (event instanceof NavigationStart) {
        this.busy.set(true);
      }

      if (event instanceof NavigationEnd) {
        const data = this.router.routerState.snapshot.root.firstChild?.data ?? {};

        this.authPage.set(Boolean(data['authMode']));

        this.accountOpen.set(false);
        this.moreOpen.set(false);
        if (event.urlAfterRedirects.startsWith('/api-builder/')) this.activities.record(this.projects.activeId(), `Opened ${data['title'] ?? 'page'}`);

        this.section.set(data['section'] ?? 'workspace');

        this.heading.set(data['title'] ?? 'Overview');
        this.inlineProjectTitle.set(Boolean(data['inlineProjectTitle']));

        this.title.setTitle(`${this.heading()} · API Builder`);

        this.busy.set(false);

        requestAnimationFrame(() => this.pageTitle?.nativeElement.focus({ preventScroll: true }));
      }

      if (event instanceof NavigationError || event instanceof NavigationCancel) {
        this.busy.set(false);
      }
    });
  }
}
