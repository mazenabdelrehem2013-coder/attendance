import 'package:attendance_app/app.dart';
import 'package:attendance_app/core/api_client.dart';
import 'package:attendance_app/core/providers.dart';
import 'package:attendance_app/core/token_store.dart';
import 'package:attendance_app/features/attendance/check_in_service.dart';
import 'package:attendance_app/features/auth/auth_controller.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_server.dart';
import 'fakes.dart';

/// Starts the whole app against the fake server.
Future<FakeServer> startApp(WidgetTester tester, {String? savedRefreshToken, void Function(FakeServer)? routes}) async {
  final server = FakeServer();
  routes?.call(server);
  final store = MemoryTokenStore(savedRefreshToken);
  await tester.pumpWidget(ProviderScope(
    retry: (_, _) => null,
    overrides: [
      tokenStoreProvider.overrideWithValue(store),
      deviceSecurityProvider.overrideWithValue(FakeDeviceSecurity()),
      locationServiceProvider.overrideWithValue(FakeLocation()),
      apiClientProvider.overrideWith((ref) {
        final client = ApiClient(baseUrl: 'http://test/api/v1', tokens: store, dio: Dio()..httpClientAdapter = server);
        client.onSessionExpired = () => ref.read(authControllerProvider.notifier).sessionExpired();
        return client;
      }),
    ],
    child: const AttendanceApp(),
  ));
  await tester.pumpAndSettle();
  return server;
}

void homeRoutes(FakeServer s) => s
  ..on('GET /employees/me', 200, profileJson)
  ..on('GET /attendance/today', 200, todayJson())
  ..on('POST /devices/register', 200, phoneJson());

Future<void> logIn(WidgetTester tester, String id, String password) async {
  await tester.enterText(find.byKey(const Key('identifier')), id);
  await tester.enterText(find.byKey(const Key('password')), password);
  await tester.tap(find.byKey(const Key('login')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('first launch shows the login screen', (tester) async {
    await startApp(tester);
    expect(find.text('Log in with your employee ID or email'), findsOneWidget);
  });

  testWidgets('empty form shows what is missing', (tester) async {
    final server = await startApp(tester);
    await tester.tap(find.byKey(const Key('login')));
    await tester.pump();
    expect(find.text('Enter your employee ID or email'), findsOneWidget);
    expect(find.text('Enter your password'), findsOneWidget);
    expect(server.requests, isEmpty);
  });

  testWidgets('wrong password shows the server message', (tester) async {
    await startApp(tester, routes: (s) => s.on('POST /auth/login', 401, error('INVALID_CREDENTIALS', 'Invalid login details.')));
    await logIn(tester, 'EMP-0101', 'wrong');
    expect(find.text('Invalid login details.'), findsOneWidget);
  });

  testWidgets('server unreachable during login', (tester) async {
    final server = await startApp(tester);
    server.offline = true;
    await logIn(tester, 'EMP-0101', 'whatever');
    expect(find.textContaining("Can't reach the server"), findsOneWidget);
  });

  testWidgets('successful login shows the home screen with profile and status', (tester) async {
    await startApp(tester, routes: (s) {
      s.on('POST /auth/login', 200, tokens());
      homeRoutes(s);
    });
    await logIn(tester, 'EMP-0101', 'Correct-Password-1');
    expect(find.text('Chinedu Eze'), findsOneWidget);
    expect(find.textContaining('EMP-0101'), findsOneWidget);
    expect(find.text('Tunde Bakare'), findsOneWidget);
    expect(find.text('Lagos Office'), findsOneWidget);
    expect(find.text('Not checked in'), findsOneWidget);
    expect(find.text('Working hours 09:00 – 18:00'), findsOneWidget);
    expect(find.text('CHECK IN'), findsOneWidget);
  });

  testWidgets('checked-in state shows CHECK OUT and the status', (tester) async {
    await startApp(tester, savedRefreshToken: 'saved', routes: (s) {
      s
        ..on('POST /auth/refresh', 200, tokens())
        ..on('GET /auth/me', 200, tokens()['user'])
        ..on('GET /employees/me', 200, profileJson)
        ..on('POST /devices/register', 200, phoneJson())
        ..on('GET /attendance/today', 200, todayJson(state: 'CHECKED_IN'));
    });
    expect(find.text('Checked in'), findsOneWidget);
    expect(find.text('CHECK OUT'), findsOneWidget);
  });

  testWidgets('a rejected attempt is explained to the employee', (tester) async {
    await startApp(tester, savedRefreshToken: 'saved', routes: (s) {
      s
        ..on('POST /auth/refresh', 200, tokens())
        ..on('GET /auth/me', 200, tokens()['user'])
        ..on('GET /employees/me', 200, profileJson)
        ..on('GET /attendance/today', 200, todayJson(attempts: [
          {
            'event_type': 'CHECK_IN',
            'server_time': '2026-10-05T08:05:00Z',
            'result': 'REJECTED',
            'message': 'You appear to be outside your assigned work location.',
          }
        ]));
    });
    expect(find.text('Last attempt was not accepted'), findsOneWidget);
    expect(find.text('You appear to be outside your assigned work location.'), findsWidgets);
  });

  testWidgets('saved session is restored without logging in again', (tester) async {
    final server = await startApp(tester, savedRefreshToken: 'saved', routes: (s) {
      s
        ..on('POST /auth/refresh', 200, tokens())
        ..on('GET /auth/me', 200, tokens()['user']);
      homeRoutes(s);
    });
    expect(find.text('Chinedu Eze'), findsOneWidget);
    expect(server.count('POST /auth/login'), 0);
  });

  testWidgets('expired session goes back to login with an explanation', (tester) async {
    await startApp(tester, savedRefreshToken: 'saved', routes: (s) {
      s
        ..on('POST /auth/refresh', 200, tokens()) // app start: works
        ..on('POST /auth/refresh', 401, error('INVALID_SESSION', 'x')) // later: refused
        ..on('GET /auth/me', 200, tokens()['user'])
        ..on('GET /employees/me', 401, error('INVALID_TOKEN', 'x'))
        ..on('GET /attendance/today', 401, error('INVALID_TOKEN', 'x'));
    });
    expect(find.text('Your session has expired. Please log in again.'), findsOneWidget);
    expect(find.byKey(const Key('login')), findsOneWidget);
  });

  testWidgets('no network at start offers to try again', (tester) async {
    final server = FakeServer()..offline = true;
    final store = MemoryTokenStore('saved');
    await tester.pumpWidget(ProviderScope(
      retry: (_, _) => null,
      overrides: [
        tokenStoreProvider.overrideWithValue(store),
        deviceSecurityProvider.overrideWithValue(FakeDeviceSecurity()),
        locationServiceProvider.overrideWithValue(FakeLocation()),
        apiClientProvider.overrideWith((ref) =>
            ApiClient(baseUrl: 'http://test/api/v1', tokens: store, dio: Dio()..httpClientAdapter = server)),
      ],
      child: const AttendanceApp(),
    ));
    await tester.pumpAndSettle();
    expect(find.text('TRY AGAIN'), findsOneWidget);
    expect(store.token, 'saved'); // being offline doesn't log you out
  });

  testWidgets('new account must change the temporary password first', (tester) async {
    await startApp(tester, routes: (s) => s.on('POST /auth/login', 200, tokens(mustChange: true)));
    await logIn(tester, 'EMP-0101', 'Temp-Pass-123');
    expect(find.text('Temporary password'), findsOneWidget);
    expect(find.text('CHECK IN'), findsNothing);
  });

  testWidgets('logout returns to the login screen and forgets the session', (tester) async {
    final store = MemoryTokenStore();
    final server = FakeServer()
      ..on('POST /auth/login', 200, tokens())
      ..on('POST /auth/logout', 204);
    homeRoutes(server);
    await tester.pumpWidget(ProviderScope(
      retry: (_, _) => null,
      overrides: [
        tokenStoreProvider.overrideWithValue(store),
        deviceSecurityProvider.overrideWithValue(FakeDeviceSecurity()),
        locationServiceProvider.overrideWithValue(FakeLocation()),
        apiClientProvider.overrideWith((ref) =>
            ApiClient(baseUrl: 'http://test/api/v1', tokens: store, dio: Dio()..httpClientAdapter = server)),
      ],
      child: const AttendanceApp(),
    ));
    await tester.pumpAndSettle();
    await logIn(tester, 'EMP-0101', 'pw');
    expect(store.token, 'refresh-2');
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Log out'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('login')), findsOneWidget);
    expect(store.token, isNull);
    expect(server.count('POST /auth/logout'), 1);
  });
}
