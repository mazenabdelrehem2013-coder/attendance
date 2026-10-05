import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

void main() {
  // retry: null -> failed requests are not retried automatically; the screens show a
  // "Try again" button instead (no surprise background calls on poor networks).
  runApp(ProviderScope(retry: (_, _) => null, child: const AttendanceApp()));
}
