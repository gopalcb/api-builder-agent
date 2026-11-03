import { infrastructureGraph, lambdaName } from './infrastructure.model';

it('creates one entity-prefixed unique AWS-valid Lambda handler per saved entity', () => {
  const entities = [{ id: 1, name: 'Order Items' }, { id: 2, name: 'Order.Items' }, { id: 3, name: 'É'.repeat(100) }, { id: 4, name: '你好' }];
  const names = entities.map(entity => lambdaName(entity, 'staging'));
  expect(new Set(names).size).toBe(4);
  expect(names[0]).toBe('Order-Items-1-staging-handler');
  for (const name of names) expect(name).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
  const graph = infrastructureGraph(entities, 'staging', null);
  expect(graph.resources.filter(resource => resource.id.startsWith('lambda-'))).toHaveLength(4);
  for (const entity of entities) {
    expect(graph.relationships).toContainEqual(expect.objectContaining({ source: 'gateway', target: `lambda-${entity.id}`, candidate: false }));
    expect(graph.relationships).toContainEqual(expect.objectContaining({ source: `lambda-${entity.id}`, target: `table-${entity.id}`, candidate: false }));
  }
  expect(graph.resources.find(resource => resource.id === 'redis')?.status).toBe('Conditional');
});

it('connects the empty Lambda and DynamoDB placeholders with an explicitly candidate request path', () => {
  const graph = infrastructureGraph([], 'dev', null);
  expect(graph.nodes.map(node => node.id)).toEqual(graph.resources.map(resource => resource.id));
  expect(graph.resources.map(resource => resource.service)).toEqual(expect.arrayContaining(['CloudFront', 'API Gateway', 'Cognito', 'Lambda', 'DynamoDB', 'S3', 'SQS', 'SNS', 'ElastiCache', 'ALB']));
  expect(graph.resources.find(resource => resource.id === 'lambda')?.status).toBe('Conditional');
  expect(graph.resources.find(resource => resource.id === 'dynamodb')?.status).toBe('Conditional');
  expect(graph.relationships).toContainEqual(expect.objectContaining({ source: 'gateway', target: 'lambda', candidate: true }));
  expect(graph.relationships).toContainEqual(expect.objectContaining({ source: 'lambda', target: 'dynamodb', candidate: true }));
});

it('uses separate asynchronous worker and alternative ingress branches without isolated nodes or publisher loops', () => {
  for (const entities of [[], [{ id: 7, name: 'Customer' }, { id: 8, name: 'Order' }]]) {
    const graph = infrastructureGraph(entities, 'dev', null);
    const ids = new Set(graph.nodes.map(node => node.id));
    for (const edge of graph.relationships) {
      expect(ids.has(edge.source)).toBe(true);
      expect(ids.has(edge.target)).toBe(true);
      expect(edge.source).not.toBe(edge.target);
    }
    for (const id of ids) expect(graph.relationships.some(edge => edge.source === id || edge.target === id)).toBe(true);
    expect(graph.relationships.filter(edge => edge.source === 'sqs').map(edge => edge.target)).toEqual(['async-worker']);
    expect(graph.relationships.some(edge => edge.source === 'async-worker' && edge.target === 'sqs')).toBe(false);
    expect(graph.relationships.some(edge => edge.source === 'alb' && edge.target === 'gateway')).toBe(false);
    expect(graph.resources.find(resource => resource.id === 'async-worker')?.status).toBe('Conditional');
    expect(graph.resources.find(resource => resource.id === 'alb')?.status).toBe('Deferred');
    for (const id of ['redis', 'sns', 'sqs', 'async-worker', 'alb']) {
      expect(graph.relationships.filter(edge => edge.source === id || edge.target === id).every(edge => edge.candidate)).toBe(true);
    }
    const handlers = entities.length ? entities.map(entity => `lambda-${entity.id}`) : ['lambda'];
    for (const handler of handlers) {
      for (const target of ['redis', 'sns', 'sqs']) expect(graph.relationships).toContainEqual(expect.objectContaining({ source: handler, target, candidate: true }));
      expect(graph.relationships).toContainEqual(expect.objectContaining({ source: 'alb', target: handler, candidate: true }));
    }
  }
});

it('reflects service recommendations while retaining candidate wiring for ownership review', () => {
  const graph = infrastructureGraph([{ id: 7, name: 'Customer' }], 'dev', { summary: 'Async', services: { sns: true, sqs: true, redis: true }, recommendations: [], requirements: [] });
  expect(graph.nodes.some(node => node.id === 'lambda')).toBe(false);
  expect(graph.resources.find(resource => resource.id === 'lambda-7')?.name).toBe('Customer-7-dev-handler');
  expect(graph.resources.find(resource => resource.id === 'sqs')?.status).toBe('Included');
  expect(graph.relationships).toContainEqual(expect.objectContaining({ source: 'sns', target: 'sqs', label: 'Fan-out', candidate: true }));
  expect(graph.relationships).toContainEqual(expect.objectContaining({ source: 'lambda-7', target: 'redis', label: 'Cache lookup', candidate: true }));
  expect(graph.relationships).toContainEqual(expect.objectContaining({ source: 'gateway', target: 'cognito', label: 'JWT validation' }));
});
