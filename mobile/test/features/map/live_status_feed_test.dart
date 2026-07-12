import 'package:evagg_driver/features/map/live_status_feed.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('test_pin_color_updates_on_live_status_change', () {
    var now = DateTime(2026, 1, 1, 12, 0, 0);
    final controller = LiveStatusFeedController(clock: () => now);

    controller.applyUpdate('CP-1', ChargerPresenceStatus.online);
    expect(controller.displayStateFor('CP-1').status, ChargerPresenceStatus.online);

    now = now.add(const Duration(seconds: 1));
    controller.applyUpdate('CP-1', ChargerPresenceStatus.offline);

    expect(controller.displayStateFor('CP-1').status, ChargerPresenceStatus.offline);
    expect(controller.displayStateFor('CP-1').stale, isFalse);
  });

  test('test_stale_indicator_shown_on_feed_disconnect', () {
    var now = DateTime(2026, 1, 1, 12, 0, 0);
    final controller = LiveStatusFeedController(
      clock: () => now,
      staleAfter: const Duration(seconds: 30),
    );
    controller.applyUpdate('CP-1', ChargerPresenceStatus.online);

    // Feed drops -- no further updates arrive, but time keeps advancing.
    now = now.add(const Duration(seconds: 45));

    final state = controller.displayStateFor('CP-1');
    expect(state.stale, isTrue);
    expect(state.status, ChargerPresenceStatus.online); // last-known state, not blanked
  });

  test('a charger with no presence data at all is unknown and stale', () {
    final controller = LiveStatusFeedController(clock: () => DateTime(2026, 1, 1));

    final state = controller.displayStateFor('never-seen');

    expect(state.status, ChargerPresenceStatus.unknown);
    expect(state.stale, isTrue);
  });

  test('a fresh update within the stale window is not flagged stale', () {
    var now = DateTime(2026, 1, 1, 12, 0, 0);
    final controller = LiveStatusFeedController(
      clock: () => now,
      staleAfter: const Duration(seconds: 30),
    );
    controller.applyUpdate('CP-1', ChargerPresenceStatus.online);

    now = now.add(const Duration(seconds: 10));

    expect(controller.displayStateFor('CP-1').stale, isFalse);
  });
}
