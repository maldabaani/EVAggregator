import 'package:evagg_driver/core/live_activity/live_activity_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('NoopLiveActivityController does nothing on start/end', () async {
    const controller = NoopLiveActivityController();

    await controller.startChargingActivity(sessionId: 's-1', chargerId: 'CP-1', connectorId: 1);
    await controller.endChargingActivity('s-1');
    // Nothing to assert beyond "didn't throw" — this is intentionally inert.
  });

  test('IosLiveActivityController is a no-op on this (non-iOS) test host', () async {
    final controller = IosLiveActivityController();

    // Platform.isIOS is false when `flutter test` runs on this machine, so
    // every method below returns immediately without touching the plugin's
    // platform channel — there is no iOS device/Xcode in this environment
    // to exercise the real ActivityKit path.
    await controller.init();
    await controller.startChargingActivity(sessionId: 's-1', chargerId: 'CP-1', connectorId: 1);
    await controller.endChargingActivity('s-1');
  });
}
