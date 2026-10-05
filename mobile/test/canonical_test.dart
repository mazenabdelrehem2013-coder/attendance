import 'package:attendance_app/features/attendance/canonical.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('signed text is identical to the server (same example as backend test_canonical_payload_format_is_stable)', () {
    final payload = canonicalPayload(
      action: 'CHECK_IN',
      challengeId: '22222222-2222-2222-2222-222222222222',
      nonce: 'abcdefghijklmnop',
      clientRequestId: '11111111-1111-1111-1111-111111111111',
      deviceId: '33333333-3333-3333-3333-333333333333',
      latitude: 6.4283,
      longitude: 3.422,
      accuracyM: 12.5,
      fixAgeMs: 1500,
      isMock: false,
      deviceTime: DateTime.utc(2026, 10, 5, 8),
    );
    expect(
      payload,
      'v1|CHECK_IN|22222222-2222-2222-2222-222222222222|abcdefghijklmnop|'
      '11111111-1111-1111-1111-111111111111|33333333-3333-3333-3333-333333333333|'
      '6.428300|3.422000|12.50|1500|0|1791187200000|',
    );
  });

  test('milliseconds and QR token are included', () {
    final payload = canonicalPayload(
      action: 'CHECK_OUT', challengeId: 'c', nonce: 'n', clientRequestId: 'r', deviceId: 'd',
      latitude: -0.5, longitude: 179.9999995, accuracyM: 0, fixAgeMs: 0, isMock: true,
      deviceTime: DateTime.utc(2026, 10, 5, 8, 0, 0, 123), qrToken: 'Q1.abc.1.xyz',
    );
    expect(payload.endsWith('|1|1791187200123|Q1.abc.1.xyz'), isTrue);
    expect(payload, contains('|-0.500000|'));
  });

  test('rounding before sending keeps sent and signed numbers identical', () {
    final lat = roundTo(6.42830049999, 6);
    expect(lat.toStringAsFixed(6), '6.428300');
    expect(roundTo(12.345678, 2), 12.35);
  });

  test('request hash is SHA-256 hex', () {
    expect(requestHash('x'), '2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881');
  });
}
