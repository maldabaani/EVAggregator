import 'package:evagg_driver/core/models/reservation.dart';
import 'package:evagg_driver/core/models/reward.dart';
import 'package:evagg_driver/core/models/vehicle.dart';
import 'package:evagg_driver/features/analytics/usage_insights.dart';
import 'package:evagg_driver/features/home/home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _vehicle = Vehicle(
  id: 'v-1',
  make: 'Tesla',
  model: 'Model 3',
  connectorType: 'CCS2',
  batteryCapacityKwh: 75,
  plugAndChargeEnabled: true,
);

Widget _pump({
  List<Vehicle> Function()? vehicles,
  int Function()? balance,
  List<DailyUsagePoint> Function()? usage,
  ReservationsFetcherOverride? reservations,
  RewardsFetcherOverride? rewards,
  VoidCallback? onOpenMap,
}) {
  return MaterialApp(
    home: HomeScreen(
      fetchVehicles: () async => vehicles?.call() ?? const [],
      fetchWalletBalance: () async => balance?.call() ?? 0,
      fetchUsageInsights: (from, to) async => usage?.call() ?? const [],
      fetchReservations: reservations == null ? null : () async => reservations(),
      fetchRewards: rewards == null ? null : () async => rewards(),
      onOpenMap: onOpenMap ?? () {},
    ),
  );
}

typedef ReservationsFetcherOverride = List<Reservation> Function();
typedef RewardsFetcherOverride = RewardsSummary Function();

void main() {
  testWidgets('shows a no-vehicle prompt when the driver has no vehicles', (tester) async {
    await tester.pumpWidget(_pump());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-no-vehicle')), findsOneWidget);
  });

  testWidgets('shows the first vehicle and wallet balance', (tester) async {
    await tester.pumpWidget(_pump(
      vehicles: () => const [_vehicle],
      balance: () => 12345,
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-vehicle-card')), findsOneWidget);
    expect(find.text('Tesla Model 3'), findsOneWidget);
    expect(find.byKey(const Key('home-wallet-balance')), findsOneWidget);
    expect(find.text('123.45 AED'), findsOneWidget);
  });

  testWidgets('shows a vehicle load error without blanking the rest of the screen', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: HomeScreen(
        fetchVehicles: () async => throw Exception('boom'),
        fetchWalletBalance: () async => 500,
        fetchUsageInsights: (from, to) async => const [],
        onOpenMap: () {},
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-vehicles-error')), findsOneWidget);
    expect(find.byKey(const Key('home-wallet-balance')), findsOneWidget);
  });

  testWidgets('summarizes the last 7 days of usage', (tester) async {
    final today = DateTime.now();
    await tester.pumpWidget(_pump(usage: () => [
          DailyUsagePoint(date: today, sessionCount: 2, kwhTotal: 10, costTotalMinorUnits: 1000),
          DailyUsagePoint(date: today, sessionCount: 1, kwhTotal: 5, costTotalMinorUnits: 500),
        ]));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-usage-summary')), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.text('15.0 kWh'), findsOneWidget);
    expect(find.text('15.00 AED'), findsOneWidget);
  });

  testWidgets('shows an upcoming reservation card when one exists', (tester) async {
    final reservation = Reservation(
      id: 'r-1',
      chargerId: 'CP-1',
      connectorId: 1,
      expiresAt: DateTime.now().add(const Duration(hours: 2)),
    );
    await tester.pumpWidget(_pump(reservations: () => [reservation]));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-reservation-card-r-1')), findsOneWidget);
  });

  testWidgets('omits the reservation card when fetchReservations is not provided', (tester) async {
    await tester.pumpWidget(_pump());
    await tester.pumpAndSettle();

    expect(find.textContaining('Reservation at'), findsNothing);
  });

  testWidgets('shows a rewards teaser when rewards are provided', (tester) async {
    await tester.pumpWidget(_pump(
      rewards: () => const RewardsSummary(balance: 250, catalog: []),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-rewards-teaser')), findsOneWidget);
    expect(find.text('250 points available'), findsOneWidget);
  });

  testWidgets('tapping "Find charging near you" calls onOpenMap', (tester) async {
    var tapped = false;
    await tester.pumpWidget(_pump(onOpenMap: () => tapped = true));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('home-open-map-button')));
    await tester.pumpAndSettle();

    expect(tapped, isTrue);
  });
}
