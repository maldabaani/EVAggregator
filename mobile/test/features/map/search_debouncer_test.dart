import 'package:evagg_driver/features/map/search_debouncer.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('test_search_debounce_cancels_in_flight_request_on_new_keystroke', () {
    fakeAsync((async) {
      final executedQueries = <String>[];
      final delivered = <String, List<String>>{};

      final controller = DebouncedSearchController(
        executor: (query) async {
          executedQueries.add(query);
          // Simulate network latency on the geocoding call.
          await Future<void>.delayed(const Duration(milliseconds: 50));
          return ['result-for-$query'];
        },
      );

      controller.search('dub', (results) => delivered['dub'] = results);
      async.elapse(const Duration(milliseconds: 100)); // less than the 300ms debounce
      controller.search('dubai', (results) => delivered['dubai'] = results);

      async.elapse(const Duration(seconds: 1)); // let everything settle

      // Only the final keystroke's query should ever have reached the executor.
      expect(executedQueries, ['dubai']);
      expect(delivered.containsKey('dub'), isFalse);
      expect(delivered['dubai'], ['result-for-dubai']);
    });
  });

  test('debounce still fires once for a single keystroke after the wait', () {
    fakeAsync((async) {
      final delivered = <List<String>>[];
      final controller = DebouncedSearchController(
        executor: (query) async => ['result-for-$query'],
      );

      controller.search('dubai', delivered.add);
      async.elapse(const Duration(milliseconds: 300));

      expect(delivered, [
        ['result-for-dubai'],
      ]);
    });
  });

  test('a superseded request whose executor resolves late is discarded, not delivered', () {
    fakeAsync((async) {
      final delivered = <String>[];
      final controller = DebouncedSearchController(
        executor: (query) async {
          if (query == 'slow-query') {
            await Future<void>.delayed(const Duration(seconds: 5)); // resolves well after the next keystroke
          }
          return [query];
        },
      );

      controller.search('slow-query', (r) => delivered.addAll(r));
      async.elapse(const Duration(milliseconds: 300)); // debounce fires, executor call begins

      controller.search('fast-query', (r) => delivered.addAll(r));
      async.elapse(const Duration(seconds: 10)); // both would resolve by now if not cancelled

      expect(delivered, ['fast-query']); // slow-query's late result never delivered
    });
  });

  test('dispose cancels a pending debounce timer', () {
    fakeAsync((async) {
      var called = false;
      final controller = DebouncedSearchController(
        executor: (query) async => [query],
      );

      controller.search('dubai', (_) => called = true);
      controller.dispose();
      async.elapse(const Duration(seconds: 1));

      expect(called, isFalse);
    });
  });
}
