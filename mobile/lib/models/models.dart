/// Plain data classes for what the API returns. Times arrive in UTC and are shown in the
/// phone's local time.
library;

DateTime? _time(dynamic v) => v == null ? null : DateTime.parse(v as String).toLocal();

class UserSummary {
  UserSummary({
    required this.id,
    required this.email,
    required this.role,
    required this.mustChangePassword,
    this.employeeCode,
    this.fullName,
  });

  factory UserSummary.fromJson(Map<String, dynamic> j) {
    final employee = j['employee'] as Map<String, dynamic>?;
    return UserSummary(
      id: j['id'] as String,
      email: j['email'] as String,
      role: j['role'] as String,
      mustChangePassword: j['must_change_password'] as bool,
      employeeCode: employee?['employee_code'] as String?,
      fullName: employee?['full_name'] as String?,
    );
  }

  final String id;
  final String email;
  final String role;
  final bool mustChangePassword;
  final String? employeeCode;
  final String? fullName;

  bool get isEmployee => employeeCode != null;

  /// Managers, HR and admins can download reports in the app.
  bool get canDownloadReports => const {'MANAGER', 'HR', 'ADMIN'}.contains(role);
}

class AssignedLocation {
  AssignedLocation({required this.id, required this.name, this.address});

  factory AssignedLocation.fromJson(Map<String, dynamic> j) => AssignedLocation(
        id: j['id'] as String,
        name: j['name'] as String,
        address: j['address'] as String?,
      );

  final String id;
  final String name;
  final String? address;
}

class Profile {
  Profile({
    required this.employeeCode,
    required this.fullName,
    required this.email,
    required this.locations,
    this.phone,
    this.department,
    this.manager,
    this.primaryLocationId,
  });

  factory Profile.fromJson(Map<String, dynamic> j) => Profile(
        employeeCode: j['employee_code'] as String,
        fullName: j['full_name'] as String,
        email: j['email'] as String,
        phone: j['phone'] as String?,
        department: j['department'] as String?,
        manager: j['manager'] as String?,
        primaryLocationId: j['primary_location_id'] as String?,
        locations: [
          for (final l in j['locations'] as List) AssignedLocation.fromJson(l as Map<String, dynamic>)
        ],
      );

  final String employeeCode;
  final String fullName;
  final String email;
  final String? phone;
  final String? department;
  final String? manager;
  final String? primaryLocationId;
  final List<AssignedLocation> locations;

  AssignedLocation? get primaryLocation {
    if (locations.isEmpty) return null;
    return locations.firstWhere((l) => l.id == primaryLocationId, orElse: () => locations.first);
  }
}

class WorkSession {
  WorkSession({
    required this.checkInAt,
    required this.workedMinutes,
    required this.status,
    required this.pendingReview,
    this.checkOutAt,
  });

  factory WorkSession.fromJson(Map<String, dynamic> j) => WorkSession(
        checkInAt: _time(j['check_in_at'])!,
        checkOutAt: _time(j['check_out_at']),
        workedMinutes: j['worked_minutes'] as int,
        status: j['status'] as String,
        pendingReview: j['pending_review'] as bool,
      );

  final DateTime checkInAt;
  final DateTime? checkOutAt;
  final int workedMinutes;
  final String status;
  final bool pendingReview;
}

class AttendanceDay {
  AttendanceDay({
    required this.date,
    required this.workedMinutes,
    required this.sessions,
    this.location,
    this.firstCheckInAt,
    this.lastCheckOutAt,
    this.arrivalStatus,
    this.departureStatus,
    this.dayStatus,
    this.verificationStatus,
  });

  factory AttendanceDay.fromJson(Map<String, dynamic> j) => AttendanceDay(
        date: DateTime.parse(j['date'] as String),
        location: j['location'] as String?,
        firstCheckInAt: _time(j['first_check_in_at']),
        lastCheckOutAt: _time(j['last_check_out_at']),
        workedMinutes: j['worked_minutes'] as int,
        arrivalStatus: j['arrival_status'] as String?,
        departureStatus: j['departure_status'] as String?,
        dayStatus: j['day_status'] as String?,
        verificationStatus: j['verification_status'] as String?,
        sessions: [
          for (final s in j['sessions'] as List) WorkSession.fromJson(s as Map<String, dynamic>)
        ],
      );

  final DateTime date;
  final String? location;
  final DateTime? firstCheckInAt;
  final DateTime? lastCheckOutAt;
  final int workedMinutes;
  final String? arrivalStatus;
  final String? departureStatus;
  final String? dayStatus;
  final String? verificationStatus;
  final List<WorkSession> sessions;
}

class Attempt {
  Attempt({required this.eventType, required this.time, required this.result, required this.message});

  factory Attempt.fromJson(Map<String, dynamic> j) => Attempt(
        eventType: j['event_type'] as String,
        time: _time(j['server_time'])!,
        result: j['result'] as String,
        message: j['message'] as String,
      );

  final String eventType;
  final DateTime time;
  final String result; // ACCEPTED / FLAGGED / REJECTED
  final String message;
}

class Today {
  Today({
    required this.date,
    required this.dayType,
    required this.state,
    required this.nextAction,
    required this.attempts,
    this.qrRequired = false,
    this.dayDescription,
    this.scheduledStart,
    this.scheduledEnd,
    this.attendance,
  });

  factory Today.fromJson(Map<String, dynamic> j) => Today(
        date: DateTime.parse(j['date'] as String),
        dayType: j['day_type'] as String,
        dayDescription: j['day_description'] as String?,
        scheduledStart: j['scheduled_start'] as String?,
        scheduledEnd: j['scheduled_end'] as String?,
        state: j['state'] as String,
        nextAction: j['next_action'] as String,
        qrRequired: j['qr_required'] as bool? ?? false,
        attendance: j['attendance'] == null
            ? null
            : AttendanceDay.fromJson(j['attendance'] as Map<String, dynamic>),
        attempts: [for (final a in j['attempts'] as List) Attempt.fromJson(a as Map<String, dynamic>)],
      );

  final DateTime date;
  final String dayType; // WORKING_DAY / NON_WORKING_DAY / HOLIDAY / ON_LEAVE
  final String? dayDescription;
  final String? scheduledStart; // "09:00:00"
  final String? scheduledEnd;
  final String state; // NOT_CHECKED_IN / CHECKED_IN / CHECKED_OUT
  final String nextAction; // CHECK_IN / CHECK_OUT
  final bool qrRequired; // an office QR code must be scanned
  final AttendanceDay? attendance;
  final List<Attempt> attempts;
}
