import {
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  ViewChild,
  computed,
  inject,
  signal,
} from "@angular/core";
import { HttpClient, HttpErrorResponse } from "@angular/common/http";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { BuilderProjectsService } from "../../services/builder-projects.service";
import { Subscription } from "rxjs";
import { firstValueFrom } from "rxjs";
import { MarkdownEditorComponent } from "../markdown-editor/markdown-editor.component";
import { ProjectBuildActionsComponent } from "../project-build-actions/project-build-actions.component";
import { ProjectSelectorComponent } from "../project-selector/project-selector.component";
import { WoSpinnerComponent } from "../../../theme/components";
import { WoIconComponent } from "../../../theme/icon.component";

interface ProjectDocument {
  id: string;
  filename: string;
  category: string;
  revision: number;
  etag: string;
  content: string;
}

@Component({
  selector: "app-project-docs",
  imports: [
    MarkdownEditorComponent,
    ProjectSelectorComponent,
    ProjectBuildActionsComponent,
    WoSpinnerComponent,
    WoIconComponent,
  ],
  templateUrl: "./project-docs.component.html",
  styles: [
    `
      .tm-document-item {
        border-radius: 4px !important;
      }
      .docs-search-clear {
        position: absolute;
        right: 4px;
        top: 2px;
        padding: 2px 6px;
        min-height: 24px;
        background: transparent;
        color: var(--wo-primary);
      }
      .docs-search-clear wo-icon {
        pointer-events: none;
      }
    `,
  ],
})
export class ProjectDocsComponent {
  readonly projects = inject(BuilderProjectsService);
  private listRequest?: Subscription;
  private readRequest?: Subscription;
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  private readVersion = 0;
  private alive = true;
  private resolveDiscard?: (discard: boolean) => void;
  @ViewChild("discardDialog") discardDialog!: ElementRef<HTMLDialogElement>;
  readonly documents = signal<ProjectDocument[]>([]);
  readonly selected = signal<ProjectDocument | null>(null);
  readonly content = signal("");
  readonly query = signal("");
  readonly descriptions: Record<string, {title: string; description: string}> = {
    overview: {title: 'Project overview and configuration summary', description: 'Project purpose and summary, bringing the saved workspace context together in one reference.'},
    entities: {title: 'Entity catalog and data model reference', description: 'Explore the saved entity names that form the foundation of this project’s data model.'},
    rbac: {title: 'Role permissions and access policy configuration', description: 'Review the saved role-based access configuration and its current revision.'},
    caching: {title: 'Route caching policies and configuration reference', description: 'Review the saved cache settings and policy configuration for this project.'},
    swagger: {title: 'Swagger API reference and request flow', description: 'OpenAPI reference and Mermaid request flow for the generated local API.'},
    'implementation-plan': {title: 'Implementation plan', description: 'The reviewed steps used to prepare the generated API.'},
    'implementation-summary': {title: 'Implementation summary', description: 'A concise record of the generated API implementation.'},
  };
  readonly loading = signal(false);
  readonly reading = signal(false);
  readonly saving = signal(false);
  readonly listError = signal("");
  readonly readError = signal("");
  readonly saveError = signal("");
  readonly notice = signal("");
  readonly dirty = computed(
    () =>
      !!this.selected() &&
      !this.reading() &&
      !this.readError() &&
      this.content() !== this.selected()!.content,
  );
  readonly filteredDocuments = computed(() => this.documents().filter(doc =>
    `${doc.filename} ${this.descriptions[doc.id]?.title ?? ''} ${this.descriptions[doc.id]?.description ?? ''}`
      .toLowerCase().includes(this.query().trim().toLowerCase())));

  readonly selectProject = async (value: string): Promise<void> => {
    const id = Number(value);
    if (id === this.projects.activeId() || !this.projects.projects().some(project => project.id === id)) return;
    if (!await this.canLeave() || !this.alive) return;
    this.listRequest?.unsubscribe();
    this.readRequest?.unsubscribe();
    ++this.readVersion;
    this.projects.select(id);
    this.documents.set([]);
    this.selected.set(null);
    this.content.set('');
    this.query.set('');
    this.reading.set(false);
    this.readError.set('');
    this.saveError.set('');
    this.notice.set('');
    this.loadList();
  }

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.alive = false;
      this.resolveDiscard?.(false);
    });
    this.loadList();
  }

  loadList(): void {
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.listError.set("");
    this.listRequest = this.http
      .get<{ documents: ProjectDocument[] }>("/api/project-documents")
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.documents.set(result.documents);
          this.loading.set(false);
        },
        error: () => {
          this.listError.set(
            "Documents could not be loaded. Please try again.",
          );
          this.loading.set(false);
        },
      });
  }

  async selectDocument(document: ProjectDocument): Promise<void> {
    if (!(await this.canLeave()) || !this.alive) return;
    this.readRequest?.unsubscribe();
    const version = ++this.readVersion;
    this.selected.set(document);
    this.content.set("");
    this.reading.set(true);
    this.readError.set("");
    this.saveError.set("");
    this.notice.set("");
    this.readRequest = this.http
      .get<{ document: ProjectDocument }>(
        `/api/project-documents/${document.id}`,
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          if (version !== this.readVersion) return;
          this.selected.set(result.document);
          this.content.set(result.document.content);
          this.reading.set(false);
        },
        error: () => {
          if (version !== this.readVersion) return;
          this.readError.set(
            "This document could not be opened. Please try again.",
          );
          this.reading.set(false);
        },
      });
  }

  async saveDocument(): Promise<void> {
    const document = this.selected();
    if (!document || !this.dirty() || this.saving()) return;
    if (new TextEncoder().encode(this.content()).length > 48000) {
      this.saveError.set("Document content must be at most 48 KB.");
      return;
    }
    this.saving.set(true);
    this.saveError.set("");
    this.notice.set("");
    try {
      const result = await firstValueFrom(
        this.http
          .put<{
            document: ProjectDocument;
          }>(`/api/project-documents/${document.id}`, { content: this.content(), revision: document.revision, etag: document.etag })
          .pipe(takeUntilDestroyed(this.destroyRef)),
      );
      if (!this.alive) return;
      this.selected.set(result.document);
      this.content.set(result.document.content);
      this.documents.update((docs) =>
        docs.map((doc) => (doc.id === document.id ? result.document : doc)),
      );
      this.notice.set("Saved.");
    } catch (error) {
      if (!this.alive) return;
      this.saveError.set(
        error instanceof HttpErrorResponse && error.status === 409
          ? "This document changed. Your draft is preserved; reopen the document to review the latest version."
          : "Save was not confirmed. Your draft is preserved; try again.",
      );
    } finally {
      this.saving.set(false);
    }
  }

  canLeave(): boolean | Promise<boolean> {
    if (this.saving()) return false;
    if (!this.dirty()) return true;
    if (this.resolveDiscard) return false;
    this.discardDialog.nativeElement.showModal();
    return new Promise((resolve) => (this.resolveDiscard = resolve));
  }

  finishDiscard(discard: boolean): void {
    this.discardDialog.nativeElement.close();
    if (discard) this.content.set(this.selected()?.content ?? "");
    this.resolveDiscard?.(discard);
    this.resolveDiscard = undefined;
  }

  @HostListener("window:beforeunload", ["$event"])
  protectDraft(event: BeforeUnloadEvent): void {
    if (this.dirty() || this.saving()) {
      event.preventDefault();
      event.returnValue = "";
    }
  }
}
