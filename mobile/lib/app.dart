import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme.dart';
import 'features/attendance/home_screen.dart';
import 'features/auth/auth_controller.dart';
import 'features/auth/change_password_screen.dart';
import 'features/auth/login_screen.dart';
import 'features/reports/reports_screen.dart';

class AttendanceApp extends StatelessWidget {
  const AttendanceApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Attendance',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        home: const AppRoot(),
      );
}

/// Shows the right screen for the login state. Logging out or an expired session always
/// brings the person back here, to the login screen.
class AppRoot extends ConsumerWidget {
  const AppRoot({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    return switch (auth) {
      AuthChecking() => const Scaffold(body: Center(child: CircularProgressIndicator())),
      AuthLoggedOut(:final message) => LoginScreen(key: ValueKey(message), notice: message),
      AuthOffline(:final message) => _OfflineScreen(message),
      AuthLoggedIn(:final user) when user.mustChangePassword => const ChangePasswordScreen(forced: true),
      AuthLoggedIn(:final user) when !user.isEmployee && user.canDownloadReports =>
        const ReportsScreen(showLogout: true),
      AuthLoggedIn(:final user) when !user.isEmployee => const _NotAnEmployeeScreen(),
      AuthLoggedIn() => const HomeScreen(),
    };
  }
}

class _OfflineScreen extends ConsumerWidget {
  const _OfflineScreen(this.message);
  final String message;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.wifi_off, size: 64, color: AppColors.neutral),
              const SizedBox(height: 16),
              Text(message, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: () => ref.read(authControllerProvider.notifier).restore(),
                child: const Text('TRY AGAIN'),
              ),
            ]),
          ),
        ),
      );
}

class _NotAnEmployeeScreen extends ConsumerWidget {
  const _NotAnEmployeeScreen();

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Text('This account has no employee record, so it can\'t record attendance. '
                  'Please use the web dashboard.', textAlign: TextAlign.center),
              const SizedBox(height: 16),
              OutlinedButton(
                onPressed: () => ref.read(authControllerProvider.notifier).logout(),
                child: const Text('Log out'),
              ),
            ]),
          ),
        ),
      );
}
