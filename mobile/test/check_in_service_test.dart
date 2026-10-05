import 'dart:typed_data';

import 'package:attendance_app/core/api_client.dart';
import 'package:attendance_app/core/location_service.dart';
import 'package:attendance_app/core/token_store.dart';
import 'package:attendance_app/features/attendance/check_in_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_server.dart';
import 'fakes.dart';

Map<String, dynamic> outcome(String result, {String type = 'CHECK_IN', String message = 'Check-in successful.'}) => {
      'success': result == 'ACCEPTED',
      'result': result,
      'event_type': type,
      'event_id': 'e1',
      'attendance_id': 'a1',
      'server_time': '2026-10-05T08:07:00Z',
      'status': 'PRESENT',
      'verification_status': 'VERIFIED',
      'location': 'Lagos Office',
      'distance_meters': result == 'ACCEPTED' ? 25 : null,
      'message_code': 'X',
      'message': message,
    };

const challenge = {'challenge_id': 'c-1', 'nonce': 'nonce-123456', 'expires_at': '2026-10-05T08:08:30Z', 'server_time': '2026-10-05T08:07:00Z'};

void main() {
  late FakeServer server;
  late FakeDeviceSecurity security;
  late FakeLocation location;
  late CheckInService service;

  setUp(() {
    server = FakeServer();
    security = FakeDeviceSecurity();
    location = FakeLocation();
    final api = ApiClient(baseUrl: 'http://test/api/v1', tokens: MemoryTokenStore(), dio: Dio()..httpClientAdapter = server);
    service = CheckInService(api: api, security: security, location: location);
  });

  test('check-in: challenge, fresh GPS, signed evidence, server result', () async {
    server
      ..on('POST /attendance/challenge', 200, challenge)
      ..on('POST /attendance/check-in', 200, outcome('ACCEPTED'));
    final stages = <CheckInStage>[];
    final result = await service.run(action: 'CHECK_IN', deviceId: 'dev-1', onStage: stages.add);

    expect(result.result, 'ACCEPTED');
    expect(result.distanceMeters, 25);
    expect(stages, [CheckInStage.preparing, CheckInStage.locating, CheckInStage.verifying]);
    expect(location.readings, 1);

    final body = server.requests.last.data as Map<String, dynamic>;
    expect(body['challenge_id'], 'c-1');
    expect(body['latitude'], 6.4283); // rounded to 6 decimals before signing
    expect(body['accuracy_m'], 12.35);
    expect(body['is_mock_location'], false);
    expect(body['fix_age_ms'], greaterThanOrEqualTo(2000));
    expect(body.containsKey('isInside'), isFalse); // the phone never claims to be inside
    expect(body['signature'], 'signature-of-1');
    // What was signed matches what was sent.
    final signed = security.signed.single;
    expect(signed, startsWith('v1|CHECK_IN|c-1|nonce-123456|${body['client_request_id']}|dev-1|6.428300|3.422000|12.35|'));
    expect(signed, contains('|${DateTime.parse(body['device_time'] as String).millisecondsSinceEpoch}|'));
  });

  test('check-out uses the check-out endpoint and challenge', () async {
    server
      ..on('POST /attendance/challenge', 200, challenge)
      ..on('POST /attendance/check-out', 200, outcome('ACCEPTED', type: 'CHECK_OUT'));
    final result = await service.run(action: 'CHECK_OUT', deviceId: 'dev-1');
    expect(result.eventType, 'CHECK_OUT');
    expect((server.requests.first.data as Map)['action'], 'CHECK_OUT');
  });

  test('location permission denied: nothing is sent to the server', () async {
    location.problem = LocationProblem(LocationProblemKind.permissionDenied);
    await expectLater(service.run(action: 'CHECK_IN', deviceId: 'dev-1'), throwsA(isA<LocationProblem>()));
    expect(server.requests, isEmpty); // no challenge wasted
  });

  test('GPS unavailable gives a helpful message', () async {
    server.on('POST /attendance/challenge', 200, challenge);
    location.readingProblem = LocationProblem(LocationProblemKind.unavailable);
    await expectLater(
      service.run(action: 'CHECK_IN', deviceId: 'dev-1'),
      throwsA(isA<LocationProblem>().having((p) => p.message, 'message', contains('open area'))),
    );
    expect(server.count('POST /attendance/check-in'), 0);
  });

  test('fake-GPS flag from Android is passed on and signed', () async {
    location.reading = LocationReading(
        latitude: 6.4283, longitude: 3.422, accuracyM: 5, isMocked: true, fixTime: DateTime.now());
    server
      ..on('POST /attendance/challenge', 200, challenge)
      ..on('POST /attendance/check-in', 200, outcome('FLAGGED', message: 'Your attendance was recorded and is waiting for HR review.'));
    final result = await service.run(action: 'CHECK_IN', deviceId: 'dev-1');
    expect((server.requests.last.data as Map)['is_mock_location'], true);
    expect(security.signed.single, contains('|1|')); // mock flag inside the signed text
    expect(result.result, 'FLAGGED');
  });

  test('poor GPS: the server decides and its message is shown', () async {
    location.reading = LocationReading(
        latitude: 6.4283, longitude: 3.422, accuracyM: 350, isMocked: false, fixTime: DateTime.now());
    server
      ..on('POST /attendance/challenge', 200, challenge)
      ..on('POST /attendance/check-in', 200,
          outcome('REJECTED', message: 'Your location signal is weak. Move to an open area or near a window and try again.'));
    final result = await service.run(action: 'CHECK_IN', deviceId: 'dev-1');
    expect(result.result, 'REJECTED');
    expect(result.message, contains('signal is weak'));
  });

  test('QR code is included in the request and the signature', () async {
    server
      ..on('POST /attendance/challenge', 200, challenge)
      ..on('POST /attendance/check-in', 200, outcome('ACCEPTED'));
    await service.run(action: 'CHECK_IN', deviceId: 'dev-1', qrToken: 'Q1.abc.123.sig');
    expect((server.requests.last.data as Map)['qr_token'], 'Q1.abc.123.sig');
    expect(security.signed.single, endsWith('|Q1.abc.123.sig'));
  });

  test('phone not approved: the server refusal is shown', () async {
    server.on('POST /attendance/challenge', 403, error('DEVICE_PENDING_APPROVAL', 'This phone is waiting for HR approval.'));
    await expectLater(
      service.run(action: 'CHECK_IN', deviceId: 'dev-1'),
      throwsA(isA<ApiException>().having((e) => e.message, 'message', 'This phone is waiting for HR approval.')),
    );
  });

  test('no internet: clear error, nothing stored for later (no offline check-in)', () async {
    server.offline = true;
    await expectLater(
      service.run(action: 'CHECK_IN', deviceId: 'dev-1'),
      throwsA(isA<ApiException>().having((e) => e.isNetworkError, 'network', true)),
    );
  });

  test('network drop while sending: the SAME request is resent, not a new one', () async {
    server
      ..on('POST /attendance/challenge', 200, challenge)
      ..on('POST /attendance/check-in', 200, outcome('ACCEPTED'));
    var failures = 1;
    final flaky = _FlakyAdapter(server, () => failures-- > 0);
    final api = ApiClient(baseUrl: 'http://test/api/v1', tokens: MemoryTokenStore(), dio: Dio()..httpClientAdapter = flaky);
    final result = await CheckInService(api: api, security: security, location: location)
        .run(action: 'CHECK_IN', deviceId: 'dev-1');
    expect(result.result, 'ACCEPTED');
    final sends = flaky.checkInBodies;
    expect(sends.length, 2);
    expect(sends[0]['client_request_id'], sends[1]['client_request_id']);
    expect(sends[0]['signature'], sends[1]['signature']);
  });
}

/// Fails the first check-in send with a network error, then passes through.
class _FlakyAdapter implements HttpClientAdapter {
  _FlakyAdapter(this.inner, this.shouldFail);
  final FakeServer inner;
  final bool Function() shouldFail;
  final checkInBodies = <Map>[];

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) {
    if (options.path == '/attendance/check-in') {
      checkInBodies.add(options.data as Map);
      if (shouldFail()) throw DioException.connectionError(requestOptions: options, reason: 'dropped');
    }
    return inner.fetch(options, null, cancelFuture);
  }

  @override
  void close({bool force = false}) {}
}
