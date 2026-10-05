// Phase 17: screens the coverage report showed untested - the forced password change at first
// login, and "My attendance" (history).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_test.dart' as app;
import 'fake_server.dart';

Map<String, dynamic> dayJson(String date, String status, int minutes) => {
      'date': date,
      'location': 'Lagos Office',
      'first_check_in_at': '${date}T08:05:00Z',
      'last_check_out_at': '${date}T16:30:00Z',
      'worked_minutes': minutes,
      'arrival_status': status == 'LATE' ? 'LATE' : 'PRESENT',
      'departure_status': 'CHECKED_OUT',
      'day_status': status,
      'verification_status': 'VERIFIED',
      'sessions': [],
    };

void main() {
  group('first login: forced password change', () {
    Future<FakeServer> toPasswordScreen(WidgetTester tester, void Function(FakeServer) extra) async {
      final server = await app.startApp(tester, routes: (s) {
        s.on('POST /auth/login', 200, tokens(mustChange: true));
        app.homeRoutes(s);
        extra(s);
      });
      await app.logIn(tester, 'EMP-0101', 'Temp-Pass-123');
      expect(find.text('Temporary password'), findsOneWidget);
      return server;
    }

    Future<void> fill(WidgetTester tester, String current, String next, String repeat) async {
      final fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), current);
      await tester.enterText(fields.at(1), next);
      await tester.enterText(fields.at(2), repeat);
      await tester.tap(find.text('SAVE PASSWORD'));
      await tester.pumpAndSettle();
    }

    testWidgets('checks length, difference and repeat before sending', (tester) async {
      final server = await toPasswordScreen(tester, (_) {});
      await fill(tester, 'Temp-Pass-123', 'short', 'short');
      expect(find.text('At least 10 characters'), findsOneWidget);
      await fill(tester, 'Temp-Pass-123', 'Temp-Pass-123', 'Temp-Pass-123');
      expect(find.text('Must be different from the current password'), findsOneWidget);
      await fill(tester, 'Temp-Pass-123', 'My-Own-Password-9', 'My-Own-Password-8');
      expect(find.text('The passwords are not the same'), findsOneWidget);
      expect(server.count('POST /auth/change-password'), 0);
    });

    testWidgets('shows the server message for a wrong temporary password', (tester) async {
      await toPasswordScreen(tester, (s) => s.on('POST /auth/change-password', 400,
          error('WRONG_PASSWORD', 'Your current password is not correct.')));
      await fill(tester, 'Wrong-Temp-1', 'My-Own-Password-9', 'My-Own-Password-9');
      expect(find.text('Your current password is not correct.'), findsOneWidget);
    });

    testWidgets('a good new password opens the app', (tester) async {
      final server = await toPasswordScreen(tester, (s) => s.on('POST /auth/change-password', 200, tokens()));
      await fill(tester, 'Temp-Pass-123', 'My-Own-Password-9', 'My-Own-Password-9');
      expect(server.count('POST /auth/change-password'), 1);
      expect(find.text('Chinedu Eze'), findsWidgets); // the home screen with the profile
      expect(find.text('Temporary password'), findsNothing);
    });
  });

  group('My attendance', () {
    testWidgets('shows the month with a summary and each day', (tester) async {
      final server = await app.startApp(tester, routes: (s) {
        s.on('POST /auth/login', 200, tokens());
        app.homeRoutes(s);
        s.on('GET /attendance/history', 200, [
          dayJson('2026-10-05', 'PRESENT', 505),
          dayJson('2026-10-06', 'LATE', 400),
        ]);
      });
      await app.logIn(tester, 'EMP-0101', 'pw');
      await tester.tap(find.byTooltip('History'));
      await tester.pumpAndSettle();

      expect(find.text('My attendance'), findsOneWidget);
      expect(find.text('Mon 5 Oct'), findsOneWidget);
      expect(find.text('Tue 6 Oct'), findsOneWidget);
      expect(find.textContaining('Lagos Office'), findsNWidgets(2));
      final request = server.requests.lastWhere((r) => r.path == '/attendance/history');
      expect(request.queryParameters['from'], endsWith('-01'));

      await tester.tap(find.byTooltip('Previous month'));
      await tester.pumpAndSettle();
      expect(server.count('GET /attendance/history'), 2);
    });

    testWidgets('an empty month says so', (tester) async {
      await app.startApp(tester, routes: (s) {
        s.on('POST /auth/login', 200, tokens());
        app.homeRoutes(s);
        s.on('GET /attendance/history', 200, []);
      });
      await app.logIn(tester, 'EMP-0101', 'pw');
      await tester.tap(find.byTooltip('History'));
      await tester.pumpAndSettle();
      expect(find.text('No attendance recorded this month.'), findsOneWidget);
    });
  });
}
