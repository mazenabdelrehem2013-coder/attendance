import 'dart:convert';

import 'package:crypto/crypto.dart';

/// The exact text that is signed with the phone's hardware key for every check-in/out.
/// MUST match backend/app/services/attendance/canonical.py character for character
/// (a test on each side pins the same example).
String canonicalPayload({
  required String action, // CHECK_IN / CHECK_OUT
  required String challengeId,
  required String nonce,
  required String clientRequestId,
  required String deviceId,
  required double latitude,
  required double longitude,
  required double accuracyM,
  required int fixAgeMs,
  required bool isMock,
  required DateTime deviceTime,
  String? qrToken,
}) =>
    [
      'v1',
      action,
      challengeId,
      nonce,
      clientRequestId,
      deviceId,
      latitude.toStringAsFixed(6),
      longitude.toStringAsFixed(6),
      accuracyM.toStringAsFixed(2),
      '$fixAgeMs',
      isMock ? '1' : '0',
      '${deviceTime.millisecondsSinceEpoch}',
      qrToken ?? '',
    ].join('|');

/// SHA-256 (hex) - what Play Integrity binds its token to.
String requestHash(String payload) => sha256.convert(utf8.encode(payload)).toString();

/// Round to [decimals] so the number sent and the number signed are identical.
double roundTo(double value, int decimals) => double.parse(value.toStringAsFixed(decimals));
