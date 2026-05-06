import 'dart:io';
import 'package:firebase_core/firebase_core.dart';

class GalleryFirebaseConfig {
  static Future<FirebaseOptions?> load() async {
    // Попытка загрузить конфигурацию Firebase из переменных окружения
    final apiKey = Platform.environment['FIREBASE_API_KEY'];
    final appId = Platform.environment['FIREBASE_APP_ID'];
    final projectId = Platform.environment['FIREBASE_PROJECT_ID'];
    final messagingSenderId = Platform.environment['FIREBASE_MESSAGING_SENDER_ID'];
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

    // Попытка загрузить конфигурацию из .env файла
    final dotEnvPath = Platform.environment['HOME'] != null
        ? File('${Platform.environment['HOME']}/.env')
        : null;
    
    if (dotEnvPath != null && await dotEnvPath.exists()) {
      final content = await dotEnvPath.readAsString();
      final lines = content.split('
');
      Map<String, String> envMap = {};
      for (final line in lines) {
        final parts = line.split('=');
        if (parts.length == 2) {
          envMap[parts[0].trim()] = parts[1].trim();
        }
      }
      final apiKey = envMap['FIREBASE_API_KEY'];
      final appId = envMap['FIREBASE_APP_ID'];
      final projectId = envMap['FIREBASE_PROJECT_ID'];
      final messagingSenderId = envMap['FIREBASE_MESSAGING_SENDER_ID'];
      final measurementId = envMap['FIREBASE_MEASUREMENT_ID'];

      if (apiKey != null && appId != null && projectId != null && messagingSenderId != null && measurementId != null) {
        return FirebaseOptions(
          apiKey: apiKey,
          appId: appId,
          messagingSenderId: messagingSenderId,
          projectId: projectId,
          measurementId: measurementId,
        );
      }
    }

    // Если нет стандартных переменных, попробуем использовать NEJE_FIREBASE_ переменные
    final nejeProjectId = Platform.environment['NEJE_FIREBASE_PROJECT_ID'];
    final nejeStorageBucket = Platform.environment['NEJE_FIREBASE_STORAGE_BUCKET'];
    final nejeCredentials = Platform.environment['NEJE_FIREBASE_CREDENTIALS'];

    if (nejeProjectId != null && nejeStorageBucket != null && nejeCredentials != null) {
      // Здесь можно загрузить учетные данные из файла nejeCredentials
      // Для разработки возвращаем null, так как нужны реальные учетные данные
      // В реальном приложении здесь нужно загрузить учетные данные из файла
      return null; // Пока возвращаем null, так как нет реальных учетных данных
    }

    return null;
  }
}
