enum QuotaSource { provider, localEstimate, unavailable }

class ProviderUsage {
  const ProviderUsage({
    required this.providerId,
    this.modelId,
    this.quotaSource = QuotaSource.unavailable,
    this.usedRequests,
    this.requestLimit,
    this.inputTokens = 0,
    this.outputTokens = 0,
    this.usedCost,
    this.budgetLimit,
    this.currency = 'USD',
    this.resetAt,
    required this.lastUpdatedAt,
  });

  final String providerId;
  final String? modelId;
  final QuotaSource quotaSource;
  final int? usedRequests;
  final int? requestLimit;
  final int inputTokens;
  final int outputTokens;
  final double? usedCost;
  final double? budgetLimit;
  final String currency;
  final DateTime? resetAt;
  final DateTime lastUpdatedAt;

  int? get remainingRequests =>
      usedRequests != null && requestLimit != null
          ? (requestLimit! - usedRequests!).clamp(0, requestLimit!)
          : null;

  double? get remainingBudget =>
      usedCost != null && budgetLimit != null
          ? (budgetLimit! - usedCost!).clamp(0, budgetLimit!)
          : null;

  bool get isOfficial => quotaSource == QuotaSource.provider;
  bool get isEstimate => quotaSource == QuotaSource.localEstimate;
}

class CostGuard {
  const CostGuard({
    this.paidApiEnabled = false,
    this.hardCostGuard = true,
    this.globalBudget,
  });

  final bool paidApiEnabled;
  final bool hardCostGuard;
  final double? globalBudget;

  bool allowPaidCall({required ProviderUsage usage, double? totalUsedCost}) {
    if (!paidApiEnabled) return false;
    if (!hardCostGuard) return true;
    if (usage.budgetLimit != null && usage.usedCost != null && usage.usedCost! >= usage.budgetLimit!) return false;
    if (globalBudget != null && totalUsedCost != null && totalUsedCost >= globalBudget!) return false;
    return true;
  }
}
