import { createEdges, createNodes, CurveFactory, Point, Position } from 'ngx-vflow';

export interface InfrastructureEntity { id: number; name: string; }
export interface InfrastructureProposal {
  summary: string;
  services: { sqs: boolean; sns: boolean; redis: boolean };
  recommendations: string[];
  requirements: string[];
}
export interface InfrastructureResource {
  id: string; service: string; name: string; description: string;
  status: 'Included' | 'Conditional' | 'Deferred'; x: number; y: number;
}
export interface InfrastructureRelationship {
  source: string; target: string; label: string; candidate?: boolean;
  sourceHandle?: Position; targetHandle?: Position; via?: Point[]; labelPoint?: Point; hideLabel?: boolean;
}

export function lambdaName(entity: InfrastructureEntity, environment: string): string {
  const prefix = entity.name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'entity';
  const suffix = `-${entity.id}-${environment}-handler`;
  return prefix.slice(0, 64 - suffix.length) + suffix;
}

export function infrastructureGraph(entities: InfrastructureEntity[], environment: string, proposal: InfrastructureProposal | null) {
  const optionalY = 180 + Math.max(1, entities.length) * 160 + 160;
  const resources: InfrastructureResource[] = [
    { id: 'cloudfront', service: 'CloudFront', name: 'Edge distribution', description: 'Delivers static assets from a private S3 origin using origin access control. API traffic is forwarded without response caching by default.', status: 'Included', x: 0, y: 180 },
    { id: 's3', service: 'S3', name: 'Static assets', description: 'Private bucket for static assets. Add separate upload storage and signed URLs when required.', status: 'Included', x: 0, y: 0 },
    { id: 'gateway', service: 'API Gateway', name: 'API ingress', description: 'Routes authenticated API requests to the matching entity Lambda. JWT validation uses Cognito; REST API may be needed for a saved gateway cache policy.', status: 'Included', x: 280, y: 180 },
    { id: 'cognito', service: 'Cognito', name: 'User pool', description: 'Issues access tokens to clients. API Gateway validates JWTs; requests do not proxy through the user pool. Existing identity settings need review.', status: 'Included', x: 280, y: 0 },
    { id: 'redis', service: 'ElastiCache', name: 'Redis cache', description: 'Optional shared cache. Requires a VPC, security groups, TTL and invalidation policy. Dashed lookup paths are illustrative; private responses remain uncached without explicit isolation.', status: proposal?.services.redis ? 'Included' : 'Conditional', x: 840, y: 0 },
  ];
  const relationships: InfrastructureRelationship[] = [
    { source: 'cloudfront', target: 's3', label: 'Static origin', sourceHandle: 'top', targetHandle: 'bottom' },
    { source: 'cloudfront', target: 'gateway', label: 'API requests' },
    { source: 'gateway', target: 'cognito', label: 'JWT validation', sourceHandle: 'top', targetHandle: 'bottom' },
  ];
  const handlers = entities.length ? entities.map(entity => ({ id: `lambda-${entity.id}`, table: `table-${entity.id}`, entity })) : [{ id: 'lambda', table: 'dynamodb', entity: null }];
  handlers.forEach(({ id, table, entity }, index) => {
    const y = 180 + index * 160;
    resources.push({ id, service: 'Lambda', name: entity ? lambdaName(entity, environment) : 'Entity functions', description: entity ? `Dedicated ${entity.name} API handler. Size memory, timeout, concurrency and least-privilege execution role during review.` : 'Add saved entities to propose a dedicated Lambda function for each entity, using its name as the function prefix. Dashed request paths show the intended pattern.', status: entity ? 'Included' : 'Conditional', x: 560, y });
    resources.push({ id: table, service: 'DynamoDB', name: entity ? `${entity.name} table` : 'Entity storage', description: entity ? `Proposed on-demand table for ${entity.name}. Review keys, access patterns, indexes and backup requirements before implementation.` : 'Add saved entities to propose one DynamoDB table per entity. Keys and access patterns need review.', status: entity ? 'Included' : 'Conditional', x: 840, y });
    relationships.push(
      { source: 'gateway', target: id, label: 'Invoke', candidate: !entity },
      { source: id, target: table, label: 'Read / write', candidate: !entity },
      { source: id, target: 'redis', label: 'Cache lookup', candidate: true, via: [{ x: 800, y: y + 48 }, { x: 800, y: 48 }], labelPoint: { x: 800, y: 116 }, hideLabel: index > 0 },
      { source: id, target: 'sns', label: 'Publish', candidate: true, sourceHandle: 'left', targetHandle: 'right', via: [{ x: 520, y: y + 48 }, { x: 520, y: optionalY + 48 }], labelPoint: { x: 520, y: optionalY - 80 }, hideLabel: index > 0 },
      { source: id, target: 'sqs', label: 'Enqueue', candidate: true, sourceHandle: 'bottom', targetHandle: 'top', via: [{ x: 656, y: y + 120 }, { x: 776, y: y + 120 }, { x: 776, y: optionalY - 40 }, { x: 656, y: optionalY - 40 }], labelPoint: { x: 716, y: optionalY - 40 }, hideLabel: index > 0 },
      { source: 'alb', target: id, label: 'Alternative ingress', candidate: true, via: [{ x: 488, y: optionalY - 112 }, { x: 488, y: y + 48 }], labelPoint: { x: 340, y: optionalY - 112 }, hideLabel: index > 0 },
      { source: 'async-worker', target: table, label: 'Process / write', candidate: true, sourceHandle: 'right', targetHandle: 'right', via: [{ x: 1080, y: optionalY + 48 }, { x: 1080, y: y + 48 }], labelPoint: { x: 1080, y: optionalY - 80 }, hideLabel: index > 0 },
    );
  });
  resources.push(
    { id: 'alb', service: 'ALB', name: 'Alternative ingress', description: 'Deferred alternative CloudFront origin with Lambda targets. This is not a serial hop before API Gateway and does not enable containerized deployment. Choose one ingress pattern during review.', status: 'Deferred', x: 0, y: optionalY - 160 },
    { id: 'sns', service: 'SNS', name: 'Event topic', description: 'Optional notifications and fan-out. Dashed publish and subscription paths illustrate possible wiring; the agent must confirm event ownership and delivery policy.', status: proposal?.services.sns ? 'Included' : 'Conditional', x: 280, y: optionalY },
    { id: 'sqs', service: 'SQS', name: 'Work queue + DLQ', description: 'Optional asynchronous work with bounded retries, dead-letter queue and idempotent consumers. Lambda event-source mapping polls the queue and invokes a separate background worker.', status: proposal?.services.sqs ? 'Included' : 'Conditional', x: 560, y: optionalY },
    { id: 'async-worker', service: 'Lambda', name: 'Background worker', description: 'Conditional, separate asynchronous role—not an entity API handler. Its event-source mapping polls SQS and invokes it in batches. Consumer ownership, target tables and idempotent writes require review; it must not enqueue back into its own source queue.', status: 'Conditional', x: 840, y: optionalY },
  );
  relationships.push(
    { source: 'cloudfront', target: 'alb', label: 'Alternative origin', candidate: true, sourceHandle: 'bottom', targetHandle: 'top' },
    { source: 'sns', target: 'sqs', label: 'Fan-out', candidate: true },
    { source: 'sqs', target: 'async-worker', label: 'Poll / invoke', candidate: true },
  );
  return {
    resources, relationships,
    nodes: createNodes(resources.map(resource => ({ id: resource.id, type: 'html-template' as const, point: { x: resource.x, y: resource.y }, width: 192, height: 96, draggable: false, data: {
      ...resource,
      sourcePorts: [...new Set(relationships.filter(edge => edge.source === resource.id).map(edge => edge.sourceHandle ?? 'right'))],
      targetPorts: [...new Set(relationships.filter(edge => edge.target === resource.id).map(edge => edge.targetHandle ?? 'left'))],
    } }))),
    edges: createEdges(relationships.map((relationship, index) => {
      const route: CurveFactory = ({ sourcePoint, targetPoint }) => ({
        path: [sourcePoint, ...relationship.via!, targetPoint].map((point, pointIndex) => `${pointIndex ? 'L' : 'M'} ${point.x} ${point.y}`).join(' '),
        ...(relationship.labelPoint ? { labelPoints: { start: sourcePoint, center: relationship.labelPoint, end: targetPoint } } : {}),
      });
      return { id: `edge-${index}`, ...relationship, sourceHandle: relationship.sourceHandle ?? 'right', targetHandle: relationship.targetHandle ?? 'left', type: 'template' as const, data: { candidate: !!relationship.candidate }, curve: relationship.via ? route : 'smooth-step' as const, markers: { end: { type: 'arrow-closed' as const, color: 'var(--wo-muted)' } }, edgeLabels: relationship.hideLabel ? {} : { center: { type: 'default' as const, text: relationship.label, style: { fontSize: '10px', fill: 'var(--wo-muted)' } } } };
    })),
  };
}
