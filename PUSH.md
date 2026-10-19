# Veröffentlichung

Repository: https://github.com/lenni76/SolarFlow2400ProAPI

Der Workflow `validate-release.yml` prüft isolierte Tests, echten Home Assistant,
hassfest und HACS. Erst nach erfolgreicher Prüfung veröffentlicht er 1.2.1 am
exakt geprüften Commit. Der unveränderte Ausgangsstand 1.2.0 wird separat erhalten.
Tags und bestehende Releases werden nicht auf andere Commits verschoben.

Der vorbereitete Rückrollstand 1.2.2 enthält den Anwendungscode von 1.2.0. Er
wird erst bei Bedarf veröffentlicht. Details: [Update und Rückkehr](docs/HACS-UPDATE-UND-ROLLBACK.md).
