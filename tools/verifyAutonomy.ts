// scripts/verifyAutonomy.ts

import { enforceAutonomy, ExecutionRecommendation } from '../packages/core/utils/guardrails';
import { AUTO_CONFIG, AutonomyLevel, setKillSwitch, GLOBAL_KILL_SWITCH } from '../packages/organs/autonomyConfig';

async function runTests() {
  console.log('--- Synthesus V3 Autonomy Verification ---\n');

  // Test 1: Advisor Mode (Level 1)
  console.log('Test 1: Advisor Mode (SysOps)');
  AUTO_CONFIG['sysops'].level = AutonomyLevel.ADVISOR;
  const t1 = enforceAutonomy('sysops', 'restart_service', { riskScore: 0.9, confidenceMargin: 0.9, attentionSensitivity: 0.1 });
  console.log(`Result: ${t1} (Expected: request_confirmation)\n`);

  // Test 2: Co-pilot Mode (Level 2)
  console.log('Test 2: Co-pilot Mode (GM)');
  AUTO_CONFIG['gm'].level = AutonomyLevel.COPILOT;
  const t2 = enforceAutonomy('gm', 'move_character', { riskScore: 0.9, confidenceMargin: 0.9, attentionSensitivity: 0.1 });
  console.log(`Result: ${t2} (Expected: request_confirmation)\n`);

  // Test 3: Autopilot Mode - Safe (Level 3)
  console.log('Test 3: Autopilot Mode - Safe (Chat)');
  AUTO_CONFIG['chat'].level = AutonomyLevel.AUTOPILOT;
  AUTO_CONFIG['chat'].maxRiskThreshold = 0.5;
  AUTO_CONFIG['chat'].minConfidenceThreshold = 0.5;
  const t3 = enforceAutonomy('chat', 'call_api', { riskScore: 0.8, confidenceMargin: 0.8, attentionSensitivity: 0.1 });
  console.log(`Result: ${t3} (Expected: execute)\n`);

  // Test 4: Autopilot Mode - High Risk (Level 3)
  console.log('Test 4: Autopilot Mode - High Risk (Chat)');
  const t4 = enforceAutonomy('chat', 'call_api', { riskScore: 0.3, confidenceMargin: 0.8, attentionSensitivity: 0.1 });
  console.log(`Result: ${t4} (Expected: request_confirmation)\n`);

  // Test 5: Autopilot Mode - Low Confidence (Level 3)
  console.log('Test 5: Autopilot Mode - Low Confidence (Chat)');
  const t5 = enforceAutonomy('chat', 'call_api', { riskScore: 0.8, confidenceMargin: 0.2, attentionSensitivity: 0.1 });
  console.log(`Result: ${t5} (Expected: request_confirmation)\n`);

  // Test 6: Kill Switch Override
  console.log('Test 6: Kill Switch Override');
  setKillSwitch(true);
  const t6 = enforceAutonomy('chat', 'call_api', { riskScore: 0.9, confidenceMargin: 0.9, attentionSensitivity: 0.1 });
  console.log(`Result: ${t6} (Expected: request_confirmation)\n`);
  setKillSwitch(false);

  // Test 7: Disallowed Tool
  console.log('Test 7: Disallowed Tool (SysOps)');
  AUTO_CONFIG['sysops'].level = AutonomyLevel.AUTOPILOT;
  const t7 = enforceAutonomy('sysops', 'DELETE_DATABASE', { riskScore: 0.9, confidenceMargin: 0.9, attentionSensitivity: 0.1 });
  console.log(`Result: ${t7} (Expected: request_confirmation)\n`);
}

runTests().catch(console.error);
