import 'dart:io';
import 'package:firebase_core/firebase_core.dart';

class GalleryFirebaseConfig {
  static Future<FirebaseOptions?> load() async {
    // Попытка загрузить конфигурацию Firebase из переменных окружения
    final apiKey = Platform.environment['FIREBASE_API_KEY'];
    final appId = Platform.environment['FIREBASE_APP_ID'];
    final projectId = Platform.environment['FIREBASE_PROJECT_ID'];
    final messagingSenderId = Platform.environment['FIREBASE_MESSAGING_SENDER_ID'];
    final appId = Platform.environment['FIREBASE_APP_ID'];
    final measurementId = Platform.environment['FIREBASE_MEASUREMENT_ID'];

    if (apiKey != null && appId != null && projectId != null && messagingSenderId != null && measurementId != null) {
      return FirebaseOptions(
        apiKey: apiKey,
        appId: appId,
        messagingSenderId: messagingSenderId,
        projectId: projectId,
        measurementId: measurementId,
      );
    }

    // Если переменные окружения не установлены, возвращаем null
    return null;
  }
}
