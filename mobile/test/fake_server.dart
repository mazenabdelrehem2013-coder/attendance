import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

/// A pretend backend for tests: answers requests by "METHOD /path" with canned JSON.
class FakeServer implements HttpClientAdapter {
  final Map<String, List<(int, Object?)>> _routes = {};
  final List<RequestOptions> requests = [];
  bool offline = false;

  /// Queue responses for a route; the last one repeats.
  void on(String route, int status, [Object? body]) => (_routes[route] ??= []).add((status, body));

  /// A file download (Excel / PDF).
  void onFile(String route, List<int> bytes, String filename, String mediaType) =>
      (_routes[route] ??= []).add((200, _FakeFile(bytes, filename, mediaType)));

  int count(String route) => requests.where((r) => '${r.method} ${r.path}' == route).length;

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    requests.add(options);
    if (offline) {
      throw DioException.connectionError(requestOptions: options, reason: 'offline');
    }
    final key = '${options.method} ${options.path}';
    final queue = _routes[key];
    if (queue == null || queue.isEmpty) {
      return _json(404, {'error': {'code': 'NOT_FOUND', 'message': 'No fake route for $key'}});
    }
    final (status, body) = queue.length > 1 ? queue.removeAt(0) : queue.first;
    if (body is _FakeFile) {
      return ResponseBody.fromBytes(body.bytes, 200, headers: {
        Headers.contentTypeHeader: [body.mediaType],
        'content-disposition': ['attachment; filename="${body.filename}"'],
      });
    }
    return _json(status, body);
  }

  ResponseBody _json(int status, Object? body) => ResponseBody.fromString(
        jsonEncode(body),
        status,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );

  @override
  void close({bool force = false}) {}
}

class _FakeFile {
  _FakeFile(this.bytes, this.filename, this.mediaType);
  final List<int> bytes;
  final String filename;
  final String mediaType;
}

Map<String, dynamic> error(String code, String message) => {
      'error': {'code': code, 'message': message, 'request_id': 'test'}
    };

Map<String, dynamic> tokens({bool mustChange = false, String refresh = 'refresh-2'}) => {
      'access_token': 'access-${DateTime.now().microsecondsSinceEpoch}',
      'token_type': 'bearer',
      'expires_in': 900,
      'refresh_token': refresh,
      'refresh_expires_at': '2026-11-01T00:00:00Z',
      'user': {
        'id': 'u1',
        'email': 'emp0101@example.com',
        'role': 'EMPLOYEE',
        'must_change_password': mustChange,
        'employee': {'id': 'e1', 'employee_code': 'EMP-0101', 'full_name': 'Chinedu Eze'},
      },
    };

const profileJson = {
  'employee_code': 'EMP-0101',
  'full_name': 'Chinedu Eze',
  'email': 'emp0101@example.com',
  'phone': null,
  'department': 'Sales',
  'manager': 'Tunde Bakare',
  'primary_location_id': 'l1',
  'locations': [
    {'id': 'l1', 'name': 'Lagos Office', 'address': 'Victoria Island', 'timezone': 'Africa/Lagos'}
  ],
};

Map<String, dynamic> todayJson({String state = 'NOT_CHECKED_IN', List attempts = const [], bool qr = false}) => {
      'date': '2026-10-05',
      'timezone': 'Africa/Lagos',
      'day_type': 'WORKING_DAY',
      'day_description': null,
      'scheduled_start': '09:00:00',
      'scheduled_end': '18:00:00',
      'state': state,
      'next_action': state == 'CHECKED_IN' ? 'CHECK_OUT' : 'CHECK_IN',
      'qr_required': qr,
      'attendance': null,
      'attempts': attempts,
    };

Map<String, dynamic> phoneJson({String status = 'ACTIVE'}) => {
      'id': 'dev-1',
      'employee_id': 'e1',
      'employee_name': 'Chinedu Eze',
      'employee_code': 'EMP-0101',
      'status': status,
      'platform': 'android',
      'device_model': 'Test phone',
      'os_version': 'Android 15',
      'app_version': '0.10.0',
      'requested_at': '2026-10-05T07:00:00Z',
      'approved_at': null,
      'decision_note': null,
      'last_seen_at': null,
    };
