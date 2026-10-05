import 'package:attendance_app/core/api_client.dart';
import 'package:attendance_app/core/token_store.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_server.dart';

void main() {
  late FakeServer server;
  late MemoryTokenStore store;
  late ApiClient api;
  var expired = 0;

  setUp(() {
    server = FakeServer();
    store = MemoryTokenStore('refresh-1');
    expired = 0;
    api = ApiClient(baseUrl: 'http://test/api/v1', tokens: store, dio: Dio()..httpClientAdapter = server)
      ..onSessionExpired = () => expired++;
  });

  test('server error message is passed through for the employee', () async {
    server.on('POST /auth/login', 401, error('INVALID_CREDENTIALS', 'Invalid login details.'));
    await expectLater(
      api.post('/auth/login', auth: false, data: {}),
      throwsA(isA<ApiException>()
          .having((e) => e.code, 'code', 'INVALID_CREDENTIALS')
          .having((e) => e.message, 'message', 'Invalid login details.')),
    );
    expect(expired, 0); // a failed login is not an "expired session"
  });

  test('no network gives a clear message', () async {
    server.offline = true;
    await expectLater(
      api.get('/attendance/today'),
      throwsA(isA<ApiException>().having((e) => e.isNetworkError, 'network', true)),
    );
  });

  test('expired access token is renewed and the request repeated once', () async {
    server
      ..on('GET /attendance/today', 401, error('INVALID_TOKEN', 'expired'))
      ..on('GET /attendance/today', 200, todayJson())
      ..on('POST /auth/refresh', 200, tokens(refresh: 'refresh-2'));
    final result = await api.get('/attendance/today') as Map;
    expect(result['state'], 'NOT_CHECKED_IN');
    expect(store.token, 'refresh-2'); // rotated token saved
    expect(server.count('POST /auth/refresh'), 1);
    final retried = server.requests.last;
    expect(retried.headers['Authorization'], startsWith('Bearer access-'));
  });

  test('if renewing fails the session ends', () async {
    server
      ..on('GET /attendance/today', 401, error('INVALID_TOKEN', 'expired'))
      ..on('POST /auth/refresh', 401, error('INVALID_SESSION', 'expired'));
    await expectLater(
      api.get('/attendance/today'),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', 'SESSION_EXPIRED')),
    );
    expect(expired, 1);
    expect(store.token, isNull); // stored session wiped
  });

  test('two requests at once share ONE refresh (the server treats reuse as theft)', () async {
    server
      ..on('GET /a', 401, error('INVALID_TOKEN', 'x'))
      ..on('GET /a', 200, {'ok': 1})
      ..on('GET /b', 401, error('INVALID_TOKEN', 'x'))
      ..on('GET /b', 200, {'ok': 2})
      ..on('POST /auth/refresh', 200, tokens());
    await Future.wait([api.get('/a'), api.get('/b')]);
    expect(server.count('POST /auth/refresh'), 1);
  });
}
