// cli.ts
// CLI runner for training and session commands

import { execSync } from 'child_process';
import path from 'path';

function runPythonTraining(domain: string, organ: string) {
  const scriptPath = path.resolve(__dirname, '../../tools/train_triad.py');
  console.log(`Executing: python ${scriptPath} --domain ${domain} --organ ${organ}`);
  execSync(`python "${scriptPath}" --domain ${domain} --organ ${organ}`, { stdio: 'inherit' });
}

import { runTrainingSessions } from '../../tools/runTrainingSessions';
import { setKillSwitch, GLOBAL_KILL_SWITCH, AUTO_CONFIG, AutonomyLevel } from './autonomyConfig';

const args = process.argv.slice(2);
const command = args[0];

switch (command) {
  case 'trainChatPolicyPrior':
    runPythonTraining('chat', 'policy_prior');
    break;
  case 'trainChatRiskOutcome':
    runPythonTraining('chat', 'risk_outcome');
    break;
  case 'trainChatAttention':
    runPythonTraining('chat', 'attention');
    break;
  case 'trainSysOpsPolicyPrior':
    runPythonTraining('sysops', 'policy_prior');
    break;
  case 'trainSysOpsRiskOutcome':
    runPythonTraining('sysops', 'risk_outcome');
    break;
  case 'trainSysOpsAttention':
    runPythonTraining('sysops', 'attention');
    break;
  case 'trainGmPolicyPrior':
    runPythonTraining('gm', 'policy_prior');
    break;
  case 'trainGmRiskOutcome':
    runPythonTraining('gm', 'risk_outcome');
    break;
  case 'trainGmAttention':
    runPythonTraining('gm', 'attention');
    break;
  case 'toggleKillSwitch':
    setKillSwitch(!GLOBAL_KILL_SWITCH);
    console.log(`Global Kill Switch is now: ${!GLOBAL_KILL_SWITCH ? 'ACTIVE' : 'INACTIVE'}`);
    break;
  case 'setAutonomyLevel':
    const domain = args[1];
    const levelStr = args[2];
    if (domain && levelStr) {
      const level = parseInt(levelStr);
      if (AUTO_CONFIG[domain] && AutonomyLevel[level]) {
        AUTO_CONFIG[domain].level = level;
        console.log(`Autonomy Level for ${domain} set to ${AutonomyLevel[level]}`);
      } else {
        console.log('Invalid domain or level');
      }
    } else {
      console.log('Usage: ts-node cli.ts setAutonomyLevel <domain> <level_num>');
    }
    break;
  case 'selfImprove':
    import('../../tools/selfImprove').then(async ({ selfImprove }) => {
      await selfImprove();
      console.log('Self-improvement loop exited');
    });
    break;
  case 'runTrainingSessions':
    runTrainingSessions().then(() => console.log('Training sessions complete'));
    break;
  default:
    console.log('Usage: ts-node cli.ts <command>');
    console.log('Commands: \n' +
      '  trainChatPolicyPrior, trainChatRiskOutcome, trainChatAttention\n' +
      '  trainSysOpsPolicyPrior, trainSysOpsRiskOutcome, trainSysOpsAttention\n' +
      '  trainGmPolicyPrior, trainGmRiskOutcome, trainGmAttention\n' +
      '  runTrainingSessions, selfImprove\n' +
      '  toggleKillSwitch, setAutonomyLevel <domain> <level>');
}
