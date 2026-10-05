import 'package:attendance_app/app.dart';
import 'package:attendance_app/core/api_client.dart';
import 'package:attendance_app/core/location_service.dart';
import 'package:attendance_app/core/providers.dart';
import 'package:attendance_app/core/token_store.dart';
import 'package:attendance_app/features/attendance/check_in_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_server.dart';
import 'fakes.dart';

/// Logged-in app (restored session) with the given phone status and fakes.
Future<FakeServer> openHome(WidgetTester tester, {String phone = 'ACTIVE', FakeLocation? location, bool qr = false}) async {
  // A typical phone screen: 1080 x 2400 pixels = 360 x 800 logical points.
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  final server = FakeServer()
    ..on('POST /auth/refresh', 200, tokens())
    ..on('GET /auth/me', 200, tokens()['user'])
    ..on('GET /employees/me', 200, profileJson)
    ..on('GET /attendance/today', 200, todayJson(qr: qr))
    ..on('POST /devices/register', 200, phoneJson(status: phone));
  final store = MemoryTokenStore('saved');
  await tester.pumpWidget(ProviderScope(
    retry: (_, _) => null,
    overrides: [
      tokenStoreProvider.overrideWithValue(store),
      deviceSecurityProvider.overrideWithValue(FakeDeviceSecurity()),
      locationServiceProvider.overrideWithValue(location ?? FakeLocation()),
      apiClientProvider.overrideWith((ref) =>
          ApiClient(baseUrl: 'http://test/api/v1', tokens: store, dio: Dio()..httpClientAdapter = server)),
    ],
    child: const AttendanceApp(),
  ));
  await tester.pumpAndSettle();
  return server;
}

Future<void> tapCheckIn(WidgetTester tester) async {
  await tester.ensureVisible(find.byKey(const Key('checkIn')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('checkIn')));
  await tester.pumpAndSettle();
}

Map<String, dynamic> result(String r, String message) => {
      'success': r == 'ACCEPTED', 'result': r, 'event_type': 'CHECK_IN', 'event_id': 'e', 'attendance_id': null,
      'server_time': '2026-10-05T08:07:00Z', 'status': null, 'verification_status': 'VERIFIED',
      'location': 'Lagos Office', 'distance_meters': r == 'ACCEPTED' ? 25 : null, 'message_code': 'X', 'message': message,
    };

const challenge = {'challenge_id': 'c-1', 'nonce': 'nonce-123456', 'expires_at': '2026-10-05T08:08:30Z', 'server_time': '2026-10-05T08:07:00Z'};

void main() {
  testWidgets('a new phone waits for HR approval and cannot check in yet', (tester) async {
    await openHome(tester, phone: 'PENDING_APPROVAL');
    expect(find.textContaining('waiting for HR approval'), findsOneWidget);
    final button = tester.widget<ButtonStyleButton>(find.byKey(const Key('checkIn')));
    expect(button.onPressed, isNull);
  });

  testWidgets('a deactivated phone is told to contact HR', (tester) async {
    await openHome(tester, phone: 'DEACTIVATED');
    expect(find.textContaining('contact HR'), findsOneWidget);
  });

  testWidgets('check-in accepted', (tester) async {
    final server = await openHome(tester);
    server
      ..on('POST /attendance/challenge', 200, challenge)
      ..on('POST /attendance/check-in', 200, result('ACCEPTED', 'Check-in successful.'));
    await tapCheckIn(tester);
    expect(find.text('Checked in'), findsWidgets);
    expect(find.text('Check-in successful.'), findsOneWidget);
    expect(find.textContaining('25 m from the office point'), findsOneWidget);
  });

  testWidgets('check-in flagged for review', (tester) async {
    final server = await openHome(tester);
    server
      ..on('POST /attendance/challenge', 200, challenge)
      ..on('POST /attendance/check-in', 200, result('FLAGGED', 'Your attendance was recorded and is waiting for HR review.'));
    await tapCheckIn(tester);
    expect(find.text('Recorded – pending review'), findsOneWidget);
  });

  testWidgets('check-in rejected shows the reason the employee may know', (tester) async {
    final server = await openHome(tester);
    server
      ..on('POST /attendance/challenge', 200, challenge)
      ..on('POST /attendance/check-in', 200, result('REJECTED', 'You appear to be outside your assigned work location.'));
    await tapCheckIn(tester);
    expect(find.text('Not accepted'), findsOneWidget);
    expect(find.text('You appear to be outside your assigned work location.'), findsOneWidget);
  });

  testWidgets('location permission blocked offers to open settings', (tester) async {
    final server = await openHome(tester,
        location: FakeLocation(problem: LocationProblem(LocationProblemKind.permissionDeniedForever)));
    await tapCheckIn(tester);
    expect(find.text('Location needed'), findsOneWidget);
    expect(find.text('Open settings'), findsOneWidget);
    expect(server.count('POST /attendance/challenge'), 0);
  });

  testWidgets('no internet while checking in', (tester) async {
    final server = await openHome(tester);
    server.offline = true;
    await tapCheckIn(tester);
    expect(find.textContaining("Can't reach the server"), findsOneWidget);
  });

  testWidgets('office requiring QR tells the employee', (tester) async {
    await openHome(tester, qr: true);
    expect(find.text('You will scan the QR code on the office screen.'), findsOneWidget);
  });
}
