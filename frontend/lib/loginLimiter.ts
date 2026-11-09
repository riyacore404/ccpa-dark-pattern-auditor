/**
 * Slows password guessing: after too many failed sign-ins in a window, further
 * attempts are refused until the oldest failures age out. The counter is
 * shared by everyone (this is a single-owner tool), and lives in memory, so it
 * resets when the server restarts.
 */
export class LoginLimiter {
  private failures: number[] = [];

  constructor(
    private readonly maxFailures: number = 10,
    private readonly windowMs: number = 15 * 60 * 1000,
    private readonly now: () => number = Date.now,
  ) {}

  private prune(): void {
    const cutoff = this.now() - this.windowMs;
    this.failures = this.failures.filter((t) => t > cutoff);
  }

  isBlocked(): boolean {
    this.prune();
    return this.failures.length >= this.maxFailures;
  }

  recordFailure(): void {
    this.prune();
    this.failures.push(this.now());
  }

  reset(): void {
    this.failures = [];
  }
}

export const loginLimiter = new LoginLimiter();
