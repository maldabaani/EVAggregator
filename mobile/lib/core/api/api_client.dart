import 'dart:convert';

import 'package:http/http.dart' as http;

/// Raised for any non-2xx response. `message` prefers the backend's
/// `detail` field (FastAPI's convention for HTTPException bodies) over the
/// raw response body, since that's what's actually useful to show a driver.
class ApiException implements Exception {
  final int statusCode;
  final String message;

  ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Called on a 401 to obtain a fresh access token (typically by rotating
/// the refresh token) so the failed request can be retried exactly once.
/// Returning null means the caller should give up — refresh failed too.
typedef TokenRefresher = Future<String?> Function();

/// Thin JSON/HTTP wrapper shared by every backend-facing service in the
/// mobile app (auth, map, vehicles, and future session/wallet calls) —
/// the single place that knows how to attach a bearer token and retry
/// once after a silent token refresh.
class ApiClient {
  final String baseUrl;
  final http.Client httpClient;
  String? accessToken;
  TokenRefresher? onUnauthorized;

  ApiClient({required this.baseUrl, http.Client? httpClient, this.accessToken, this.onUnauthorized})
      : httpClient = httpClient ?? http.Client();

  Uri _uri(String path, Map<String, String>? query) {
    final uri = Uri.parse('$baseUrl$path');
    if (query == null || query.isEmpty) return uri;
    return uri.replace(queryParameters: query);
  }

  Map<String, String> _headers(bool authorized) => {
        'Content-Type': 'application/json',
        if (authorized && accessToken != null) 'Authorization': 'Bearer $accessToken',
      };

  Future<dynamic> get(String path, {Map<String, String>? query, bool authorized = true}) =>
      _send('GET', path, query: query, authorized: authorized);

  Future<dynamic> post(String path, {Object? body, bool authorized = true}) =>
      _send('POST', path, body: body, authorized: authorized);

  Future<dynamic> patch(String path, {Object? body, bool authorized = true}) =>
      _send('PATCH', path, body: body, authorized: authorized);

  Future<dynamic> delete(String path, {bool authorized = true}) => _send('DELETE', path, authorized: authorized);

  Future<dynamic> _send(
    String method,
    String path, {
    Map<String, String>? query,
    Object? body,
    bool authorized = true,
    bool isRetry = false,
  }) async {
    final request = http.Request(method, _uri(path, query))..headers.addAll(_headers(authorized));
    if (body != null) {
      request.body = jsonEncode(body);
    }

    final streamed = await httpClient.send(request);
    final response = await http.Response.fromStream(streamed);

    if (response.statusCode == 401 && authorized && !isRetry && onUnauthorized != null) {
      final refreshedToken = await onUnauthorized!();
      if (refreshedToken != null) {
        accessToken = refreshedToken;
        return _send(method, path, query: query, body: body, authorized: authorized, isRetry: true);
      }
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty) return null;
      return jsonDecode(response.body);
    }
    throw ApiException(response.statusCode, _extractErrorMessage(response.body));
  }

  String _extractErrorMessage(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map && decoded['detail'] != null) {
        return decoded['detail'].toString();
      }
    } catch (_) {
      // Not JSON (or not a map with `detail`) — fall through to the raw body.
    }
    return body;
  }
}
