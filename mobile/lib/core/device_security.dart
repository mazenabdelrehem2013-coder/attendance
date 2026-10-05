import 'package:flutter/services.dart';

/// The phone's security features, implemented natively in MainActivity.kt.
abstract class DeviceSecurity {
  /// Base64 DER public key of the hardware-held EC P-256 key (created on first use).
  Future<String> publicKey();

  /// Base64 ECDSA (SHA-256) signature made inside the Android Keystore.
  Future<String> sign(String payload);

  /// SHA-256 (hex) of ANDROID_ID - identifies this phone for this app.
  Future<String> fingerprint();

  Future<({String model, String osVersion})> deviceInfo();

  /// Google Play Integrity token bound to [requestHash], or null if unavailable.
  Future<String?> integrityToken(String requestHash, String cloudProjectNumber);
}

class NativeDeviceSecurity implements DeviceSecurity {
  static const _channel = MethodChannel('attendance/device');

  @override
  Future<String> publicKey() async => (await _channel.invokeMethod<String>('publicKey'))!;

  @override
  Future<String> sign(String payload) async =>
      (await _channel.invokeMethod<String>('sign', {'payload': payload}))!;

  @override
  Future<String> fingerprint() async => (await _channel.invokeMethod<String>('fingerprint'))!;

  @override
  Future<({String model, String osVersion})> deviceInfo() async {
    final info = (await _channel.invokeMapMethod<String, String>('deviceInfo'))!;
    return (model: info['model']!, osVersion: info['osVersion']!);
  }

  @override
  Future<String?> integrityToken(String requestHash, String cloudProjectNumber) async {
    try {
      return await _channel.invokeMethod<String>(
          'integrityToken', {'requestHash': requestHash, 'cloudProjectNumber': cloudProjectNumber});
    } on PlatformException {
      return null; // no Play services / not installed from Play: the server decides what that means
    }
  }
}
