import 'package:evagg_driver/features/map/map_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('typing a search query eventually shows debounced results', (tester) async {
    final executedQueries = <String>[];

    await tester.pumpWidget(
      MaterialApp(
        home: MapScreen(
          searchExecutor: (query) async {
            executedQueries.add(query);
            return ['Result for $query'];
          },
        ),
      ),
    );

    await tester.enterText(find.byKey(const Key('map-search-field')), 'Dubai Marina');
    // Before the debounce window elapses, nothing has executed yet.
    await tester.pump(const Duration(milliseconds: 100));
    expect(executedQueries, isEmpty);

    await tester.pump(const Duration(milliseconds: 250)); // crosses the 300ms debounce
    await tester.pump();

    expect(executedQueries, ['Dubai Marina']);
    expect(find.text('Result for Dubai Marina'), findsOneWidget);
  });

  testWidgets('toggling available-only updates the switch state', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MapScreen(searchExecutor: (query) async => []),
      ),
    );

    final switchFinder = find.byKey(const Key('available-only-switch'));
    expect(tester.widget<SwitchListTile>(switchFinder).value, isFalse);

    await tester.tap(switchFinder);
    await tester.pump();

    expect(tester.widget<SwitchListTile>(switchFinder).value, isTrue);
  });

  testWidgets('shows the map placeholder when there is no active search', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MapScreen(searchExecutor: (query) async => []),
      ),
    );

    expect(find.text('Map view (provider TBD)'), findsOneWidget);
  });
}
