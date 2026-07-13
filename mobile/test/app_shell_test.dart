import 'package:evagg_driver/app_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('starts on the map tab and switches tabs on nav taps', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: AppShell(
        mapScreen: Text('map-tab-content'),
        vehiclesScreen: Text('vehicles-tab-content'),
        accountScreen: Text('account-tab-content'),
      ),
    ));

    // IndexedStack keeps every tab mounted (that's the point — it preserves
    // each tab's state), so presence alone can't distinguish the active
    // tab; only its `index` can.
    IndexedStack stack() => tester.widget<IndexedStack>(find.byType(IndexedStack));

    expect(stack().index, 0);

    await tester.tap(find.byKey(const Key('nav-vehicles')));
    await tester.pumpAndSettle();
    expect(stack().index, 1);

    await tester.tap(find.byKey(const Key('nav-account')));
    await tester.pumpAndSettle();
    expect(stack().index, 2);
  });
}
