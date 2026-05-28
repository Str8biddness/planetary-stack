import { execSync } from 'child_process';
import path from 'path';
import { registerDefaultOrgans } from '../packages/organs/bootstrap';
import { runTrainingSessions } from './runTrainingSessions';

function runPythonTraining(domain: string, organ: string): void {
  const scriptPath = path.join(__dirname, 'train_triad.py');
  console.log(`Executing: python ${scriptPath} --domain ${domain} --organ ${organ}`);
  execSync(`python "${scriptPath}" --domain ${domain} --organ ${organ}`, { stdio: 'inherit' });
}

function runPythonEvaluation(): void {
  const scriptPath = path.join(__dirname, 'evaluate_organs.py');
  console.log(`Executing: python ${scriptPath}`);
  execSync(`python "${scriptPath}"`, { stdio: 'inherit' });
}

export async function selfImprove(): Promise<void> {
  registerDefaultOrgans();

  await runTrainingSessions();

  const organPairs: Array<[string, string]> = [
    ['chat', 'policy_prior'],
    ['chat', 'risk_outcome'],
    ['chat', 'attention'],
    ['sysops', 'policy_prior'],
    ['sysops', 'risk_outcome'],
    ['sysops', 'attention'],
    ['gm', 'policy_prior'],
    ['gm', 'risk_outcome'],
    ['gm', 'attention'],
  ];

  for (const [domain, organ] of organPairs) {
    runPythonTraining(domain, organ);
  }

  runPythonEvaluation();

  console.log('Default ML organs registered and triad training completed.');
}
