/// Task 5.4 — driver analytics & insights dashboard. One point per day
/// with a session, grouped from the driver's own completed-session
/// history (`GET /driver/usage-insights`) rather than reprocessing raw
/// sessions on-device — the backend does the grouping, this just
/// summarizes the result into the numbers the dashboard shows.
library;

class DailyUsagePoint {
  final DateTime date;
  final int sessionCount;
  final double kwhTotal;
  final int costTotalMinorUnits;
  final String? topSiteName;

  const DailyUsagePoint({
    required this.date,
    required this.sessionCount,
    required this.kwhTotal,
    required this.costTotalMinorUnits,
    this.topSiteName,
  });

  factory DailyUsagePoint.fromJson(Map<String, dynamic> json) => DailyUsagePoint(
        date: DateTime.parse(json['usage_date'] as String),
        sessionCount: json['session_count'] as int,
        kwhTotal: (json['kwh_total'] as num).toDouble(),
        costTotalMinorUnits: json['cost_total_minor_units'] as int,
        topSiteName: json['top_site_name'] as String?,
      );
}

class UsageSummary {
  final int totalSessions;
  final double totalKwh;
  final int totalCostMinorUnits;

  const UsageSummary({
    required this.totalSessions,
    required this.totalKwh,
    required this.totalCostMinorUnits,
  });

  static const zero = UsageSummary(totalSessions: 0, totalKwh: 0, totalCostMinorUnits: 0);

  /// Cost per kWh in minor currency units, or null when no energy was
  /// delivered (a driver with zero sessions has no meaningful average).
  double? get averageCostPerKwhMinorUnits => totalKwh > 0 ? totalCostMinorUnits / totalKwh : null;
}

UsageSummary summarize(List<DailyUsagePoint> points) {
  var sessions = 0;
  var kwh = 0.0;
  var cost = 0;
  for (final point in points) {
    sessions += point.sessionCount;
    kwh += point.kwhTotal;
    cost += point.costTotalMinorUnits;
  }
  return UsageSummary(totalSessions: sessions, totalKwh: kwh, totalCostMinorUnits: cost);
}

/// Percentage change of `current` vs `previous`, e.g. 0.25 for a 25% increase.
/// Null when `previous` had zero spend — "infinite % increase from zero" is
/// not a meaningful number to show a driver.
double? percentSpendChange(UsageSummary current, UsageSummary previous) {
  if (previous.totalCostMinorUnits <= 0) return null;
  return (current.totalCostMinorUnits - previous.totalCostMinorUnits) / previous.totalCostMinorUnits;
}

/// The single day with the most sessions; ties broken by the earlier date.
/// Returns null for an empty period (nothing to highlight).
DailyUsagePoint? busiestDay(List<DailyUsagePoint> points) {
  DailyUsagePoint? best;
  for (final point in points) {
    if (best == null || point.sessionCount > best.sessionCount) {
      best = point;
    }
  }
  return best;
}

/// The most frequently reported top charging site across the period, by day
/// count (not by session count) — a simple, explainable definition of
/// "favorite site." Returns null if no day carried a site name.
String? favoriteSite(List<DailyUsagePoint> points) {
  final counts = <String, int>{};
  for (final point in points) {
    final site = point.topSiteName;
    if (site == null) continue;
    counts[site] = (counts[site] ?? 0) + 1;
  }
  if (counts.isEmpty) return null;
  return counts.entries.reduce((a, b) => b.value > a.value ? b : a).key;
}
