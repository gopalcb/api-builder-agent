import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

const paths: Record<string, string> = {
  activity: 'M3 12h4l3-8 4 16 3-8h4',
  settings: 'M4 7h16M4 17h16M8 4v6M16 14v6',
  more: 'M4 6h16M4 12h16M4 18h16',
  build: 'm12 3 9 5-9 5-9-5zM3 8v10l9 5 9-5V8M12 13v10',
  github: 'M9 19c-4 1-4-2-6-2m12 5v-4c0-1 .1-2-1-3 4 0 7-2 7-6 0-2-1-3-2-4 0-1 0-3-1-3-2 0-3 1-3 1-2-1-5-1-7 0 0 0-2-1-3-1-1 0-1 2-1 3-1 1-2 2-2 4 0 4 3 6 7 6-1 1-1 2-1 3v4', 
  document: 'M5 3h9l5 5v13H5zM14 3v6h5M8 13h8M8 17h8',
  gauge: 'M4 19a10 10 0 1 1 16 0M12 13l5-6M5 12h2M12 4v2M17 12h2M12 13a2 2 0 1 0 0 4 2 2 0 0 0 0-4',
  check: 'm5 12 4 4L19 6',
  plus: 'M12 5v14M5 12h14',
  edit: 'm15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
  close: 'm6 6 12 12M6 18 18 6',
  refresh: 'M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 2l1 4M4 12l1 4a8 8 0 0 0 13 2',
  folder: 'M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10H3z',
  entity: 'M4 4h16v16H4zM4 9h16M9 9v11',
  route: 'M6 9v6m0-3h8a4 4 0 0 0 4-4V7M6 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6M18 1a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  lock: 'M6 10h12v11H6zM8 10V6a4 4 0 0 1 8 0v4',
  shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6',
  search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14m5 12 6 6',
  cache: 'm13 2-8 12h6l-1 8 9-13h-6z',
  server: 'M3 3h18v7H3zM3 14h18v7H3zM6 6.5h1M6 17.5h1M11 6.5h7M11 17.5h7',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  import: 'M12 3v12m-5-5 5 5 5-5M3 13v8h18v-8',
  sparkle: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5zM20 2v4M18 4h4',
};

/** Decorative icons always accompany a visible, accessible text label. */
@Component({
  selector: 'wo-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'aria-hidden': 'true' },
  template: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" focusable="false"><path [attr.d]="paths[name]" /></svg>',
  styles: [':host { display: inline-flex; width: 14px; height: 14px; flex: 0 0 14px; vertical-align: middle; } svg { display: block; width: 100%; height: 100%; }'],
})
export class WoIconComponent {
  @Input({ required: true }) name = '';
  readonly paths = paths;
}
