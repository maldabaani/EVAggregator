import 'package:flutter/material.dart';

import 'app.dart';
import 'core/api/api_client.dart';
import 'core/auth/auth_session.dart';
import 'core/auth/shared_preferences_token_storage.dart';

/// Points at `backend-edge` (docker-compose maps it to host port 8090) —
/// the only backend app driver auth, the map, and vehicles are mounted on;
/// see `evagg.edge_app`'s module docstring for why. Override at build time
/// with `--dart-define=API_BASE_URL=...` for a real device or a non-default
/// host.
const String apiBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8090');

void main() {
  final apiClient = ApiClient(baseUrl: apiBaseUrl);
  final authSession = AuthSession(apiClient: apiClient, tokenStorage: SharedPreferencesTokenStorage());
  runApp(EvAggregatorApp(apiClient: apiClient, authSession: authSession));
}
