/// Task 5.3 — live session tracking screen. Charging sessions are polled
/// rather than pushed (no WS/SSE session feed exists yet, unlike the
/// charger presence feed from Task 2.4/5.1), so this controller re-fetches
/// on a fixed interval and, like `LiveStatusFeedController` (Task 5.1),
/// derives staleness on demand from the clock rather than assuming every
/// poll succeeds.
library;

import 'dart:async';

import 'package:clock/clock.dart' as clock_pkg;

enum SessionStatus { charging, suspended, stopping, finished }

class SessionSnapshot {
  final SessionStatus status;
  final double energyKwh;
  final double powerKw;
  final int costMinorUnits;
  final String currency;
  final DateTime startedAt;
  final DateTime updatedAt;

  const SessionSnapshot({
    required this.status,
    required this.energyKwh,
    required this.powerKw,
    required this.costMinorUnits,
    required this.currency,
    required this.startedAt,
    required this.updatedAt,
  });
}

typedef SessionFetcher = Future<SessionSnapshot> Function();
typedef SessionStopper = Future<void> Function();

/// Formats minor units (e.g. fils, cents) as a 2-decimal major-unit string,
/// e.g. 1234 -> "12.34". Assumes a 2-decimal-digit currency, true for every
/// currency this platform currently supports.
String formatCost(int minorUnits, String currency) {
  final major = minorUnits / 100;
  return '${major.toStringAsFixed(2)} $currency';
}

String formatElapsed(Duration elapsed) {
  final hours = elapsed.inHours;
  final minutes = elapsed.inMinutes.remainder(60);
  final seconds = elapsed.inSeconds.remainder(60);
  final mm = minutes.toString().padLeft(2, '0');
  final ss = seconds.toString().padLeft(2, '0');
  if (hours > 0) {
    return '$hours:$mm:$ss';
  }
  return '$mm:$ss';
}

const Duration defaultPollInterval = Duration(seconds: 5);
const Duration defaultSessionStaleAfter = Duration(seconds: 20);

/// A stop request already in flight must not be fired twice — e.g. from a
/// driver double-tapping "Stop charging" — so `stop()` collapses concurrent
/// callers onto the single underlying request rather than issuing another
/// remote-stop command per tap.
class SessionTrackingController {
  final SessionFetcher fetcher;
  final SessionStopper stopper;
  final Duration pollInterval;
  final Duration staleAfter;
  final DateTime Function() _clock;
  final void Function(SessionSnapshot snapshot)? onUpdate;
  final void Function(Object error)? onFetchError;

  Timer? _timer;
  SessionSnapshot? _latest;
  DateTime? _lastFetchSucceededAt;
  Future<void>? _inFlightStop;

  SessionTrackingController({
    required this.fetcher,
    required this.stopper,
    this.pollInterval = defaultPollInterval,
    this.staleAfter = defaultSessionStaleAfter,
    DateTime Function()? clock,
    this.onUpdate,
    this.onFetchError,
  }) : _clock = clock ?? clock_pkg.clock.now;

  SessionSnapshot? get latest => _latest;

  bool get isStale {
    if (_lastFetchSucceededAt == null) return true;
    return _clock().difference(_lastFetchSucceededAt!) > staleAfter;
  }

  Future<void> start() async {
    await _fetchOnce();
    _timer = Timer.periodic(pollInterval, (_) => _fetchOnce());
  }

  Future<void> _fetchOnce() async {
    try {
      final snapshot = await fetcher();
      _latest = snapshot;
      _lastFetchSucceededAt = _clock();
      onUpdate?.call(snapshot);
    } catch (error) {
      onFetchError?.call(error);
    }
  }

  Future<void> stop() {
    return _inFlightStop ??= stopper().whenComplete(() => _inFlightStop = null);
  }

  void dispose() {
    _timer?.cancel();
  }
}
