import 'package:evagg_driver/core/models/charger_filter.dart';
import 'package:evagg_driver/features/map/live_status_feed.dart';
import 'package:evagg_driver/features/map/map_screen.dart';
import 'package:evagg_driver/features/map/pin_clustering.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart' hide LatLngBounds;
import 'package:flutter_test/flutter_test.dart';

// A 1x1 black PNG, used so TileLayer never makes a real network request
// during tests.
final _fakeTileBytes = Uri.parse(
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNiAAAABgADNjd8qAAAAABJRU5ErkJggg==',
).data!.contentAsBytes();

class _FakeTileProvider extends TileProvider {
  @override
  ImageProvider<Object> getImage(TileCoordinates coordinates, TileLayer options) => MemoryImage(_fakeTileBytes);
}

List<MapPin> _threePins() => const [
      MapPin(id: 'CP-001', lat: 25.20, lng: 55.27),
      MapPin(id: 'CP-002', lat: 25.21, lng: 55.28),
      MapPin(id: 'CP-003', lat: 25.22, lng: 55.29),
    ];

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
          pinsFetcher: (bbox, filter) async => [],
          tileProvider: _FakeTileProvider(),
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

  testWidgets('toggling available-only updates the switch state and re-fetches pins', (tester) async {
    final requestedFilters = <ChargerFilter>[];

    await tester.pumpWidget(
      MaterialApp(
        home: MapScreen(
          searchExecutor: (query) async => [],
          pinsFetcher: (bbox, filter) async {
            requestedFilters.add(filter);
            return [];
          },
          tileProvider: _FakeTileProvider(),
        ),
      ),
    );
    await tester.pump();

    final switchFinder = find.byKey(const Key('available-only-switch'));
    expect(tester.widget<SwitchListTile>(switchFinder).value, isFalse);

    await tester.tap(switchFinder);
    await tester.pump();

    expect(tester.widget<SwitchListTile>(switchFinder).value, isTrue);
    expect(requestedFilters.last.availableOnly, isTrue);
  });

  testWidgets('shows a real map with a marker per fetched charger when there is no active search', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MapScreen(
          searchExecutor: (query) async => [],
          pinsFetcher: (bbox, filter) async => _threePins(),
          tileProvider: _FakeTileProvider(),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(FlutterMap), findsOneWidget);
    expect(find.byKey(const Key('map-pin-CP-001')), findsOneWidget);
    expect(find.byKey(const Key('map-pin-CP-002')), findsOneWidget);
    expect(find.byKey(const Key('map-pin-CP-003')), findsOneWidget);
  });

  testWidgets("a pin's color reflects the injected live status feed", (tester) async {
    final statusFeed = LiveStatusFeedController(clock: () => DateTime(2026, 1, 1));
    statusFeed.applyUpdate('CP-001', ChargerPresenceStatus.online);
    statusFeed.applyUpdate('CP-002', ChargerPresenceStatus.offline);

    await tester.pumpWidget(
      MaterialApp(
        home: MapScreen(
          searchExecutor: (query) async => [],
          pinsFetcher: (bbox, filter) async => _threePins(),
          tileProvider: _FakeTileProvider(),
          statusFeed: statusFeed,
        ),
      ),
    );
    await tester.pump();

    Color colorOfPin(String chargerId) {
      final container = tester.widget<Container>(
        find.descendant(of: find.byKey(Key('map-pin-$chargerId')), matching: find.byType(Container)),
      );
      return (container.decoration as BoxDecoration).color!;
    }

    expect(colorOfPin('CP-001'), Colors.green);
    expect(colorOfPin('CP-002'), Colors.red);
    expect(colorOfPin('CP-003'), Colors.grey); // no status reported -> unknown
  });

  testWidgets('tapping a single charger pin opens its detail sheet', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MapScreen(
          searchExecutor: (query) async => [],
          pinsFetcher: (bbox, filter) async => _threePins(),
          tileProvider: _FakeTileProvider(),
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.byKey(const Key('map-pin-CP-002')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('charger-detail-sheet')), findsOneWidget);
    expect(find.text('CP-002'), findsOneWidget);
  });
}
