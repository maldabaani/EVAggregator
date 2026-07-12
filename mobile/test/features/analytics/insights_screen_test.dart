import 'package:evagg_driver/features/analytics/insights_screen.dart';
import 'package:evagg_driver/features/analytics/usage_insights.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final fixedNow = DateTime(2026, 1, 14); // a Wednesday

  List<DailyUsagePoint> currentPeriodPoints() => [
        DailyUsagePoint(
          date: DateTime(2026, 1, 10),
          sessionCount: 2,
          kwhTotal: 20,
          costTotalMinorUnits: 2000,
          topSiteName: 'Marina Mall',
        ),
        DailyUsagePoint(
          date: DateTime(2026, 1, 12),
          sessionCount: 5,
          kwhTotal: 40,
          costTotalMinorUnits: 4000,
          topSiteName: 'Marina Mall',
        ),
      ];

  List<DailyUsagePoint> previousPeriodPoints() => [
        DailyUsagePoint(date: DateTime(2026, 1, 3), sessionCount: 3, kwhTotal: 30, costTotalMinorUnits: 5000),
      ];

  testWidgets('shows a loading indicator, then the summarized totals for the current period', (tester) async {
    final requestedRanges = <(DateTime, DateTime)>[];

    await tester.pumpWidget(
      MaterialApp(
        home: InsightsScreen(
          now: () => fixedNow,
          fetcher: (from, to) async {
            requestedRanges.add((from, to));
            final isCurrent = requestedRanges.length == 1;
            return isCurrent ? currentPeriodPoints() : previousPeriodPoints();
          },
        ),
      ),
    );

    expect(find.byKey(const Key('insights-loading')), findsOneWidget);

    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('insights-loading')), findsNothing);
    expect(tester.widget<Text>(find.byKey(const Key('total-sessions-value'))).data, '7');
    expect(tester.widget<Text>(find.byKey(const Key('total-kwh-value'))).data, '60.0 kWh');
    expect(tester.widget<Text>(find.byKey(const Key('total-spend-value'))).data, '60.00 AED');

    // current 6000, previous 5000 -> +20%
    expect(tester.widget<Text>(find.byKey(const Key('spend-change-value'))).data, '+20% vs previous period');

    expect(tester.widget<Text>(find.byKey(const Key('busiest-day-value'))).data, '2026-01-12 (5 sessions)');
    expect(tester.widget<Text>(find.byKey(const Key('favorite-site-value'))).data, 'Marina Mall');

    // Two calls: current period and previous period.
    expect(requestedRanges, hasLength(2));
    final currentRange = requestedRanges[0];
    expect(currentRange.$1, DateTime(2026, 1, 8)); // 7 days ending today (inclusive)
    expect(currentRange.$2, DateTime(2026, 1, 14));
  });

  testWidgets('an empty period shows the no-sessions message and no percent change', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: InsightsScreen(now: () => fixedNow, fetcher: (from, to) async => []),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.text('No charging sessions in this period yet.'), findsOneWidget);
    expect(find.byKey(const Key('spend-change-value')), findsNothing);
    expect(find.byKey(const Key('busiest-day-tile')), findsNothing);
    expect(find.byKey(const Key('favorite-site-tile')), findsNothing);
    expect(tester.widget<Text>(find.byKey(const Key('total-sessions-value'))).data, '0');
  });

  testWidgets('a fetch failure shows an error with a working retry button', (tester) async {
    var attempt = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: InsightsScreen(
          now: () => fixedNow,
          fetcher: (from, to) async {
            attempt++;
            if (attempt <= 2) throw Exception('network error'); // fails on first load's 2 calls
            return currentPeriodPoints();
          },
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('insights-error-message')), findsOneWidget);

    await tester.tap(find.byKey(const Key('insights-retry-button')));
    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('insights-error-message')), findsNothing);
    expect(find.byKey(const Key('total-sessions-value')), findsOneWidget);
  });

  testWidgets('pulling to refresh re-fetches usage data', (tester) async {
    var fetchCount = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: InsightsScreen(
          now: () => fixedNow,
          fetcher: (from, to) async {
            fetchCount++;
            return currentPeriodPoints();
          },
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(fetchCount, 2); // current + previous

    await tester.fling(find.byType(ListView), const Offset(0, 300), 1000);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(fetchCount, 4); // refreshed: current + previous again
  });
}
