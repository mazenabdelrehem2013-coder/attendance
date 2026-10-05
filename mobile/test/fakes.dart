import 'package:attendance_app/core/device_security.dart';
import 'package:attendance_app/core/location_service.dart';

class FakeDeviceSecurity implements DeviceSecurity {
  final signed = <String>[];

  @override
  Future<String> publicKey() async => 'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEfake';

  @override
  Future<String> sign(String payload) async {
    signed.add(payload);
    return 'signature-of-${signed.length}';
  }

  @override
  Future<String> fingerprint() async => 'a' * 64;

  @override
  Future<({String model, String osVersion})> deviceInfo() async => (model: 'Test phone', osVersion: 'Android 15');

  @override
  Future<String?> integrityToken(String requestHash, String cloudProjectNumber) async => null;
}

class FakeLocation implements LocationService {
  FakeLocation({this.problem, this.readingProblem, LocationReading? reading})
      : reading = reading ??
            LocationReading(
              latitude: 6.4283001,
              longitude: 3.4220004,
              accuracyM: 12.3456,
              isMocked: false,
              fixTime: DateTime.now().subtract(const Duration(seconds: 2)),
            );

  LocationProblem? problem; // thrown by ensureReady (permission, service off)
  LocationProblem? readingProblem; // thrown by currentReading (no GPS fix)
  LocationReading reading;
  int readings = 0;

  @override
  Future<void> ensureReady() async {
    if (problem != null) throw problem!;
  }

  @override
  Future<LocationReading> currentReading() async {
    if (readingProblem != null) throw readingProblem!;
    readings++;
    return reading;
  }

  @override
  Future<void> openSettings(LocationProblemKind kind) async {}
}
