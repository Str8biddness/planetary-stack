// tests/cloudParameters.test.ts
// Basic integration test for cloud parameters functionality

import { CloudParameterManager, CloudParameterConfig } from '../utils/cloudParameters';
import http, { IncomingMessage, ServerResponse } from 'http';

const testConfig: CloudParameterConfig = {
  cloud_endpoint: 'http://127.0.0.1:5015/parameter-cloud',
  api_key: process.env.SYNTHESUS_API_KEY || 'test-key',
  cache_duration_ms: 5000, // Shorter for testing
  update_interval_ms: 30000,
  local_fallback_enabled: true
};

async function waitForServerReady(url: string, timeoutMs: number): Promise<void> {
  const start = Date.now();
  while ((Date.now() - start) < timeoutMs) {
    try {
      const res = await fetch(url, { method: 'GET' });
      if (res.ok) return;
    } catch {
      // ignore
    }
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error(`Timed out waiting for server at ${url}`);
}

async function readJson(req: IncomingMessage): Promise<any> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  if (chunks.length === 0) return {};
  const raw = Buffer.concat(chunks).toString('utf-8');
  return raw ? JSON.parse(raw) : {};
}

function sendJson(res: ServerResponse, status: number, body: any) {
  const payload = JSON.stringify(body);
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(payload);
}

describe('Cloud Parameter Manager Integration', () => {
  let manager: CloudParameterManager;
  let server: http.Server | null = null;
  let store: { parameters: Record<string, any>; version: number; updated_at_ms: number; metrics: Record<string, any> };

  beforeEach(() => {
    manager = new CloudParameterManager(testConfig);
  });

  afterEach(() => {
    if (manager) {
      manager.destroy();
    }
  });

  beforeAll(async () => {
    store = { parameters: {}, version: 0, updated_at_ms: Date.now(), metrics: {} };

    server = http.createServer(async (req, res) => {
      try {
        const url = new URL(req.url || '/', 'http://127.0.0.1');

        if (req.method === 'GET' && url.pathname === '/parameter-cloud/fetch') {
          return sendJson(res, 200, {
            parameters: store.parameters,
            version: store.version,
            updated_at_ms: store.updated_at_ms,
          });
        }

        if (req.method === 'POST' && url.pathname === '/parameter-cloud/update') {
          const body = await readJson(req);
          const updates = body?.updates;
          if (!updates || typeof updates !== 'object') {
            return sendJson(res, 400, { detail: 'updates must be an object' });
          }
          Object.assign(store.parameters, updates);
          store.version += 1;
          store.updated_at_ms = Date.now();
          if (body?.performance_metrics && typeof body.performance_metrics === 'object') {
            Object.assign(store.metrics, body.performance_metrics);
          }
          return sendJson(res, 200, { ok: true, version: store.version });
        }

        if (req.method === 'POST' && url.pathname === '/parameter-cloud/metrics') {
          const body = await readJson(req);
          const metrics = body?.metrics;
          if (metrics && typeof metrics === 'object') {
            Object.assign(store.metrics, metrics);
          }
          return sendJson(res, 200, { ok: true });
        }

        return sendJson(res, 404, { detail: 'Not found' });
      } catch (e: any) {
        return sendJson(res, 500, { detail: e?.message || 'server error' });
      }
    });

    await new Promise<void>((resolve, reject) => {
      server!.listen(5015, '127.0.0.1', () => resolve());
      server!.once('error', reject);
    });

    await waitForServerReady('http://127.0.0.1:5015/parameter-cloud/fetch', 5000);
  }, 20000);

  afterAll(() => {
    if (server) {
      server.close();
      server = null;
    }
  });

  test('should initialize with local defaults when cloud unavailable', async () => {
    const params = await manager.getParameters();

    expect(params).toBeDefined();
    expect(params.temperature).toBe(1.0);
    expect(params.top_k).toBe(50);
    expect(params.compute_budget_multiplier).toBe(1.0);
    expect(params.attention_weights).toEqual({ policy: 0.3, risk: 0.3, attention: 0.4 });
  });

  test('should return cached parameters on subsequent calls', async () => {
    const params1 = await manager.getParameters();
    const params2 = await manager.getParameters();

    expect(params1).toEqual(params2);
  });

  test('should track performance metrics', async () => {
    await manager.getParameters();
    const metrics = manager.getPerformanceMetrics();

    expect(metrics).toBeDefined();
    expect(typeof metrics.fetch_latency).toBe('number');
    expect(typeof metrics.cache_hit_rate).toBe('number');
    expect(metrics.cache_hit_rate).toBeGreaterThanOrEqual(0);
    expect(metrics.cache_hit_rate).toBeLessThanOrEqual(1);
  });

  test('should handle parameter updates', async () => {
    const initialParams = await manager.getParameters();
    const initialMultiplier = initialParams.compute_budget_multiplier || 1.0;

    // Update parameters
    await manager.updateParameters({
      compute_budget_multiplier: initialMultiplier * 1.1
    });

    // Force cache invalidation by waiting
    await new Promise(resolve => setTimeout(resolve, 6000));

    const updatedParams = await manager.getParameters();
    expect(updatedParams.compute_budget_multiplier).toBe(initialMultiplier * 1.1);
  }, 15000);

  test('should handle multiple parameter updates', async () => {
    const updates = {
      temperature: 1.2,
      top_k: 60,
      risk_thresholds: { max_risk: 0.8, min_confidence: 0.7 }
    };

    await manager.updateParameters(updates);

    // Force cache invalidation
    await new Promise(resolve => setTimeout(resolve, 6000));

    const params = await manager.getParameters();
    expect(params.temperature).toBe(1.2);
    expect(params.top_k).toBe(60);
    expect(params.risk_thresholds?.max_risk).toBe(0.8);
  }, 15000);
});
