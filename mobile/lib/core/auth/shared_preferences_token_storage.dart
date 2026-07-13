import 'package:shared_preferences/shared_preferences.dart';

import 'auth_session.dart';

class SharedPreferencesTokenStorage implements TokenStorage {
  static const _key = 'refresh_token';

  @override
  Future<String?> readRefreshToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_key);
  }

  @override
  Future<void> saveRefreshToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, token);
  }

  @override
  Future<void> clearRefreshToken() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
  }
}
