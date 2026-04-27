import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:http/http.dart' as http;

class GalleryFirebaseConfig {
  static Future<FirebaseOptions?> load() async {
    final fromDefines = _fromDartDefines();
    if (fromDefines != null) {
      return fromDefines;
    }

    final uri = Uri.base.resolve('firebase-config.json');
    try {
      final response = await http.get(uri);
      if (response.statusCode != 200) {
        return null;
      }
      final payload = jsonDecode(response.body) as Map<String, dynamic>;
      return _fromJson(payload);
    } catch (_) {
      return null;
    }
  }

  static FirebaseOptions? _fromDartDefines() {
    const apiKey = String.fromEnvironment('FIREBASE_API_KEY');
    const appId = String.fromEnvironment('FIREBASE_APP_ID');
    const messagingSenderId = String.fromEnvironment(
      'FIREBASE_MESSAGING_SENDER_ID',
    );
    const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
    const authDomain = String.fromEnvironment('FIREBASE_AUTH_DOMAIN');
    const storageBucket = String.fromEnvironment('FIREBASE_STORAGE_BUCKET');
    const measurementId = String.fromEnvironment('FIREBASE_MEASUREMENT_ID');

    if (_isMissingOrPlaceholder(apiKey) ||
        _isMissingOrPlaceholder(appId) ||
        _isMissingOrPlaceholder(messagingSenderId) ||
        _isMissingOrPlaceholder(projectId) ||
        _isMissingOrPlaceholder(authDomain) ||
        _isMissingOrPlaceholder(storageBucket)) {
      return null;
    }

    return const FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: messagingSenderId,
      projectId: projectId,
      authDomain: authDomain,
      storageBucket: storageBucket,
      measurementId: measurementId,
    );
  }

  static FirebaseOptions? _fromJson(Map<String, dynamic> payload) {
    final apiKey = payload['apiKey'] as String? ?? '';
    final appId = payload['appId'] as String? ?? '';
    final messagingSenderId = payload['messagingSenderId'] as String? ?? '';
    final projectId = payload['projectId'] as String? ?? '';
    final authDomain = payload['authDomain'] as String? ?? '';
    final storageBucket = payload['storageBucket'] as String? ?? '';
    final measurementId = payload['measurementId'] as String? ?? '';

    if (_isMissingOrPlaceholder(apiKey) ||
        _isMissingOrPlaceholder(appId) ||
        _isMissingOrPlaceholder(messagingSenderId) ||
        _isMissingOrPlaceholder(projectId) ||
        _isMissingOrPlaceholder(authDomain) ||
        _isMissingOrPlaceholder(storageBucket)) {
      return null;
    }

    return FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: messagingSenderId,
      projectId: projectId,
      authDomain: authDomain,
      storageBucket: storageBucket,
      measurementId: measurementId,
    );
  }

  static bool _isMissingOrPlaceholder(String value) {
    return value.isEmpty || value.startsWith('YOUR_');
  }
}
