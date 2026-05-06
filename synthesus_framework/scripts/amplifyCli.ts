// scripts/amplifyCli.ts
// CLI entrypoint for Python wrapper to call AmplificationPlane
// Reads JSON from stdin, writes JSON to stdout

import { amplifyIntake, amplifyPlanning, amplifyOutput, AmplificationContext } from '../amplification/index';

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    console.error('Usage: npx ts-node scripts/amplifyCli.ts <intake|planning|output> [jsonInput]');
    process.exit(1);
  }
  const phase = args[0];
  let input: any = {};
  if (args[1]) {
    try {
      input = JSON.parse(args[1]);
    } catch (e) {
      // If JSON parse fails, treat remaining args as string input
      input = { rawInput: args.slice(1).join(' ') };
    }
  }

  const ctx: AmplificationContext = {
    computeBudget: input.computeBudget ?? 50,
    sessionId: input.sessionId ?? 'cli-session',
    domain: input.domain ?? 'chat',
    allowedOrgans: input.allowedOrgans,
  };

  let result: any;
  try {
    if (phase === 'intake') {
      result = await amplifyIntake(ctx, input);
    } else if (phase === 'planning') {
      result = await amplifyPlanning(ctx, input);
    } else if (phase === 'output') {
      result = await amplifyOutput(ctx, input);
    } else {
      console.error('Unknown phase:', phase);
      process.exit(1);
    }
    console.log(JSON.stringify(result));
  } catch (err: any) {
    console.error('Error during amplification:', err?.message || String(err));
    process.exit(1);
  }
}

main();
