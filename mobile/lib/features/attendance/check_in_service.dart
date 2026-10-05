import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/device_security.dart';
import '../../core/location_service.dart';
import '../../core/providers.dart';
import 'canonical.dart';

final deviceSecurityProvider = Provider<DeviceSecurity>((ref) => NativeDeviceSecurity());
final locationServiceProvider = Provider<LocationService>((ref) => GeolocatorLocationService());

/// This phone's registration with the company (HR must approve it once).
class PhoneRegistration {
  PhoneRegistration(this.id, this.status);
  final String id;
  final String status; // PENDING_APPROVAL / ACTIVE / REJECTED / DEACTIVATED / ...

  bool get approved => status == 'ACTIVE';
}

/// Registers this phone (idempotent - the same phone and key always get the same registration)
/// and returns its approval status.
final phoneProvider = FutureProvider.autoDispose<PhoneRegistration>((ref) async {
  final api = ref.watch(apiClientProvider);
  final security = ref.watch(deviceSecurityProvider);
  final store = ref.watch(tokenStoreProvider);
  final info = await security.deviceInfo();
  final json = await api.post('/devices/register', data: {
    'device_fingerprint': await security.fingerprint(),
    'install_id': await store.installId(),
    'public_key': await security.publicKey(),
    'device_model': info.model,
    'os_version': info.osVersion,
    'app_version': AppConfig.appVersion,
  }) as Map<String, dynamic>;
  return PhoneRegistration(json['id'] as String, json['status'] as String);
});

final checkInServiceProvider = Provider<CheckInService>((ref) => CheckInService(
      api: ref.watch(apiClientProvider),
      security: ref.watch(deviceSecurityProvider),
      location: ref.watch(locationServiceProvider),
    ));

enum CheckInStage { preparing, locating, verifying }

class CheckOutcome {
  CheckOutcome(this.json);
  final Map<String, dynamic> json;

  String get result => json['result'] as String; // ACCEPTED / FLAGGED / REJECTED
  String get message => json['message'] as String;
  String get eventType => json['event_type'] as String;
  String? get location => json['location'] as String?;
  int? get distanceMeters => json['distance_meters'] as int?;
  DateTime get serverTime => DateTime.parse(json['server_time'] as String).toLocal();
}

/// The check-in / check-out procedure. The phone only collects evidence; the server decides.
class CheckInService {
  CheckInService({required this.api, required this.security, required this.location, DateTime Function()? now})
      : _now = now ?? DateTime.now;

  final ApiClient api;
  final DeviceSecurity security;
  final LocationService location;
  final DateTime Function() _now;

  /// Throws [LocationProblem] or [ApiException] with a message for the employee.
  Future<CheckOutcome> run({
    required String action, // CHECK_IN / CHECK_OUT
    required String deviceId,
    String? qrToken,
    void Function(CheckInStage)? onStage,
  }) async {
    onStage?.call(CheckInStage.preparing);
    await location.ensureReady(); // ask for permission BEFORE using up a challenge

    // 1. One-time code from the server, right before reading GPS.
    final challenge = await api.post('/attendance/challenge',
        data: {'action': action, 'device_id': deviceId}) as Map<String, dynamic>;

    // 2. A fresh GPS reading.
    onStage?.call(CheckInStage.locating);
    final reading = await location.currentReading();

    // 3. Evidence, signed inside the phone's secure hardware.
    onStage?.call(CheckInStage.verifying);
    final now = _now();
    final deviceTime = DateTime.fromMillisecondsSinceEpoch(now.millisecondsSinceEpoch, isUtc: true);
    final fixAgeMs = now.difference(reading.fixTime).inMilliseconds.clamp(0, 86400000);
    final lat = roundTo(reading.latitude, 6);
    final lng = roundTo(reading.longitude, 6);
    final accuracy = roundTo(reading.accuracyM, 2);
    final clientRequestId = const Uuid().v4();
    final payload = canonicalPayload(
      action: action,
      challengeId: challenge['challenge_id'] as String,
      nonce: challenge['nonce'] as String,
      clientRequestId: clientRequestId,
      deviceId: deviceId,
      latitude: lat,
      longitude: lng,
      accuracyM: accuracy,
      fixAgeMs: fixAgeMs,
      isMock: reading.isMocked,
      deviceTime: deviceTime,
      qrToken: qrToken,
    );
    String? integrity;
    if (AppConfig.cloudProjectNumber.isNotEmpty) {
      integrity = await security.integrityToken(requestHash(payload), AppConfig.cloudProjectNumber);
    }
    final body = {
      'client_request_id': clientRequestId,
      'challenge_id': challenge['challenge_id'],
      'nonce': challenge['nonce'],
      'device_id': deviceId,
      'latitude': lat,
      'longitude': lng,
      'accuracy_m': accuracy,
      'fix_age_ms': fixAgeMs,
      'is_mock_location': reading.isMocked,
      'device_time': deviceTime.toIso8601String(),
      'app_version': AppConfig.appVersion,
      'qr_token': qrToken,
      'integrity_token': integrity,
      'signature': await security.sign(payload),
    };

    // 4. Send. On a network drop, the SAME request is sent again (same ID): the server
    //    returns the original result instead of recording it twice.
    final path = action == 'CHECK_IN' ? '/attendance/check-in' : '/attendance/check-out';
    for (var attempt = 1;; attempt++) {
      try {
        return CheckOutcome(await api.post(path, data: body) as Map<String, dynamic>);
      } on ApiException catch (e) {
        if (!e.isNetworkError || attempt == 3) rethrow;
        await Future<void>.delayed(Duration(seconds: attempt));
      }
    }
  }
}
