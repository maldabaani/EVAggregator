import 'package:evagg_driver/features/session/live_session_screen.dart';
import 'package:evagg_driver/features/session/session_tracking.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

SessionSnapshot _snapshot({
  SessionStatus status = SessionStatus.charging,
  double energyKwh = 5.25,
  double powerKw = 7.4,
  int costMinorUnits = 1234,
}) {
  final now = DateTime.now();
  return SessionSnapshot(
    status: status,
    energyKwh: energyKwh,
    powerKw: powerKw,
    costMinorUnits: costMinorUnits,
    currency: 'AED',
    startedAt: now.subtract(const Duration(minutes: 12, seconds: 34)),
    updatedAt: now,
  );
}

void main() {
  testWidgets('shows a loading indicator before the first fetch resolves, then the session metrics', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LiveSessionScreen(
          sessionFetcher: () async => _snapshot(),
          sessionStopper: () async {},
        ),
      ),
    );

    expect(find.byKey(const Key('session-loading')), findsOneWidget);

    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('session-loading')), findsNothing);
    expect(find.byKey(const Key('energy-value')), findsOneWidget);
    expect(tester.widget<Text>(find.byKey(const Key('energy-value'))).data, '5.25 kWh');
    expect(tester.widget<Text>(find.byKey(const Key('power-value'))).data, '7.4 kW');
    expect(tester.widget<Text>(find.byKey(const Key('cost-value'))).data, '12.34 AED');
    expect(tester.widget<Text>(find.byKey(const Key('status-value'))).data, 'charging');
  });

  testWidgets('canceling the stop confirmation dialog leaves the session running', (tester) async {
    var stopCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: LiveSessionScreen(
          sessionFetcher: () async => _snapshot(),
          sessionStopper: () async => stopCalls++,
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    await tester.tap(find.byKey(const Key('stop-session-button')));
    await tester.pump();
    expect(find.text('Stop charging?'), findsOneWidget);

    await tester.tap(find.byKey(const Key('stop-session-cancel')));
    await tester.pump();

    expect(stopCalls, 0);
    expect(find.byKey(const Key('stop-session-button')), findsOneWidget);
  });

  testWidgets('confirming stop calls the stopper and shows the session-ended state', (tester) async {
    var stopCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: LiveSessionScreen(
          sessionFetcher: () async => _snapshot(),
          sessionStopper: () async => stopCalls++,
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    await tester.tap(find.byKey(const Key('stop-session-button')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('stop-session-confirm')));
    await tester.pump();
    await tester.pump();

    expect(stopCalls, 1);
    expect(find.byKey(const Key('session-ended-label')), findsOneWidget);
    expect(find.byKey(const Key('stop-session-button')), findsNothing);
  });

  testWidgets('a failed stop shows an error and re-enables the stop button', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LiveSessionScreen(
          sessionFetcher: () async => _snapshot(),
          sessionStopper: () async => throw Exception('charger unreachable'),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    await tester.tap(find.byKey(const Key('stop-session-button')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('stop-session-confirm')));
    await tester.pump();
    await tester.pump();

    expect(find.text('Could not stop the session. Please try again.'), findsOneWidget);
    final button = tester.widget<ElevatedButton>(find.byKey(const Key('stop-session-button')));
    expect(button.onPressed, isNotNull);
  });

  testWidgets('a stale feed shows the connection-lost banner', (tester) async {
    var succeed = true;
    await tester.pumpWidget(
      MaterialApp(
        home: LiveSessionScreen(
          sessionFetcher: () async {
            if (!succeed) throw Exception('offline');
            return _snapshot();
          },
          sessionStopper: () async {},
          pollInterval: const Duration(seconds: 1),
          staleAfter: const Duration(seconds: 2),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('stale-banner')), findsNothing);

    succeed = false;
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));

    expect(find.byKey(const Key('stale-banner')), findsOneWidget);
  });
}
