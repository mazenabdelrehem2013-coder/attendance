import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import 'token_store.dart';

/// Every API failure becomes one of these, with a message that can be shown to the employee.
class ApiException implements Exception {
  ApiException(this.statusCode, this.code, this.message);

  /// null = the server couldn't be reached at all.
  final int? statusCode;
  final String code;
  final String message;

  bool get isNetworkError => statusCode == null;

  @override
  String toString() => 'ApiException($statusCode, $code, $message)';
}

/// Talks to the backend. Adds the access token to requests and, when it has expired,
/// gets a new one with the refresh token and repeats the request once - so the employee
/// stays logged in. If that fails too, [onSessionExpired] is called.
class ApiClient {
  ApiClient({
    required String baseUrl,
    required this.tokens,
    Dio? dio,
    this.onSessionExpired,
  }) : _dio = dio ??
            Dio(BaseOptions(
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 20),
              sendTimeout: const Duration(seconds: 20),
            )) {
    _dio.options.baseUrl = baseUrl;
    _dio.options.contentType = Headers.jsonContentType;
  }

  final Dio _dio;
  final TokenStore tokens;
  void Function()? onSessionExpired;

  String? _accessToken;
  Completer<bool>? _refreshing;

  bool get hasAccessToken => _accessToken != null;

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) =>
      _send('GET', path, query: query);

  Future<dynamic> post(String path, {Object? data, bool auth = true}) =>
      _send('POST', path, data: data, auth: auth);

  Future<dynamic> put(String path, {Object? data}) => _send('PUT', path, data: data);

  /// Downloads a file (Excel / PDF report). GET when [data] is null, otherwise POST.
  Future<DownloadedFile> download(String path, {Object? data}) async {
    final response = await _send(data == null ? 'GET' : 'POST', path, data: data, bytes: true) as Response<dynamic>;
    final disposition = response.headers.value('content-disposition') ?? '';
    final name = RegExp(r'filename="([^"]+)"').firstMatch(disposition)?.group(1) ?? 'report';
    final type = response.headers.value(Headers.contentTypeHeader) ?? 'application/octet-stream';
    return DownloadedFile(Uint8List.fromList(response.data as List<int>), name, type.split(';').first);
  }

  /// Stores the tokens returned by login / refresh / change-password.
  Future<void> saveSession(Map<String, dynamic> tokenResponse) async {
    _accessToken = tokenResponse['access_token'] as String;
    final refresh = tokenResponse['refresh_token'] as String?;
    if (refresh != null) await tokens.saveRefreshToken(refresh);
  }

  Future<void> clearSession() async {
    _accessToken = null;
    await tokens.clear();
  }

  /// Gets a new access token using the stored refresh token. Only one refresh runs at a time
  /// (the server treats a refresh token used twice as stolen).
  Future<bool> refreshSession() {
    final running = _refreshing;
    if (running != null) return running.future;
    final completer = _refreshing = Completer<bool>();
    () async {
      try {
        final token = await tokens.readRefreshToken();
        if (token == null) return completer.complete(false);
        final response = await _dio.post('/auth/refresh', data: {'refresh_token': token});
        await saveSession(response.data as Map<String, dynamic>);
        completer.complete(true);
      } on DioException catch (e) {
        if (_isNetwork(e)) {
          completer.completeError(_networkError());
        } else {
          await clearSession();
          completer.complete(false);
        }
      } finally {
        _refreshing = null;
      }
    }();
    return completer.future;
  }

  Future<dynamic> _send(
    String method,
    String path, {
    Object? data,
    Map<String, dynamic>? query,
    bool auth = true,
    bool isRetry = false,
    bool bytes = false,
  }) async {
    try {
      final response = await _dio.request<dynamic>(
        path,
        data: data,
        queryParameters: query,
        options: Options(
          method: method,
          responseType: bytes ? ResponseType.bytes : null,
          headers: {
            if (auth && _accessToken != null) 'Authorization': 'Bearer $_accessToken',
          },
        ),
      );
      return bytes ? response : response.data;
    } on DioException catch (e) {
      if (_isNetwork(e)) throw _networkError();
      final status = e.response?.statusCode;
      if (status == 401 && auth && !isRetry) {
        if (await refreshSession()) {
          return _send(method, path, data: data, query: query, auth: auth, isRetry: true, bytes: bytes);
        }
        onSessionExpired?.call();
        throw ApiException(401, 'SESSION_EXPIRED', 'Your session has expired. Please log in again.');
      }
      throw _fromResponse(e.response);
    }
  }

  static bool _isNetwork(DioException e) =>
      e.response == null &&
      const {
        DioExceptionType.connectionError,
        DioExceptionType.connectionTimeout,
        DioExceptionType.receiveTimeout,
        DioExceptionType.sendTimeout,
        DioExceptionType.unknown,
      }.contains(e.type);

  static ApiException _networkError() => ApiException(
      null, 'NETWORK', "Can't reach the server. Check your internet connection and try again.");

  static ApiException _fromResponse(Response<dynamic>? response) {
    var body = response?.data;
    if (body is List<int>) {
      // A file download that failed: the error is JSON inside the bytes.
      try {
        body = jsonDecode(utf8.decode(body));
      } on FormatException {
        body = null;
      }
    }
    if (body is Map && body['error'] is Map) {
      final error = body['error'] as Map;
      return ApiException(response!.statusCode, '${error['code']}', '${error['message']}');
    }
    return ApiException(response?.statusCode, 'UNKNOWN', 'Something went wrong. Please try again.');
  }
}

/// A file received from the server.
class DownloadedFile {
  DownloadedFile(this.bytes, this.filename, this.mediaType);
  final Uint8List bytes;
  final String filename;
  final String mediaType;
}
