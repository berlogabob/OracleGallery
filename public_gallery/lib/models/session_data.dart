import 'package:cloud_firestore/cloud_firestore.dart';

class SessionData {
  const SessionData({
    required this.sessionId,
    required this.createdAt,
    required this.status,
    required this.plotStatus,
    required this.markName,
    required this.oracleText,
    required this.themes,
    required this.measures,
    required this.svgUrl,
    required this.receiptUrl,
    required this.qrUrl,
    required this.sessionUrl,
    required this.qrImageUrl,
    required this.tarotUrl,
    required this.origin,
    required this.tags,
    required this.visibleInLibrary,
  });

  final String sessionId;
  final DateTime createdAt;
  final String status;
  final String plotStatus;
  final String markName;
  final String oracleText;
  final List<String> themes;
  final Map<String, double> measures;
  final String svgUrl;
  final String receiptUrl;
  final String qrUrl;
  final String sessionUrl;
  final String qrImageUrl;
  final String tarotUrl;
  final String origin;
  final List<String> tags;
  final bool visibleInLibrary;

  bool get isPublished => status == 'published';

  bool get isPublicInLibrary {
    final lowerTags = tags.map((tag) => tag.toLowerCase()).toSet();
    return visibleInLibrary && origin.toLowerCase() != 'test' && !lowerTags.contains('test');
  }

  factory SessionData.fromDoc(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data() ?? const <String, dynamic>{};
    final assetUrls = _stringMap(data['assetUrls']);
    final sessionUrl = _string(data['sessionUrl']).isNotEmpty
        ? _string(data['sessionUrl'])
        : _string(data['qrUrl']);
    final qrImageUrl = _string(data['qrImageUrl']).isNotEmpty
        ? _string(data['qrImageUrl'])
        : _string(assetUrls['qr']);
    return SessionData(
      sessionId: _string(data['sessionId']).isNotEmpty ? _string(data['sessionId']) : doc.id,
      createdAt: _dateTime(data['createdAt']),
      status: _string(data['status']).isNotEmpty ? _string(data['status']) : 'publishing',
      plotStatus: _string(data['plotStatus']).isNotEmpty ? _string(data['plotStatus']) : 'pending',
      markName: _firstNonEmpty([
        _string(data['markName']),
        _string(data['title']),
        doc.id.replaceAll('_', ' '),
      ]),
      oracleText: _firstNonEmpty([
        _string(data['oracleText']),
        _string(data['summary']),
        'The oracle has not spoken yet.',
      ]),
      themes: _stringList(data['themes']),
      measures: _measuresMap(data['measures']),
      svgUrl: _firstNonEmpty([_string(assetUrls['svg']), _string(data['svgUrl'])]),
      receiptUrl: _firstNonEmpty([_string(assetUrls['receipt']), _string(data['receiptUrl'])]),
      qrUrl: _string(data['qrUrl']).isNotEmpty ? _string(data['qrUrl']) : sessionUrl,
      sessionUrl: sessionUrl,
      qrImageUrl: qrImageUrl,
      tarotUrl: _firstNonEmpty([_string(assetUrls['tarot']), _string(data['tarotUrl'])]),
      origin: _string(data['origin']),
      tags: _stringList(data['tags']),
      visibleInLibrary: data['visibleInLibrary'] is bool ? data['visibleInLibrary'] as bool : true,
    );
  }
}

String _string(Object? value) => value == null ? '' : value.toString();

String _firstNonEmpty(List<String> values) {
  return values.firstWhere((value) => value.trim().isNotEmpty, orElse: () => '');
}

Map<String, dynamic> _stringMap(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return value.map((key, mapValue) => MapEntry(key.toString(), mapValue));
  }
  return const <String, dynamic>{};
}

List<String> _stringList(Object? value) {
  if (value is Iterable) {
    return value.map((item) => item.toString()).where((item) => item.trim().isNotEmpty).toList();
  }
  if (value is String && value.trim().isNotEmpty) {
    return value.split(',').map((item) => item.trim()).where((item) => item.isNotEmpty).toList();
  }
  return const <String>[];
}

Map<String, double> _measuresMap(Object? value) {
  if (value is! Map) {
    return const <String, double>{};
  }
  final result = <String, double>{};
  for (final entry in value.entries) {
    final raw = entry.value;
    final parsed = raw is num ? raw.toDouble() : double.tryParse(raw.toString());
    if (parsed != null) {
      result[entry.key.toString()] = parsed;
    }
  }
  return result;
}

DateTime _dateTime(Object? value) {
  if (value is Timestamp) {
    return value.toDate();
  }
  if (value is DateTime) {
    return value;
  }
  if (value is String) {
    return DateTime.tryParse(value) ?? DateTime.fromMillisecondsSinceEpoch(0);
  }
  return DateTime.fromMillisecondsSinceEpoch(0);
}
