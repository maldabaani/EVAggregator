import 'package:flutter/foundation.dart';

import '../api/api_client.dart';

class DriverProfile {
  final String id;
  final String email;
  final String fullName;

  const DriverProfile({required this.id, required this.email, required this.fullName});

  factory DriverProfile.fromJson(Map<String, dynamic> json) => DriverProfile(
        id: json['id'] as String,
        email: json['email'] as String,
        fullName: json['full_name'] as String,
      );
}

/// Persists the refresh token across app restarts. Injected so tests use an
/// in-memory fake instead of the real `shared_preferences` plugin.
abstract class TokenStorage {
  Future<String?> readRefreshToken();
  Future<void> saveRefreshToken(String token);
  Future<void> clearRefreshToken();
}

/// Owns the driver's login state for the whole app. Wires itself into
/// [ApiClient.onUnauthorized] so any ambient API call (not just an explicit
/// login) can silently rotate an expired access token — the same rotation
/// endpoint the initial login response's refresh token is good for.
///
/// A silent rotation deliberately does *not* call [notifyListeners]: it
/// updates the token in place so the next retried request carries it, but
/// firing a change notification here would rebuild the whole authenticated
/// app shell (losing map/scroll state) on every background token refresh.
/// Listeners only need to know about the transitions that actually change
/// what's on screen: logging in, logging out, or losing the session
/// entirely because even the refresh token was rejected.
class AuthSession extends ChangeNotifier {
  final ApiClient apiClient;
  final TokenStorage tokenStorage;

  DriverProfile? _driver;
  String? _refreshToken;
  bool _restoring = true;

  AuthSession({required this.apiClient, required this.tokenStorage}) {
    apiClient.onUnauthorized = _refresh;
  }

  DriverProfile? get driver => _driver;
  bool get isAuthenticated => _driver != null;
  bool get isRestoring => _restoring;

  /// Called once at app startup: if a refresh token was persisted from a
  /// previous run, try to exchange it for a fresh session silently, rather
  /// than forcing the driver to log in again every time the app restarts.
  Future<void> restoreSession() async {
    _restoring = true;
    notifyListeners();
    final stored = await tokenStorage.readRefreshToken();
    if (stored != null) {
      _refreshToken = stored;
      await _refresh();
    }
    _restoring = false;
    notifyListeners();
  }

  Future<void> signup({required String email, required String fullName, required String password}) async {
    final response = await apiClient.post(
      '/auth/signup',
      body: {'email': email, 'full_name': fullName, 'password': password},
      authorized: false,
    );
    await _applySession(response as Map<String, dynamic>);
    notifyListeners();
  }

  Future<void> login({required String email, required String password}) async {
    final response = await apiClient.post(
      '/auth/login',
      body: {'email': email, 'password': password},
      authorized: false,
    );
    await _applySession(response as Map<String, dynamic>);
    notifyListeners();
  }

  Future<void> logout() async {
    _driver = null;
    _refreshToken = null;
    apiClient.accessToken = null;
    await tokenStorage.clearRefreshToken();
    notifyListeners();
  }

  Future<void> _applySession(Map<String, dynamic> response) async {
    apiClient.accessToken = response['access_token'] as String;
    _refreshToken = response['refresh_token'] as String;
    _driver = DriverProfile.fromJson(response['driver'] as Map<String, dynamic>);
    await tokenStorage.saveRefreshToken(_refreshToken!);
  }

  Future<String?> _refresh() async {
    final refreshToken = _refreshToken;
    if (refreshToken == null) {
      await _clearSessionAfterRefreshFailure();
      return null;
    }
    try {
      final response = await apiClient.post(
        '/auth/refresh',
        body: {'refresh_token': refreshToken},
        authorized: false,
      );
      await _applySession(response as Map<String, dynamic>);
      return apiClient.accessToken;
    } catch (_) {
      await _clearSessionAfterRefreshFailure();
      return null;
    }
  }

  Future<void> _clearSessionAfterRefreshFailure() async {
    final wasAuthenticated = _driver != null;
    _driver = null;
    _refreshToken = null;
    apiClient.accessToken = null;
    await tokenStorage.clearRefreshToken();
    if (wasAuthenticated) notifyListeners();
  }
}
