import 'package:evagg_driver/core/models/route_plan.dart';
import 'package:evagg_driver/core/models/vehicle.dart';
import 'package:evagg_driver/features/route_planner/route_planner_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _vehicle = Vehicle(
  id: 'v-1',
  make: 'Tesla',
  model: 'Model 3',
  connectorType: 'CCS2',
  batteryCapacityKwh: 75.0,
  plugAndChargeEnabled: false,
);

Widget _wrap(Widget child) => MaterialApp(home: child);

Future<void> _fillCoordinates(WidgetTester tester) async {
  await tester.enterText(find.byKey(const Key('route-planner-origin-lat-field')), '25.2');
  await tester.enterText(find.byKey(const Key('route-planner-origin-lng-field')), '55.3');
  await tester.enterText(find.byKey(const Key('route-planner-destination-lat-field')), '24.4');
  await tester.enterText(find.byKey(const Key('route-planner-destination-lng-field')), '54.3');
}

void main() {
  testWidgets('shows a message to add a vehicle when the driver has none', (tester) async {
    await tester.pumpWidget(_wrap(RoutePlannerScreen(
      fetchVehicles: () async => [],
      planRoute: (_, _, _, _, _) async => throw UnimplementedError(),
    )));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('route-planner-no-vehicles')), findsOneWidget);
  });

  testWidgets('planning a route with no charging stop shows the no-stop message', (tester) async {
    await tester.pumpWidget(_wrap(RoutePlannerScreen(
      fetchVehicles: () async => [_vehicle],
      planRoute: (vehicleId, originLat, originLng, destLat, destLng) async => const RoutePlanResult(
        distanceKm: 10.0,
        durationMinutes: 8.0,
        chargingStopNeeded: false,
        suggestedCharger: null,
      ),
    )));
    await tester.pumpAndSettle();

    await _fillCoordinates(tester);
    await tester.tap(find.byKey(const Key('route-planner-submit-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('route-planner-no-stop-needed')), findsOneWidget);
  });

  testWidgets('planning a long route suggests a charging stop', (tester) async {
    String? capturedVehicleId;
    await tester.pumpWidget(_wrap(RoutePlannerScreen(
      fetchVehicles: () async => [_vehicle],
      planRoute: (vehicleId, originLat, originLng, destLat, destLng) async {
        capturedVehicleId = vehicleId;
        return const RoutePlanResult(
          distanceKm: 300.0,
          durationMinutes: 240.0,
          chargingStopNeeded: true,
          suggestedCharger: SuggestedCharger(id: 'CP-1', name: 'Midway Station', lat: 24.9, lng: 54.8),
        );
      },
    )));
    await tester.pumpAndSettle();

    await _fillCoordinates(tester);
    await tester.tap(find.byKey(const Key('route-planner-submit-button')));
    await tester.pumpAndSettle();

    expect(capturedVehicleId, 'v-1');
    expect(find.byKey(const Key('route-planner-charging-stop')), findsOneWidget);
    expect(find.textContaining('Midway Station'), findsOneWidget);
  });

  testWidgets('submitting with missing coordinates shows a validation error', (tester) async {
    await tester.pumpWidget(_wrap(RoutePlannerScreen(
      fetchVehicles: () async => [_vehicle],
      planRoute: (_, _, _, _, _) async => throw UnimplementedError(),
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('route-planner-submit-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('route-planner-error')), findsOneWidget);
  });

  testWidgets('a failed plan shows an inline error', (tester) async {
    await tester.pumpWidget(_wrap(RoutePlannerScreen(
      fetchVehicles: () async => [_vehicle],
      planRoute: (_, _, _, _, _) async => throw Exception('boom'),
    )));
    await tester.pumpAndSettle();

    await _fillCoordinates(tester);
    await tester.tap(find.byKey(const Key('route-planner-submit-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('route-planner-error')), findsOneWidget);
  });

  testWidgets('shows a load error when fetching vehicles fails', (tester) async {
    await tester.pumpWidget(_wrap(RoutePlannerScreen(
      fetchVehicles: () async => throw Exception('boom'),
      planRoute: (_, _, _, _, _) async => throw UnimplementedError(),
    )));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('route-planner-load-error')), findsOneWidget);
  });
}
