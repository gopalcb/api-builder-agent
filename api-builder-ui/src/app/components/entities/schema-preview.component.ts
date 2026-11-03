import { ChangeDetectionStrategy, Component } from '@angular/core';
import { WoCardComponent } from '../../../theme/components';

interface SchemaField { name: string; type: string; key?: 'PK' | 'FK'; }
interface SchemaEntity { name: string; fields: SchemaField[]; }

@Component({
  selector: 'app-schema-preview',
  imports: [WoCardComponent],
  templateUrl: './schema-preview.component.html',
  styleUrl: './schema-preview.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SchemaPreviewComponent {
  readonly tables: SchemaEntity[] = [
    { name: 'Customers', fields: [
      { name: 'id', type: 'uuid', key: 'PK' },
      { name: 'name', type: 'varchar' },
      { name: 'email', type: 'varchar' },
      { name: 'created_at', type: 'timestamp' },
    ] },
    { name: 'Orders', fields: [
      { name: 'id', type: 'uuid', key: 'PK' },
      { name: 'customer_id', type: 'uuid', key: 'FK' },
      { name: 'status', type: 'varchar' },
      { name: 'total', type: 'decimal' },
    ] },
    { name: 'OrderItems', fields: [
      { name: 'id', type: 'uuid', key: 'PK' },
      { name: 'order_id', type: 'uuid', key: 'FK' },
      { name: 'quantity', type: 'integer' },
      { name: 'unit_price', type: 'decimal' },
    ] },
  ];
}
