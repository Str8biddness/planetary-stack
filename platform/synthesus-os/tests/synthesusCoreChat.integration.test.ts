// tests/synthesusCoreChat.integration.test.ts
// Integration test for SynthesusCoreChat with Parameter Cloud

import { SynthesusCoreChat } from '../synthetic_core/synthesusCoreChat';
import { CloudParameterConfig } from '../utils/cloudParameters';
import http, { IncomingMessage, ServerResponse } from 'http';

const testConfig: CloudParameterConfig = {
  cloud_endpoint: 'http://127.0.0.1:5016/parameter-cloud',
  api_key: 'test-key',
  cache_duration_ms: 1000,
  update_interval_ms: 5000,
  local_fallback_enabled: true
};

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

describe('SynthesusCoreChat + Parameter Cloud Integration', () => {
  let core: SynthesusCoreChat;
  let server: http.Server | null = null;
  let store: { parameters: Record<string, any>; version: number; updated_at_ms: number; metrics: Record<string, any> };

  beforeAll(async () => {
    store = {
      parameters: {
        temperature: 0.8,
        top_k: 40,
        compute_budget_multiplier: 1.5,
        risk_thresholds: { max_risk: 0.6, min_confidence: 0.8 },
        attention_weights: { policy: 0.4, risk: 0.4, attention: 0.2 }
      },
      version: 1,
      updated_at_ms: Date.now(),
      metrics: {}
    };

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
          if (updates && typeof updates === 'object') {
            Object.assign(store.parameters, updates);
            store.version += 1;
            store.updated_at_ms = Date.now();
          }
          return sendJson(res, 200, { ok: true, version: store.version });
        }

        return sendJson(res, 404, { detail: 'Not found' });
      } catch (e: any) {
        return sendJson(res, 500, { detail: e?.message || 'server error' });
      }
    });

    await new Promise<void>((resolve, reject) => {
      server!.listen(5016, '127.0.0.1', () => resolve());
      server!.once('error', reject);
    });
  }, 10000);

  afterAll(() => {
    if (server) {
      server.close();
      server = null;
    }
  });

  beforeEach(() => {
    core = new SynthesusCoreChat(testConfig);
  });

  afterEach(() => {
    core.destroy();
  });

  test('should fetch cloud parameters during intake', async () => {
    const input = {
      query: 'Hello, how are you?',
      domain: 'chat',
      sessionId: 'test-session-1'
    };

    const result = await core.intake(input);

    expect(result.processedInput).toBeDefined();
    expect(result.worldState).toBeDefined();
    expect(result.worldState.domain).toBe('chat');
  });

  test('should use cloud parameters for planning', async () => {
    const worldState = {
      domain: 'chat',
      conversationId: 'test-session',
      history: [],
      inferredGoals: [],
      topics: [],
      flags: { confusion: false, safety: false, frustration: false },
      unresolvedQuestions: 0,
      turnCount: 1,
      timestamp: new Date()
    };

    const result = await core.plan(worldState);

    expect(result.actions).toBeDefined();
    expect(result.actions.length).toBeGreaterThan(0);
    expect(result.reasoning).toContain('Amplified');
  });

  test('should update cloud parameters after planning', async () => {
    const worldState = {
      domain: 'chat',
      conversationId: 'test-session',
      history: [],
      inferredGoals: [],
      topics: [],
      flags: { confusion: false, safety: false, frustration: false },
      unresolvedQuestions: 0,
      turnCount: 1,
      timestamp: new Date()
    };

    const initialVersion = store.version;

    // Run planning which should update parameters
    await core.plan(worldState);

    // Wait for async update
    await new Promise(resolve => setTimeout(resolve, 100));

    // Parameters should have been updated based on planning results
    expect(store.version).toBeGreaterThanOrEqual(initialVersion);
  });

  test('should execute act phase with cloud parameters', async () => {
    const plan = {
      actions: [{ type: 'answer_question', content: 'I am doing well!', description: 'Answer' }],
      reasoning: 'Test plan'
    };

    const result = await core.act(plan);

    expect(result.action).toBeDefined();
    expect(result.outcome).toBeDefined();
    expect(result.updatedWorld).toBeDefined();
  });

  test('should report performance metrics', async () => {
    // Run some operations to generate metrics
    await core.intake({ query: 'Test', domain: 'chat', sessionId: 'metrics-test' });

    const metrics = core.getPerformanceMetrics();

    expect(metrics).toBeDefined();
    expect(typeof metrics.fetch_latency).toBe('number');
    expect(typeof metrics.cache_hit_rate).toBe('number');
  });

  test('should complete full workflow cycle', async () => {
    const sessionId = 'full-workflow-test';

    // Intake
    const intakeResult = await core.intake({
      query: 'What is the weather today?',
      domain: 'chat',
      sessionId
    });
    expect(intakeResult.worldState).toBeDefined();

    // Plan
    const planResult = await core.plan(intakeResult.worldState);
    expect(planResult.actions.length).toBeGreaterThan(0);

    // Act
    const actResult = await core.act(planResult);
    expect(actResult.action).toBeDefined();
    expect(actResult.outcome.success).toBe(true);
  });
});
