// App Store screenshots of the real app screens (iPhone 6.9", 1320 x 2868).
// The real widgets run against the test fake server with realistic sample data.
// Run from mobile/ (TZ picks the clock time shown, here late morning):
//   TZ=Etc/GMT+12 flutter test store/app_store_screenshots_test.dart --update-goldens
// Output: store/out/ios/*.png
import 'dart:io';

import 'package:attendance_app/app.dart';
import 'package:attendance_app/core/api_client.dart';
import 'package:attendance_app/core/providers.dart';
import 'package:attendance_app/core/token_store.dart';
import 'package:attendance_app/features/attendance/check_in_service.dart';
import 'package:attendance_app/features/auth/auth_controller.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';

import '../test/fake_server.dart';
import '../test/fakes.dart';

const _size = Size(1320, 2868);
const _ratio = 3.0;

Future<void> _loadFonts() async {
  final fonts = '${Platform.environment['FLUTTER_ROOT']}/bin/cache/artifacts/material_fonts';
  // Tests have no system font; Roboto stands in for it, also for styles that name no family.
  for (final family in ['Roboto', 'FlutterTest', 'Ahem', '.SF UI Text', '.SF UI Display', 'CupertinoSystemText', 'CupertinoSystemDisplay']) {
    final loader = FontLoader(family);
    for (final f in ['Roboto-Regular', 'Roboto-Medium', 'Roboto-Bold']) {
      loader.addFont(File('$fonts/$f.ttf').readAsBytes().then((b) => ByteData.view(b.buffer)));
    }
    await loader.load();
  }
  final icons = FontLoader('MaterialIcons')
    ..addFont(File('$fonts/MaterialIcons-Regular.otf').readAsBytes().then((b) => ByteData.view(b.buffer)));
  await icons.load();
}

final _now = DateTime.now();
final _day = DateFormat('yyyy-MM-dd').format(_now);
String _at(String hhmm) => '${_day}T$hhmm:00';

Map<String, dynamic> _user(String role) => {
      'id': 'u1',
      'email': 'ahmed.hassan@company.com',
      'role': role,
      'must_change_password': false,
      'employee': {'id': 'e1', 'employee_code': 'EMP-1024', 'full_name': 'Ahmed Hassan'},
    };

const _profile = {
  'employee_code': 'EMP-1024',
  'full_name': 'Ahmed Hassan',
  'email': 'ahmed.hassan@company.com',
  'phone': null,
  'department': 'Operations',
  'manager': 'Mona Adel',
  'primary_location_id': 'l1',
  'locations': [
    {'id': 'l1', 'name': 'Head Office', 'address': 'Cairo', 'timezone': 'Africa/Cairo'}
  ],
};

Map<String, dynamic> _today({required bool checkedIn}) => {
      'date': _day,
      'timezone': 'Africa/Cairo',
      'day_type': 'WORKING_DAY',
      'day_description': null,
      'scheduled_start': '09:00:00',
      'scheduled_end': '17:00:00',
      'state': checkedIn ? 'CHECKED_IN' : 'NOT_CHECKED_IN',
      'next_action': checkedIn ? 'CHECK_OUT' : 'CHECK_IN',
      'qr_required': false,
      'attendance': checkedIn
          ? {
              'date': _day,
              'location': 'Head Office',
              'first_check_in_at': _at('08:52'),
              'last_check_out_at': null,
              'worked_minutes': 185,
              'arrival_status': 'PRESENT',
              'departure_status': null,
              'day_status': 'PRESENT',
              'verification_status': 'VERIFIED',
              'sessions': [],
            }
          : null,
      'attempts': checkedIn
          ? [
              {
                'event_type': 'CHECK_IN',
                'server_time': _at('08:52'),
                'result': 'ACCEPTED',
                'message': 'Checked in at Head Office.',
              }
            ]
          : [],
    };

List<Map<String, dynamic>> _month() {
  final out = <Map<String, dynamic>>[];
  for (var d = 1; d < _now.day; d++) {
    final date = DateTime(_now.year, _now.month, d);
    if (date.weekday == DateTime.friday || date.weekday == DateTime.saturday) continue;
    final late = d % 9 == 4;
    final iso = DateFormat('yyyy-MM-dd').format(date);
    final inAt = late ? '09:24' : '08:${(40 + d % 18).toString().padLeft(2, '0')}';
    final outAt = '17:${(5 + d % 20).toString().padLeft(2, '0')}';
    final mins = DateFormat('HH:mm').parse(outAt).difference(DateFormat('HH:mm').parse(inAt)).inMinutes;
    out.add({
      'date': iso,
      'location': 'Head Office',
      'first_check_in_at': '${iso}T$inAt:00',
      'last_check_out_at': '${iso}T$outAt:00',
      'worked_minutes': mins,
      'arrival_status': late ? 'LATE' : 'PRESENT',
      'departure_status': 'CHECKED_OUT',
      'day_status': late ? 'LATE' : 'PRESENT',
      'verification_status': 'VERIFIED',
      'sessions': [],
    });
  }
  return out.reversed.toList();
}

const _reports = {
  'total': 3,
  'keep_days': 90,
  'items': [
    {
      'id': 'f1',
      'title': 'Weekly attendance report',
      'period': 'Last week',
      'scope': 'Your team',
      'schedule_name': 'Weekly',
      'format': 'PDF',
      'filename': 'attendance-weekly.pdf',
      'size_bytes': 184320,
      'created_at': '2026-10-25T06:00:00Z',
      'expires_at': '2027-01-23T06:00:00Z',
    },
    {
      'id': 'f2',
      'title': 'Monthly attendance report',
      'period': 'September 2026',
      'scope': 'Your team',
      'schedule_name': 'Monthly',
      'format': 'EXCEL',
      'filename': 'attendance-monthly.xlsx',
      'size_bytes': 96256,
      'created_at': '2026-10-01T06:00:00Z',
      'expires_at': '2026-12-30T06:00:00Z',
    },
  ],
};

Future<void> _start(WidgetTester tester, void Function(FakeServer) routes, {bool loggedIn = true}) async {
  tester.view
    ..physicalSize = _size
    ..devicePixelRatio = _ratio
    ..padding = const FakeViewPadding(top: 62 * _ratio, bottom: 34 * _ratio);
  addTearDown(tester.view.reset);
  final server = FakeServer();
  routes(server);
  final store = MemoryTokenStore(loggedIn ? 'saved' : null);
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
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pump(const Duration(milliseconds: 500));
}

void _loggedIn(FakeServer s, {String role = 'EMPLOYEE', bool checkedIn = false}) => s
  ..on('POST /auth/refresh', 200, {...tokens(), 'user': _user(role)})
  ..on('GET /auth/me', 200, _user(role))
  ..on('GET /employees/me', 200, _profile)
  ..on('GET /attendance/today', 200, _today(checkedIn: checkedIn))
  ..on('GET /attendance/history', 200, _month())
  ..on('GET /reports/ready', 200, _reports)
  ..on('POST /devices/register', 200, {...phoneJson(), 'approved_at': '2026-10-01T07:00:00Z'});

Future<void> _shot(WidgetTester tester, String name) async {
  // Let the phone registration finish, so CHECK IN shows as enabled.
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 500));
  }
  await expectLater(find.byType(MaterialApp), matchesGoldenFile('out/ios/$name.png'));
}

// Render as on an iPhone (iOS back arrow, scrolling and fonts).
final _iPhone = TargetPlatformVariant.only(TargetPlatform.iOS);

void main() {
  setUpAll(_loadFonts);

  testWidgets('1 check in', (tester) async {
    await _start(tester, (s) => _loggedIn(s));
    await _shot(tester, '1-check-in');
  }, variant: _iPhone);

  testWidgets('2 checked in', (tester) async {
    await _start(tester, (s) => _loggedIn(s, checkedIn: true));
    await _shot(tester, '2-checked-in');
  }, variant: _iPhone);

  testWidgets('3 history', (tester) async {
    await _start(tester, (s) => _loggedIn(s));
    await tester.tap(find.byTooltip('History'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    await _shot(tester, '3-history');
  }, variant: _iPhone);

  testWidgets('4 reports', (tester) async {
    await _start(tester, (s) => _loggedIn(s, role: 'MANAGER'));
    await tester.tap(find.byTooltip('Reports'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    await _shot(tester, '4-reports');
  }, variant: _iPhone);

  testWidgets('5 login', (tester) async {
    await _start(tester, (_) {}, loggedIn: false);
    await _shot(tester, '5-login');
  }, variant: _iPhone);
}
