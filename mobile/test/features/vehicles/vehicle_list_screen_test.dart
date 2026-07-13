import 'package:evagg_driver/core/models/vehicle.dart';
import 'package:evagg_driver/features/vehicles/vehicle_list_screen.dart';
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

void main() {
  testWidgets('shows an empty state when the driver has no vehicles', (tester) async {
    await tester.pumpWidget(_wrap(VehicleListScreen(
      fetcher: () async => [],
      creator: (make, model, connector, battery) async => _vehicle,
      toggler: (id, enabled) async {},
      deleter: (id) async {},
    )));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('vehicles-empty-state')), findsOneWidget);
  });

  testWidgets('renders a tile per vehicle', (tester) async {
    await tester.pumpWidget(_wrap(VehicleListScreen(
      fetcher: () async => [_vehicle],
      creator: (make, model, connector, battery) async => _vehicle,
      toggler: (id, enabled) async {},
      deleter: (id) async {},
    )));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('vehicle-tile-v-1')), findsOneWidget);
    expect(find.text('Tesla Model 3'), findsOneWidget);
  });

  testWidgets('shows a load error banner when fetching vehicles fails', (tester) async {
    await tester.pumpWidget(_wrap(VehicleListScreen(
      fetcher: () async => throw Exception('boom'),
      creator: (make, model, connector, battery) async => _vehicle,
      toggler: (id, enabled) async {},
      deleter: (id) async {},
    )));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('vehicles-load-error')), findsOneWidget);
  });

  testWidgets('tapping the FAB reveals the add-vehicle form, and saving calls the creator', (tester) async {
    String? capturedMake;
    await tester.pumpWidget(_wrap(VehicleListScreen(
      fetcher: () async => [],
      creator: (make, model, connector, battery) async {
        capturedMake = make;
        return _vehicle;
      },
      toggler: (id, enabled) async {},
      deleter: (id) async {},
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('add-vehicle-fab')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('add-vehicle-form')), findsOneWidget);

    await tester.enterText(find.byKey(const Key('vehicle-make-field')), 'Tesla');
    await tester.enterText(find.byKey(const Key('vehicle-model-field')), 'Model 3');
    await tester.enterText(find.byKey(const Key('vehicle-battery-field')), '75');
    await tester.tap(find.byKey(const Key('save-vehicle-button')));
    await tester.pumpAndSettle();

    expect(capturedMake, 'Tesla');
    expect(find.byKey(const Key('add-vehicle-form')), findsNothing);
  });

  testWidgets('an invalid add-vehicle form shows an error and never calls the creator', (tester) async {
    var creatorCalled = false;
    await tester.pumpWidget(_wrap(VehicleListScreen(
      fetcher: () async => [],
      creator: (make, model, connector, battery) async {
        creatorCalled = true;
        return _vehicle;
      },
      toggler: (id, enabled) async {},
      deleter: (id) async {},
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('add-vehicle-fab')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('save-vehicle-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('vehicle-save-error')), findsOneWidget);
    expect(creatorCalled, isFalse);
  });

  testWidgets('toggling the Plug & Charge switch calls the toggler', (tester) async {
    String? toggledId;
    bool? toggledValue;
    await tester.pumpWidget(_wrap(VehicleListScreen(
      fetcher: () async => [_vehicle],
      creator: (make, model, connector, battery) async => _vehicle,
      toggler: (id, enabled) async {
        toggledId = id;
        toggledValue = enabled;
      },
      deleter: (id) async {},
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('plug-and-charge-switch-v-1')));
    await tester.pumpAndSettle();

    expect(toggledId, 'v-1');
    expect(toggledValue, isTrue);
  });

  testWidgets('deleting a vehicle calls the deleter and removes it from the list', (tester) async {
    var vehicles = [_vehicle];
    await tester.pumpWidget(_wrap(VehicleListScreen(
      fetcher: () async => vehicles,
      creator: (make, model, connector, battery) async => _vehicle,
      toggler: (id, enabled) async {},
      deleter: (id) async {
        vehicles = [];
      },
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('delete-vehicle-button-v-1')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('vehicle-tile-v-1')), findsNothing);
  });
}
