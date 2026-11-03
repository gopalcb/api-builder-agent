import { vi } from 'vitest';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { EntitiesComponent } from './entities.component';

describe('Entity config', () => {
  beforeEach(() => TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting()],
  }));
  afterEach(() => { TestBed.inject(HttpTestingController).verify(); vi.useRealTimers(); });

  const setup = (initial: { id: number; name: string }[] = []) => {
    const fixture = TestBed.createComponent(EntitiesComponent);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/entities').flush({ entities: initial });
    for (const entity of initial) http.expectOne(`/api/entity-configurations/${entity.id}`).flush({ prompt: '', revision: 0, attributes: [] });
    fixture.detectChanges();
    let nextId = 1;
    const root = fixture.nativeElement as HTMLElement;
    for (const dialog of Array.from(root.querySelectorAll('dialog'))) {
      dialog.showModal = () => dialog.setAttribute('open', '');
      dialog.close = () => dialog.removeAttribute('open');
    }
    const type = (selector: string, value: string) => {
      const input = root.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector)!;
      input.value = value;
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    };
    const create = (name: string) => {
      type('input', name);
      root.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      const pending = http.match((request) => request.method === 'POST');
      for (const request of pending) {
        expect(Object.keys(request.request.body)).toEqual(['name']);
        request.flush({ entity: { id: nextId++, name: request.request.body.name } });
      }
      fixture.detectChanges();
    };
    return { fixture, root, type, create, http };
  };

  it('loads saved IDs and names with blank definition drafts', () => {
    const { root } = setup([{ id: 42, name: 'Saved customer' }]);
    expect(root.textContent).toContain('Saved customer');
    expect(root.querySelector<HTMLTextAreaElement>('#entity-definition-42')!.value).toBe('');
  });

  it('prevents repeated saves and keeps input on failure', () => {
    const { fixture, root, type, http } = setup();
    type('input', 'Customer');
    fixture.componentInstance.createEntity();
    fixture.componentInstance.createEntity();
    fixture.detectChanges();
    expect(root.querySelector<HTMLButtonElement>('button[type=submit]')!.disabled).toBe(true);
    http.expectOne('/api/entities').flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(root.querySelector<HTMLInputElement>('input')!.value).toBe('Customer');
    expect(root.querySelector('[role=alert]')!.textContent).toContain('Could not save');
    expect(fixture.componentInstance.entities()).toEqual([]);
    fixture.componentInstance.createEntity();
    http.expectOne('/api/entities').flush({ entity: { id: 71, name: 'Customer' } });
    fixture.detectChanges();
    expect(root.querySelector('#entity-definition-71')).not.toBeNull();
  });

  it('keeps creation available without a notice after a failed load', () => {
    const fixture = TestBed.createComponent(EntitiesComponent);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/entities').flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('No entities yet');
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('Could not load entities');
    expect(fixture.nativeElement.querySelector('button[type=submit]').disabled).toBe(false);

  });

  it('rejects whitespace and duplicate names without creating another entity', () => {
    const { root, create } = setup();
    create('   ');
    expect(root.querySelector('textarea')).toBeNull();
    create('Customer');
    create(' customer ');
    expect(root.textContent).toMatch(/already|duplicate|exists/i);
    expect(root.querySelectorAll('.entity-cards wo-card')).toHaveLength(1);
    expect(root.querySelector('.entity-cards')!.textContent).toContain('Customer');
  });

  it('keeps definitions separate for each entity', () => {
    const { fixture, root, type, create } = setup();
    create('Customer');
    type('textarea', 'Customer has an email and a name.');
    create('Order');
    expect(root.querySelector<HTMLTextAreaElement>('#entity-definition-2')!.value).toBe('');
    type('#entity-definition-2', 'Order has a total.');
    expect(root.querySelectorAll('.entity-definition')).toHaveLength(1);
    expect(root.querySelector('#entity-definition-1')).toBeNull();
    root.querySelector<HTMLButtonElement>('.entity-title-select')!.click();
    fixture.detectChanges();
    expect(root.querySelector<HTMLTextAreaElement>('#entity-definition-1')!.value).toBe('Customer has an email and a name.');
    expect(root.querySelector('.entity-editor [aria-label="Edit Customer"]')).toBeNull();
    expect(root.querySelector('.entity-schema [aria-label="Edit Customer"]')).not.toBeNull();
    expect(root.querySelectorAll('.entity-cards wo-card')).toHaveLength(2);
  });
  it('edits names without losing prompts, rejects duplicates and deletes the selected entity', () => {
    const { fixture, root, type, http } = setup([{ id: 1, name: 'Customer' }, { id: 2, name: 'Order' }]);
    root.querySelector<HTMLButtonElement>('[aria-label="Edit Customer"]')!.click();
    fixture.detectChanges();
    type('#entity-definition-1', 'Keep this prompt');
    expect(root.querySelector<HTMLInputElement>('input')!.value).toBe('Customer');
    type('input', ' order ');
    fixture.componentInstance.createEntity();
    http.expectNone((request) => request.method === 'PUT');
    type('input', 'Customers');
    fixture.componentInstance.createEntity();
    http.expectOne('/api/entities/1').flush({ entity: { id: 1, name: 'Customers' } });
    fixture.detectChanges();
    expect(root.querySelector<HTMLTextAreaElement>('#entity-definition-1')!.value).toBe('Keep this prompt');
    expect(root.querySelector('.entity-cards')!.textContent).toContain('Customers');
    const dialog = root.querySelector('dialog')!;
    dialog.showModal = () => dialog.setAttribute('open', '');
    dialog.close = () => dialog.removeAttribute('open');
    root.querySelector<HTMLButtonElement>('[aria-label="Delete Customers"]')!.click();
    fixture.componentInstance.deleteEntity();
    const deletion = http.expectOne('/api/entities/1');
    expect(deletion.request.method).toBe('DELETE');
    deletion.flush({ deleted: true });
    fixture.detectChanges();
    expect(root.querySelector('#entity-definition-1')).toBeNull();
    expect(root.querySelector('#entity-definition-2')).not.toBeNull();
  });

  it('waits for saved schema, generates once and preserves attributes on failure', () => {
    vi.useFakeTimers();
    const fixture = TestBed.createComponent(EntitiesComponent);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/entities').flush({ entities: [{ id: 9, name: 'Product' }] });
    const component = fixture.componentInstance;
    component.entities()[0].definition.setValue('New prompt');
    component.generate(component.entities()[0]);
    http.expectNone(request => request.method === 'POST');
    http.expectOne('/api/entity-configurations/9').flush({ prompt: 'Saved product', revision: 2, attributes: [] });
    component.entities()[0].definition.setValue('Product with price');
    component.generate(component.entities()[0]);
    component.generate(component.entities()[0]);
    const generation = http.expectOne('/api/entity-configurations/9');
    expect(generation.request.body).toEqual({ prompt: 'Product with price', revision: 2, run_id: expect.any(String) });
    http.expectOne(request => request.url.includes('/logs/')).flush({ entries: [], cursor: 0, more: false });
    generation.flush({ revision: 3, attributes: [{ name: 'price', data_type: 'decimal', nullable: false, description: 'Unit price' }] });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('Unit price');
    expect(fixture.nativeElement.querySelector('.entity-attribute').textContent).toContain('price');
    vi.advanceTimersByTime(750);
    http.expectOne(request => request.url.includes('/logs/')).flush({ entries: [{ timestamp: '2026-11-03T01:00:00Z', level: 'INFO', event: 'entity.generation.completed' }], cursor: 100, more: false });
    component.generate(component.entities()[0]);
    http.expectOne(request => request.url.includes('/logs/')).flush({ entries: [], cursor: 0, more: false });
    http.expectOne('/api/entity-configurations/9').flush({ error: 'Agent unavailable' }, { status: 502, statusText: 'Bad Gateway' });
    expect(component.entities()[0].attributes?.[0].name).toBe('price');
    expect(component.entities()[0].definition.value).toBe('Product with price');
    expect(component.generationError()).toBe('Agent unavailable');
    vi.advanceTimersByTime(750);
    http.expectOne(request => request.url.includes('/logs/')).flush({ entries: [], cursor: 0, more: false });
    fixture.destroy();
  });

  it('edits name, type and required flag and persists deletion without generating code', () => {
    const { fixture, http, root } = setup([{ id: 9, name: 'Product' }]);
    const component = fixture.componentInstance;
    component.entities.update(items => items.map(item => ({ ...item, revision: 2, attributes: [
      { name: 'price', data_type: 'decimal', nullable: false, description: 'Hidden description' },
      { name: 'stock', data_type: 'integer', nullable: false, description: '' },
    ] })));
    fixture.detectChanges();
    expect(root.textContent).not.toContain('Hidden description');
    root.querySelector<HTMLButtonElement>('[aria-label="Edit Product attribute price"]')!.click();
    component.attributeForm.setValue({ name: 'cost', data_type: 'float', required: false });
    component.saveAttribute(component.entities()[0]);
    const save = http.expectOne('/api/entity-configurations/9');
    expect(save.request.method).toBe('PUT');
    expect(save.request.body.attributes[0]).toMatchObject({ name: 'cost', data_type: 'float', nullable: true });
    save.flush({ revision: 3, attributes: save.request.body.attributes });
    expect(component.editingAttribute()).toBeNull();
    component.deleteAttribute(component.entities()[0], 1);
    const deletion = http.expectOne('/api/entity-configurations/9');
    expect(deletion.request.body.revision).toBe(3);
    expect(deletion.request.body.attributes).toHaveLength(1);
    deletion.flush({}, { status: 409, statusText: 'Conflict' });
    expect(component.entities()[0].attributes).toHaveLength(2);
    expect(component.attributeError()).toBeTruthy();
    http.expectNone(request => request.method === 'POST');
  });

  it('renders current agent logs below Generate and stops polling on navigation', () => {
    vi.useFakeTimers();
    const { fixture, http, root } = setup([{ id: 9, name: 'Product' }]);
    const component = fixture.componentInstance;
    component.entities()[0].definition.setValue('Add price');
    component.generate(component.entities()[0]);
    const generation = http.expectOne('/api/entity-configurations/9');
    http.expectOne(request => request.url.includes('/logs/')).flush({ entries: [
      { timestamp: '2026-11-03T01:00:00Z', level: 'INFO', function: 'workflow.step', event: 'function.started', step: 'draft_definition' },
    ], cursor: 120, more: false });
    fixture.detectChanges();
    expect(root.querySelector('.entity-editor [role=log]')!.textContent).toContain('draft_definition');
    expect(root.querySelector('.entity-schema [role=log]')).toBeNull();
    fixture.destroy();
    expect(generation.cancelled).toBe(true);
    vi.advanceTimersByTime(2000);
    http.expectNone(request => request.url.includes('/logs/'));
  });

  it('finishes the previous entity log stream when another generation starts immediately', () => {
    vi.useFakeTimers();
    const { fixture, http } = setup([{ id: 1, name: 'First' }, { id: 2, name: 'Second' }]);
    const component = fixture.componentInstance;
    component.entities()[0].definition.setValue('First attributes');
    component.entities()[1].definition.setValue('Second attributes');
    component.generate(component.entities()[0]);
    http.expectOne(request => request.url.includes('/1/logs/')).flush({ entries: [], cursor: 1, more: false });
    http.expectOne('/api/entity-configurations/1').flush({ revision: 1, attributes: [] });
    component.generate(component.entities()[1]);
    http.expectOne(request => request.url.includes('/2/logs/')).flush({ entries: [], cursor: 1, more: false });
    const second = http.expectOne('/api/entity-configurations/2');
    vi.advanceTimersByTime(750);
    http.expectOne(request => request.url.includes('/1/logs/')).flush({ entries: [
      { timestamp: '2026-11-03T01:00:00Z', level: 'INFO', event: 'entity.generation.completed' },
    ], cursor: 2, more: false });
    http.expectOne(request => request.url.includes('/2/logs/')).flush({ entries: [], cursor: 1, more: false });
    expect(component.entities()[0].logs?.at(-1)?.event).toBe('entity.generation.completed');
    expect(component.entities()[1].logs).toEqual([]);
    fixture.destroy();
    expect(second.cancelled).toBe(true);
  });

});
