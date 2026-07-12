/// Task 5.1 — pin color reflects Redis presence state (Epic 2 Task 2.4),
/// delivered via a WS/SSE bridge. If that feed drops, pins must show a
/// "stale" indicator (last-known state, greyed out) rather than silently
/// freezing with no signal to the user.
library;

enum ChargerPresenceStatus { online, offline, unknown }

class PresenceSnapshot {
  final ChargerPresenceStatus status;
  final DateTime lastUpdated;

  const PresenceSnapshot({required this.status, required this.lastUpdated});
}

class PinDisplayState {
  final ChargerPresenceStatus status;
  final bool stale;

  const PinDisplayState({required this.status, required this.stale});

  @override
  bool operator ==(Object other) =>
      other is PinDisplayState && other.status == status && other.stale == stale;

  @override
  int get hashCode => Object.hash(status, stale);

  @override
  String toString() => 'PinDisplayState(status: $status, stale: $stale)';
}

const Duration defaultStaleAfter = Duration(seconds: 30);

PinDisplayState derivePinDisplayState(
  PresenceSnapshot? snapshot,
  DateTime now, {
  Duration staleAfter = defaultStaleAfter,
}) {
  if (snapshot == null) {
    return const PinDisplayState(status: ChargerPresenceStatus.unknown, stale: true);
  }
  final isStale = now.difference(snapshot.lastUpdated) > staleAfter;
  return PinDisplayState(status: snapshot.status, stale: isStale);
}

/// Tracks the latest presence snapshot per charger and derives each pin's
/// display state on demand — a pull model rather than a push model, so the
/// UI can recompute staleness even when no new update has arrived (which is
/// exactly the disconnected case this needs to detect).
class LiveStatusFeedController {
  final Duration staleAfter;
  final DateTime Function() _clock;
  final Map<String, PresenceSnapshot> _snapshots = {};

  LiveStatusFeedController({
    this.staleAfter = defaultStaleAfter,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  void applyUpdate(String chargerId, ChargerPresenceStatus status) {
    _snapshots[chargerId] = PresenceSnapshot(status: status, lastUpdated: _clock());
  }

  PinDisplayState displayStateFor(String chargerId) {
    return derivePinDisplayState(_snapshots[chargerId], _clock(), staleAfter: staleAfter);
  }
}
