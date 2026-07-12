import 'package:evagg_driver/features/session/session_tracking.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

SessionSnapshot _snapshot({
  SessionStatus status = SessionStatus.charging,
  double energyKwh = 1.0,
  double powerKw = 7.4,
  int costMinorUnits = 100,
  DateTime? updatedAt,
}) {
  final now = updatedAt ?? DateTime.utc(2026, 1, 1, 12);
  return SessionSnapshot(
    status: status,
    energyKwh: energyKwh,
    powerKw: powerKw,
    costMinorUnits: costMinorUnits,
    currency: 'AED',
    startedAt: now.subtract(const Duration(minutes: 10)),
    updatedAt: now,
  );
}

void main() {
  group('formatCost', () {
    test('formats minor units as a 2-decimal major-unit string', () {
      expect(formatCost(1234, 'AED'), '12.34 AED');
      expect(formatCost(0, 'USD'), '0.00 USD');
      expect(formatCost(5, 'USD'), '0.05 USD');
    });
  });

  group('formatElapsed', () {
    test('formats under an hour as mm:ss', () {
      expect(formatElapsed(const Duration(minutes: 4, seconds: 7)), '04:07');
    });

    test('formats an hour or more as h:mm:ss', () {
      expect(formatElapsed(const Duration(hours: 1, minutes: 2, seconds: 3)), '1:02:03');
    });
  });

  group('SessionTrackingController', () {
    test('start() fetches immediately and delivers the snapshot', () {
      fakeAsync((async) {
        final updates = <SessionSnapshot>[];
        final controller = SessionTrackingController(
          fetcher: () async => _snapshot(),
          stopper: () async {},
          onUpdate: updates.add,
        );

        controller.start();
        async.flushMicrotasks();

        expect(updates, hasLength(1));
        expect(controller.latest, isNotNull);
      });
    });

    test('polls again after each pollInterval elapses', () {
      fakeAsync((async) {
        var fetchCount = 0;
        final controller = SessionTrackingController(
          fetcher: () async {
            fetchCount++;
            return _snapshot(energyKwh: fetchCount.toDouble());
          },
          stopper: () async {},
          pollInterval: const Duration(seconds: 5),
        );

        controller.start();
        async.flushMicrotasks();
        expect(fetchCount, 1);

        async.elapse(const Duration(seconds: 5));
        expect(fetchCount, 2);

        async.elapse(const Duration(seconds: 10));
        expect(fetchCount, 4);

        controller.dispose();
      });
    });

    test('dispose stops further polling', () {
      fakeAsync((async) {
        var fetchCount = 0;
        final controller = SessionTrackingController(
          fetcher: () async {
            fetchCount++;
            return _snapshot();
          },
          stopper: () async {},
          pollInterval: const Duration(seconds: 5),
        );

        controller.start();
        async.flushMicrotasks();
        controller.dispose();

        async.elapse(const Duration(minutes: 5));
        expect(fetchCount, 1); // only the initial fetch from start()
      });
    });

    test('a stalled feed is reported stale once staleAfter elapses since the last success', () {
      fakeAsync((async) {
        var succeed = true;
        final controller = SessionTrackingController(
          fetcher: () async {
            if (!succeed) throw Exception('charger offline');
            return _snapshot();
          },
          stopper: () async {},
          pollInterval: const Duration(seconds: 5),
          staleAfter: const Duration(seconds: 20),
        );

        controller.start();
        async.flushMicrotasks();
        expect(controller.isStale, isFalse);

        succeed = false;
        async.elapse(const Duration(seconds: 15)); // 3 more failed polls, still under staleAfter
        expect(controller.isStale, isFalse);

        async.elapse(const Duration(seconds: 10)); // now > 20s since the last success
        expect(controller.isStale, isTrue);

        controller.dispose();
      });
    });

    test('a fetch error is reported via onFetchError and does not overwrite the last good snapshot', () {
      fakeAsync((async) {
        var succeed = true;
        final errors = <Object>[];
        final controller = SessionTrackingController(
          fetcher: () async {
            if (!succeed) throw Exception('network blip');
            return _snapshot(energyKwh: 3.0);
          },
          stopper: () async {},
          pollInterval: const Duration(seconds: 5),
          onFetchError: errors.add,
        );

        controller.start();
        async.flushMicrotasks();
        succeed = false;
        async.elapse(const Duration(seconds: 5));

        expect(errors, hasLength(1));
        expect(controller.latest!.energyKwh, 3.0); // last good value preserved

        controller.dispose();
      });
    });

    test('concurrent stop() calls collapse onto a single in-flight stopper invocation', () {
      fakeAsync((async) {
        var stopCallCount = 0;
        final controller = SessionTrackingController(
          fetcher: () async => _snapshot(),
          stopper: () async {
            stopCallCount++;
            await Future<void>.delayed(const Duration(seconds: 1));
          },
        );

        final first = controller.stop();
        final second = controller.stop();
        async.elapse(const Duration(seconds: 1));

        expect(stopCallCount, 1);
        expect(identical(first, second), isTrue);
      });
    });

    test('stop() can be called again after the previous stop completed', () {
      fakeAsync((async) {
        var stopCallCount = 0;
        final controller = SessionTrackingController(
          fetcher: () async => _snapshot(),
          stopper: () async {
            stopCallCount++;
          },
        );

        controller.stop();
        async.flushMicrotasks();
        controller.stop();
        async.flushMicrotasks();

        expect(stopCallCount, 2);
      });
    });
  });
}
