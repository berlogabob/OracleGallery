import 'package:firebase_core/firebase_core.dart';

class GalleryFirebaseConfig {
  static Future<FirebaseOptions?> load() async {
    return const FirebaseOptions(
      apiKey: 'AIzaSyDqBzqcDefYypWiu6vC15WVQVlisgMypIg',
      authDomain: 'oraclegallery.firebaseapp.com',
      projectId: 'oraclegallery',
      storageBucket: 'oraclegallery.firebasestorage.app',
      messagingSenderId: '690305000229',
      appId: '1:690305000229:web:63d9d74d5030dbaefcf0cc',
      measurementId: 'G-2FXB448E74',
    );
  }
}
