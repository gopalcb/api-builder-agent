import { WoIconComponent } from '../../../theme/icon.component';
import { projectDraftProviders } from '../../services/project-draft.providers';
import { ChangeDetectionStrategy, Component, ElementRef, effect, inject } from '@angular/core';
import { ReactiveFormsModule } from '@angular/forms';
import { WoCardComponent, WoSpinnerComponent } from '../../../theme/components';
import { SelectComponent } from '../select/select.component';
import { searchTypes, VectorSearchService } from './vector-search.service';

@Component({
  providers: projectDraftProviders,
  imports: [WoIconComponent, ReactiveFormsModule, WoCardComponent, WoSpinnerComponent, SelectComponent],
  templateUrl: './vector-search.component.html',
  styleUrl: './vector-search.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VectorSearchComponent {
  readonly store = inject(VectorSearchService);
  readonly types = searchTypes;
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  constructor() { effect(() => this.store.reconcilePath()); }
  get selectedType() { return this.types.find(type => type.value === this.store.type.value)!; }
  get pathError(): string {
    if (this.store.path.hasError('required')) return 'Route path is required.';
    if (this.store.path.hasError('routeType')) return 'Choose a current route matching the selected search type.';
    if (this.store.path.hasError('duplicate')) return 'This search route path is already configured.';
    return 'Use a path such as /products/search with letters, numbers, hyphens or underscores.';
  }
  label(type: string): string { return this.types.find(item => item.value === type)!.label; }
  setType(value: string): void {
    if (!this.store.busy() && this.types.some(type => type.value === value)) this.store.setType(value);
  }
  generate(): void {
    this.store.generate();
    if (this.store.form.invalid) {
      this.host.nativeElement.querySelector<HTMLElement>(this.store.path.invalid ? '#search-path' : '#search-prompt')?.focus();
    }
  }
}
