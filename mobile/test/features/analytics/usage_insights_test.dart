import 'package:evagg_driver/features/analytics/usage_insights.dart';
import 'package:flutter_test/flutter_test.dart';

DailyUsagePoint _point({
  required DateTime date,
  int sessionCount = 1,
  double kwhTotal = 10.0,
  int costTotalMinorUnits = 1000,
  String? topSiteName,
}) {
  return DailyUsagePoint(
    date: date,
    sessionCount: sessionCount,
    kwhTotal: kwhTotal,
    costTotalMinorUnits: costTotalMinorUnits,
    topSiteName: topSiteName,
  );
}

void main() {
  group('summarize', () {
    test('sums sessions, kWh, and cost across all points', () {
      final points = [
        _point(date: DateTime(2026, 1, 1), sessionCount: 2, kwhTotal: 10, costTotalMinorUnits: 500),
        _point(date: DateTime(2026, 1, 2), sessionCount: 1, kwhTotal: 5, costTotalMinorUnits: 250),
      ];

      final summary = summarize(points);

      expect(summary.totalSessions, 3);
      expect(summary.totalKwh, 15);
      expect(summary.totalCostMinorUnits, 750);
    });

    test('an empty period summarizes to all zeros', () {
      final summary = summarize([]);

      expect(summary.totalSessions, 0);
      expect(summary.totalKwh, 0);
      expect(summary.totalCostMinorUnits, 0);
    });
  });

  group('averageCostPerKwhMinorUnits', () {
    test('divides total cost by total kWh', () {
      const summary = UsageSummary(totalSessions: 2, totalKwh: 20, totalCostMinorUnits: 1000);

      expect(summary.averageCostPerKwhMinorUnits, 50);
    });

    test('is null when no energy was delivered, to avoid a division by zero', () {
      expect(UsageSummary.zero.averageCostPerKwhMinorUnits, isNull);
    });
  });

  group('percentSpendChange', () {
    test('reports a positive fraction for an increase', () {
      const current = UsageSummary(totalSessions: 1, totalKwh: 1, totalCostMinorUnits: 125);
      const previous = UsageSummary(totalSessions: 1, totalKwh: 1, totalCostMinorUnits: 100);

      expect(percentSpendChange(current, previous), 0.25);
    });

    test('reports a negative fraction for a decrease', () {
      const current = UsageSummary(totalSessions: 1, totalKwh: 1, totalCostMinorUnits: 75);
      const previous = UsageSummary(totalSessions: 1, totalKwh: 1, totalCostMinorUnits: 100);

      expect(percentSpendChange(current, previous), -0.25);
    });

    test('is null when the previous period had zero spend', () {
      const current = UsageSummary(totalSessions: 1, totalKwh: 1, totalCostMinorUnits: 100);

      expect(percentSpendChange(current, UsageSummary.zero), isNull);
    });
  });

  group('busiestDay', () {
    test('picks the day with the most sessions', () {
      final quiet = _point(date: DateTime(2026, 1, 1), sessionCount: 1);
      final busy = _point(date: DateTime(2026, 1, 2), sessionCount: 4);

      expect(busiestDay([quiet, busy]), same(busy));
    });

    test('breaks ties by the earlier date', () {
      final earlier = _point(date: DateTime(2026, 1, 1), sessionCount: 3);
      final later = _point(date: DateTime(2026, 1, 2), sessionCount: 3);

      expect(busiestDay([earlier, later]), same(earlier));
    });

    test('returns null for an empty period', () {
      expect(busiestDay([]), isNull);
    });
  });

  group('favoriteSite', () {
    test('picks the site that appears as top site on the most days', () {
      final points = [
        _point(date: DateTime(2026, 1, 1), topSiteName: 'Marina Mall'),
        _point(date: DateTime(2026, 1, 2), topSiteName: 'Marina Mall'),
        _point(date: DateTime(2026, 1, 3), topSiteName: 'Downtown Hub'),
      ];

      expect(favoriteSite(points), 'Marina Mall');
    });

    test('ignores days with no recorded site', () {
      final points = [
        _point(date: DateTime(2026, 1, 1), topSiteName: null),
        _point(date: DateTime(2026, 1, 2), topSiteName: 'Downtown Hub'),
      ];

      expect(favoriteSite(points), 'Downtown Hub');
    });

    test('returns null when no day carries a site name', () {
      final points = [_point(date: DateTime(2026, 1, 1), topSiteName: null)];

      expect(favoriteSite(points), isNull);
    });
  });
}
