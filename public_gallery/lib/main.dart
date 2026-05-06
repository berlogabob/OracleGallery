import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_web_plugins/url_strategy.dart';

import 'app.dart';
import 'firebase_config.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  setUrlStrategy(HashUrlStrategy());

  var firebaseReady = false;
  try {
    final firebaseOptions = await GalleryFirebaseConfig.load();
    if (firebaseOptions != null) {
      await Firebase.initializeApp(options: firebaseOptions);
      firebaseReady = true;
    }
  } catch (error, stackTrace) {
    debugPrint('Firebase initialization failed: $error\n$stackTrace');
  }

  runApp(OracleGalleryApp(firebaseReady: firebaseReady));
}
