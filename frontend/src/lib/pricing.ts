// Illustrative token pricing for the Runs screen's cost-per-email display.
// Source: https://platform.claude.com/docs/en/about-claude/pricing (Claude
// Sonnet 5, checked September 2026). Anthropic's rates change — this is a
// rough estimate for the demo, not a billing guarantee. Update these two
// numbers (or wire up real per-model rates) if you swap models.
export const CLAUDE_SONNET_5_RATE_PER_MTOK = { input: 2, output: 10 } as const;

export function estimateCostUsd(inputTokens: number, outputTokens: number): number {
  const { input, output } = CLAUDE_SONNET_5_RATE_PER_MTOK;
  return (inputTokens / 1_000_000) * input + (outputTokens / 1_000_000) * output;
}

export function formatCostUsd(usd: number): string {
  if (usd === 0) return "$0.000";
  if (usd < 0.001) return "<$0.001";
  return `$${usd.toFixed(3)}`;
}
