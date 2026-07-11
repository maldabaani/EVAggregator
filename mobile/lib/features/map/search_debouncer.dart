import 'dart:async';

/// Task 5.1 — debounced location search (300ms), cancel-in-flight on new
/// keystroke: only the most recent query's result is ever delivered, even
/// if an earlier (superseded) request's geocoding call resolves late.
typedef SearchExecutor = Future<List<String>> Function(String query);

class DebouncedSearchController {
  final SearchExecutor executor;
  final Duration debounce;

  Timer? _timer;
  int _generation = 0;

  DebouncedSearchController({
    required this.executor,
    this.debounce = const Duration(milliseconds: 300),
  });

  /// Schedules a debounced search for [query]. Any pending timer from a
  /// previous call is cancelled outright; if a previous call's executor is
  /// already in flight when this fires, its eventual result is discarded
  /// (the generation counter no longer matches) rather than delivered.
  void search(String query, void Function(List<String> results) onResults) {
    _timer?.cancel();
    final generation = ++_generation;
    _timer = Timer(debounce, () async {
      final results = await executor(query);
      if (generation == _generation) {
        onResults(results);
      }
    });
  }

  void dispose() {
    _timer?.cancel();
  }
}
