import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

/// Keeps the refresh token (the "stay logged in" token) between app launches, plus a random
/// ID for this installation of the app. The short-lived access token is only kept in memory.
abstract class TokenStore {
  Future<String?> readRefreshToken();
  Future<void> saveRefreshToken(String token);

  /// Removes the login only (the installation ID stays).
  Future<void> clear();

  /// Random ID created on first use, kept until the app is uninstalled.
  Future<String> installId();
}

/// Android Keystore-backed encrypted storage - other apps can't read it, and app data is
/// excluded from backups (android:allowBackup="false").
class SecureTokenStore implements TokenStore {
  SecureTokenStore([FlutterSecureStorage? storage]) : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  static const _key = 'refresh_token';
  static const _installKey = 'install_id';

  @override
  Future<String?> readRefreshToken() => _storage.read(key: _key);

  @override
  Future<void> saveRefreshToken(String token) => _storage.write(key: _key, value: token);

  @override
  Future<void> clear() => _storage.delete(key: _key);

  @override
  Future<String> installId() async {
    final existing = await _storage.read(key: _installKey);
    if (existing != null) return existing;
    final created = const Uuid().v4();
    await _storage.write(key: _installKey, value: created);
    return created;
  }
}

/// For tests.
class MemoryTokenStore implements TokenStore {
  MemoryTokenStore([this.token]);
  String? token;
  final String _installId = const Uuid().v4();

  @override
  Future<String?> readRefreshToken() async => token;

  @override
  Future<void> saveRefreshToken(String value) async => token = value;

  @override
  Future<void> clear() async => token = null;

  @override
  Future<String> installId() async => _installId;
}
