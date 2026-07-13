import 'dart:io';

import 'package:live_activities/live_activities.dart';

/// Drives the Lock Screen/Dynamic Island presence for an active charging
/// session. This Dart side only sends session data through ActivityKit —
/// rendering that data still needs a native iOS Widget Extension target
/// (a SwiftUI view + `ActivityAttributes` struct) added in Xcode, which
/// this repo cannot create or compile (no Mac/Xcode in this environment).
/// Until that target exists, `IosLiveActivityController` calls a real,
/// correctly-wired plugin API that has nothing on the other end to render.
abstract class LiveActivityController {
  Future<void> startChargingActivity({
    required String sessionId,
    required String chargerId,
    required int connectorId,
  });

  Future<void> endChargingActivity(String sessionId);
}

class NoopLiveActivityController implements LiveActivityController {
  const NoopLiveActivityController();

  @override
  Future<void> startChargingActivity({
    required String sessionId,
    required String chargerId,
    required int connectorId,
  }) async {}

  @override
  Future<void> endChargingActivity(String sessionId) async {}
}

class IosLiveActivityController implements LiveActivityController {
  final LiveActivities _liveActivities;
  bool _initialized = false;

  IosLiveActivityController([LiveActivities? liveActivities]) : _liveActivities = liveActivities ?? LiveActivities();

  bool get _supported => Platform.isIOS;

  /// Must be called once (e.g. from the app's root `initState`) before
  /// `startChargingActivity` — a no-op, non-throwing call on any other
  /// platform. The app group id must match the one configured on both the
  /// "Runner" target and the (not-yet-created) Widget Extension target in
  /// Xcode.
  Future<void> init() async {
    if (!_supported || _initialized) return;
    try {
      await _liveActivities.init(appGroupId: 'group.com.evaggregator.driver');
      _initialized = true;
    } catch (_) {
      // Live Activities are best-effort UI chrome — initialization failing
      // (e.g. the app group / widget extension isn't configured yet) must
      // never block the app from starting.
    }
  }

  @override
  Future<void> startChargingActivity({
    required String sessionId,
    required String chargerId,
    required int connectorId,
  }) async {
    if (!_supported) return;
    try {
      await _liveActivities.createActivity(sessionId, {
        'chargerId': chargerId,
        'connectorId': connectorId.toString(),
        'status': 'charging',
      });
    } catch (_) {
      // Same rationale as init(): never let Live Activity chrome block or
      // fail an actual charging session start.
    }
  }

  @override
  Future<void> endChargingActivity(String sessionId) async {
    if (!_supported) return;
    try {
      await _liveActivities.endActivity(sessionId);
    } catch (_) {}
  }
}
