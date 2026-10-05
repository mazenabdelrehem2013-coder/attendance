import 'dart:convert';
import 'dart:typed_data';

import 'package:attendance_app/app.dart';
import 'package:attendance_app/core/api_client.dart';
import 'package:attendance_app/core/file_saver.dart';
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

class FakeFileSaver implements FileSaver {
  FakeFileSaver({this.location = 'Downloads/Attendance'});
  final String location;
  final saved = <(String, int)>[];
  final opened = <String>[];

  @override
  Future<SavedFile> save(Uint8List bytes, String filename, String mediaType) async {
    saved.add((filename, bytes.length));
    return SavedFile(uri: 'content://x/$filename', location: location, filename: filename, mediaType: mediaType);
  }

  @override
  Future<bool> open(SavedFile file) async {
    opened.add(file.filename);
    return true;
  }
}

Map<String, dynamic> staffTokens(String role, {bool employee = true}) => {
      ...tokens(),
      'user': {
        'id': 'u2',
        'email': 'manager.lagos@example.com',
        'role': role,
        'must_change_password': false,
        'employee': employee ? {'id': 'e2', 'employee_code': 'EMP-0002', 'full_name': 'Tunde Bakare'} : null,
      },
    };

const readyJson = {
  'total': 1,
  'keep_days': 90,
  'items': [
    {
      'id': 'f1',
      'title': 'Weekly attendance report',
      'period': '28 September 2026 – 04 October 2026',
      'scope': 'Your team',
      'schedule_name': 'Weekly',
      'format': 'PDF',
      'filename': 'attendance-weekly-2026-09-28-to-2026-10-04.pdf',
      'size_bytes': 30000,
      'rows': 7,
      'created_at': '2026-10-05T07:00:00Z',
    }
  ],
};

Future<(FakeServer, FakeFileSaver)> start(WidgetTester tester, Map<String, dynamic> login,
    {FakeFileSaver? saver, void Function(FakeServer)? routes}) async {
  final server = FakeServer()
    ..on('POST /auth/login', 200, login)
    ..on('GET /employees/me', 200, profileJson)
    ..on('GET /attendance/today', 200, todayJson())
    ..on('POST /devices/register', 200, phoneJson())
    ..on('GET /reports/ready', 200, readyJson);
  routes?.call(server);
  final files = saver ?? FakeFileSaver();
  final store = MemoryTokenStore(null);
  await tester.pumpWidget(ProviderScope(
    retry: (_, _) => null,
    overrides: [
      tokenStoreProvider.overrideWithValue(store),
      deviceSecurityProvider.overrideWithValue(FakeDeviceSecurity()),
      locationServiceProvider.overrideWithValue(FakeLocation()),
      fileSaverProvider.overrideWithValue(files),
      apiClientProvider.overrideWith((ref) {
        final client = ApiClient(baseUrl: 'http://test/api/v1', tokens: store, dio: Dio()..httpClientAdapter = server);
        client.onSessionExpired = () => ref.read(authControllerProvider.notifier).sessionExpired();
        return client;
      }),
    ],
    child: const AttendanceApp(),
  ));
  await tester.pumpAndSettle();
  await tester.enterText(find.byKey(const Key('identifier')), 'someone');
  await tester.enterText(find.byKey(const Key('password')), 'pw');
  await tester.tap(find.byKey(const Key('login')));
  await tester.pumpAndSettle();
  return (server, files);
}

void main() {
  testWidgets('employees have no reports button', (tester) async {
    await start(tester, tokens());
    expect(find.byTooltip('History'), findsOneWidget);
    expect(find.byTooltip('Reports'), findsNothing);
  });

  testWidgets('a manager downloads a daily Excel report', (tester) async {
    final (server, files) = await start(tester, staffTokens('MANAGER'), routes: (s) {
      s.onFile('POST /reports/export/excel', utf8.encode('xlsx-bytes'), 'attendance-daily-2026-10-05.xlsx',
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    });
    await tester.tap(find.byTooltip('Reports'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('download')));
    await tester.pumpAndSettle();

    final request = server.requests.last;
    expect('${request.method} ${request.path}', 'POST /reports/export/excel');
    expect((request.data as Map)['report'], 'daily');
    expect((request.data as Map)['date'], isNotNull);
    expect(files.saved, [('attendance-daily-2026-10-05.xlsx', 10)]);
    expect(find.text('Saved to Downloads/Attendance: attendance-daily-2026-10-05.xlsx'), findsOneWidget);
    await tester.tap(find.text('OPEN'));
    await tester.pumpAndSettle();
    expect(files.opened, ['attendance-daily-2026-10-05.xlsx']);
  });

  testWidgets('a manager downloads a ready report', (tester) async {
    final (server, files) = await start(tester, staffTokens('MANAGER'), routes: (s) {
      s.onFile('GET /reports/ready/f1/download', [1, 2, 3], 'attendance-weekly-2026-09-28-to-2026-10-04.pdf',
          'application/pdf');
    });
    await tester.tap(find.byTooltip('Reports'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ready reports'));
    await tester.pumpAndSettle();
    expect(find.text('Weekly attendance report'), findsOneWidget);
    expect(find.textContaining('Your team · PDF · 30 KB'), findsOneWidget);
    await tester.tap(find.text('Weekly attendance report'));
    await tester.pumpAndSettle();
    expect(server.count('GET /reports/ready/f1/download'), 1);
    expect(files.saved.single.$1, 'attendance-weekly-2026-09-28-to-2026-10-04.pdf');
  });

  testWidgets('a server error during download is shown', (tester) async {
    await start(tester, staffTokens('HR'), routes: (s) {
      s.on('POST /reports/export/excel', 422, error('VALIDATION_ERROR', 'Choose at most 93 days.'));
    });
    await tester.tap(find.byTooltip('Reports'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('download')));
    await tester.pumpAndSettle();
    expect(find.text('Choose at most 93 days.'), findsOneWidget);
  });

  testWidgets('HR without an employee record opens straight into reports', (tester) async {
    await start(tester, staffTokens('HR', employee: false));
    expect(find.text('Create a report'), findsOneWidget);
    expect(find.byTooltip('Log out'), findsOneWidget);
  });

  testWidgets('older phones open the file straight away', (tester) async {
    final saver = FakeFileSaver(location: '');
    await start(tester, staffTokens('MANAGER'), saver: saver, routes: (s) {
      s.onFile('POST /reports/export/excel', [1], 'r.xlsx', 'application/vnd.ms-excel');
    });
    await tester.tap(find.byTooltip('Reports'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('download')));
    await tester.pumpAndSettle();
    expect(saver.opened, ['r.xlsx']);
  });
}
