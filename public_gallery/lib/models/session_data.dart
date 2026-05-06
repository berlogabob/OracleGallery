import 'package:cloud_firestore/cloud_firestore.dart';

class SessionData {
  final String? sessionId;
  final String? sessionUrl;
  final String? qrUrl;
  final String? qrImageUrl;
  final Map<String, String>? assetUrls;
  final Map<String, String>? assetPaths;
  final String? svgUrl;
  final String? receiptUrl;
  final String? status;
  final String? plotStatus;
  final String? markName;
  final String? oracleText;
  final List<String>? themes;
  final List<Map<String, Object?>>? measures;

  SessionData({
    this.sessionId,
    this.sessionUrl,
    this.qrUrl,
    this.qrImageUrl,
    this.assetUrls,
    this.assetPaths,
    this.svgUrl,
    this.receiptUrl,
    this.status,
    this.plotStatus,
    this.markName,
    this.oracleText,
    this.themes,
    this.measures,
  });

  factory SessionData.fromDocument(DocumentSnapshot doc) {
    final data = doc.data()!;
    return SessionData(
      sessionId: doc.id,
      sessionUrl: data['sessionUrl'] ?? data['qrUrl'],
      qrUrl: data['qrUrl'],
      qrImageUrl: data['qrImageUrl'],
      assetUrls: data['assetUrls'] as Map<String, String>?,
      assetPaths: data['assetPaths'] as Map<String, String>?,
      svgUrl: data['svgUrl'],
      receiptUrl: data['receiptUrl'],
      status: data['status'],
      plotStatus: data['plotStatus'],
      markName: data['markName'],
      oracleText: data['oracleText'],
      themes: (data['themes'] as List<dynamic>?)?.cast<String>(),
      measures: (data['measures'] as List<dynamic>?)?.cast<Map<String, Object?>>(),
    );
  }
}
