import 'package:evagg_driver/app_shell.dart';
import 'package:evagg_driver/core/navigation/tab_switcher.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('starts on the home tab and switches tabs on nav taps', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: AppShell(
        homeScreen: Text('home-tab-content'),
        mapScreen: Text('map-tab-content'),
        vehiclesScreen: Text('vehicles-tab-content'),
        walletScreen: Text('wallet-tab-content'),
        routePlannerScreen: Text('route-tab-content'),
        accountScreen: Text('account-tab-content'),
      ),
    ));

    // IndexedStack keeps every tab mounted (that's the point — it preserves
    // each tab's state), so presence alone can't distinguish the active
    // tab; only its `index` can.
    IndexedStack stack() => tester.widget<IndexedStack>(find.byType(IndexedStack));

    expect(stack().index, 0);

    await tester.tap(find.byKey(const Key('nav-map')));
    await tester.pumpAndSettle();
    expect(stack().index, 1);

    await tester.tap(find.byKey(const Key('nav-vehicles')));
    await tester.pumpAndSettle();
    expect(stack().index, 2);

    await tester.tap(find.byKey(const Key('nav-wallet')));
    await tester.pumpAndSettle();
    expect(stack().index, 3);

    await tester.tap(find.byKey(const Key('nav-route')));
    await tester.pumpAndSettle();
    expect(stack().index, 4);

    await tester.tap(find.byKey(const Key('nav-account')));
    await tester.pumpAndSettle();
    expect(stack().index, 5);

    await tester.tap(find.byKey(const Key('nav-home')));
    await tester.pumpAndSettle();
    expect(stack().index, 0);
  });

  testWidgets('a TabSwitcher can switch tabs programmatically', (tester) async {
    final tabSwitcher = TabSwitcher();
    await tester.pumpWidget(MaterialApp(
      home: AppShell(
        tabSwitcher: tabSwitcher,
        homeScreen: const Text('home-tab-content'),
        mapScreen: const Text('map-tab-content'),
        vehiclesScreen: const Text('vehicles-tab-content'),
        walletScreen: const Text('wallet-tab-content'),
        routePlannerScreen: const Text('route-tab-content'),
        accountScreen: const Text('account-tab-content'),
      ),
    ));

    IndexedStack stack() => tester.widget<IndexedStack>(find.byType(IndexedStack));
    expect(stack().index, 0);

    tabSwitcher.switchTo(1);
    await tester.pumpAndSettle();
    expect(stack().index, 1);
  });
}
