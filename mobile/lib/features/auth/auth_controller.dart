import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';

/// Where the app is: still checking, logged out, can't reach the server, or logged in.
sealed class AuthState {
  const AuthState();
}

class AuthChecking extends AuthState {
  const AuthChecking();
}

class AuthLoggedOut extends AuthState {
  const AuthLoggedOut([this.message]);
  final String? message; // e.g. "Your session has expired"
}

class AuthOffline extends AuthState {
  const AuthOffline(this.message);
  final String message;
}

class AuthLoggedIn extends AuthState {
  const AuthLoggedIn(this.user);
  final UserSummary user;
}

final authControllerProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);

class AuthController extends Notifier<AuthState> {
  ApiClient get _api => ref.read(apiClientProvider);

  @override
  AuthState build() {
    Future.microtask(restore);
    return const AuthChecking();
  }

  /// On app start: if there is a saved session, renew it and load the user.
  Future<void> restore() async {
    state = const AuthChecking();
    try {
      if (await _api.tokens.readRefreshToken() == null || !await _api.refreshSession()) {
        state = const AuthLoggedOut();
        return;
      }
      state = AuthLoggedIn(UserSummary.fromJson(await _api.get('/auth/me') as Map<String, dynamic>));
    } on ApiException catch (e) {
      state = e.isNetworkError ? AuthOffline(e.message) : const AuthLoggedOut();
    }
  }

  /// Throws [ApiException] with a message to show on the login screen.
  Future<void> login(String identifier, String password) async {
    final response = await _api.post(
      '/auth/login',
      auth: false,
      data: {'identifier': identifier.trim(), 'password': password, 'client_type': 'MOBILE'},
    ) as Map<String, dynamic>;
    await _api.saveSession(response);
    state = AuthLoggedIn(UserSummary.fromJson(response['user'] as Map<String, dynamic>));
  }

  /// Logs out every other device; this one stays logged in with the new tokens returned.
  Future<void> changePassword(String current, String next) async {
    final response = await _api.post('/auth/change-password', data: {
      'current_password': current,
      'new_password': next,
      'client_type': 'MOBILE',
    }) as Map<String, dynamic>;
    await _api.saveSession(response);
    state = AuthLoggedIn(UserSummary.fromJson(response['user'] as Map<String, dynamic>));
  }

  Future<void> logout() async {
    final token = await _api.tokens.readRefreshToken();
    try {
      if (token != null) await _api.post('/auth/logout', auth: false, data: {'refresh_token': token});
    } on ApiException {
      // Logging out locally is what matters; the server session expires on its own.
    }
    await _api.clearSession();
    state = const AuthLoggedOut();
  }

  void sessionExpired() {
    _api.clearSession();
    state = const AuthLoggedOut('Your session has expired. Please log in again.');
  }
}
