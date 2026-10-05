import 'package:geolocator/geolocator.dart';

/// One GPS reading, taken at the moment of checking in or out. The app never tracks
/// location in the background.
class LocationReading {
  LocationReading({
    required this.latitude,
    required this.longitude,
    required this.accuracyM,
    required this.isMocked,
    required this.fixTime,
  });

  final double latitude;
  final double longitude;
  final double accuracyM;
  final bool isMocked; // Android's mock-location flag (fake-GPS apps)
  final DateTime fixTime; // when the reading was taken (phone clock)
}

enum LocationProblemKind { serviceOff, permissionDenied, permissionDeniedForever, unavailable }

class LocationProblem implements Exception {
  LocationProblem(this.kind);
  final LocationProblemKind kind;

  String get message => switch (kind) {
        LocationProblemKind.serviceOff => 'Location is turned off. Turn on Location in your phone settings and try again.',
        LocationProblemKind.permissionDenied =>
          'The app needs your location to check you in. It is only used at the moment you check in or out.',
        LocationProblemKind.permissionDeniedForever =>
          'Location permission is blocked. Open the app settings and allow Location, then try again.',
        LocationProblemKind.unavailable =>
          "We couldn't get your location. Move to an open area or near a window and try again.",
      };

  bool get canOpenSettings =>
      kind == LocationProblemKind.permissionDeniedForever || kind == LocationProblemKind.serviceOff;
}

abstract class LocationService {
  /// Location on and permission granted - asks for permission if needed. Throws [LocationProblem].
  Future<void> ensureReady();

  /// A NEW high-accuracy reading (never a cached one). Throws [LocationProblem].
  Future<LocationReading> currentReading();

  Future<void> openSettings(LocationProblemKind kind);
}

class GeolocatorLocationService implements LocationService {
  @override
  Future<void> ensureReady() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      throw LocationProblem(LocationProblemKind.serviceOff);
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.deniedForever) {
      throw LocationProblem(LocationProblemKind.permissionDeniedForever);
    }
    if (permission == LocationPermission.denied) {
      throw LocationProblem(LocationProblemKind.permissionDenied);
    }
  }

  @override
  Future<LocationReading> currentReading() async {
    try {
      final p = await Geolocator.getCurrentPosition(
        locationSettings: AndroidSettings(
          accuracy: LocationAccuracy.best,
          timeLimit: const Duration(seconds: 25),
        ),
      );
      return LocationReading(
        latitude: p.latitude,
        longitude: p.longitude,
        accuracyM: p.accuracy,
        isMocked: p.isMocked,
        fixTime: p.timestamp,
      );
    } on LocationServiceDisabledException {
      throw LocationProblem(LocationProblemKind.serviceOff);
    } on PermissionDeniedException {
      throw LocationProblem(LocationProblemKind.permissionDenied);
    } catch (_) {
      throw LocationProblem(LocationProblemKind.unavailable); // timeout, no GPS signal
    }
  }

  @override
  Future<void> openSettings(LocationProblemKind kind) async {
    if (kind == LocationProblemKind.serviceOff) {
      await Geolocator.openLocationSettings();
    } else {
      await Geolocator.openAppSettings();
    }
  }
}
