import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/auth/auth_controller.dart';
import 'api_client.dart';
import 'config.dart';
import 'file_saver.dart';
import 'token_store.dart';

final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient(baseUrl: AppConfig.apiBaseUrl, tokens: ref.watch(tokenStoreProvider));
  // When the session can't be renewed, send the person back to the login screen.
  client.onSessionExpired = () => ref.read(authControllerProvider.notifier).sessionExpired();
  return client;
});

/// Saves downloaded reports on the phone (replaced by a fake in tests).
final fileSaverProvider = Provider<FileSaver>((ref) => NativeFileSaver());
