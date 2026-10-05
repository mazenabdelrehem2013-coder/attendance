/// Build-time settings. Nothing secret lives in the app - only the public API address.
///
/// Local development (Android emulator -> API on your PC):
///   flutter run                                  (uses the default below)
/// Real phone on the same Wi-Fi, or production:
///   flutter run --dart-define=API_BASE_URL=https://attendance.example.com/api/v1
class AppConfig {
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    // 10.0.2.2 is how the Android emulator reaches "localhost" on the host PC.
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );

  /// Google Cloud project number linked in the Play Console (Phase 19). Empty = Play Integrity
  /// not used (development builds).
  static const cloudProjectNumber = String.fromEnvironment('CLOUD_PROJECT_NUMBER');

  static const appVersion = '0.10.0';
}
