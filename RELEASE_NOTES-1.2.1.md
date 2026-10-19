**SolarFlow2400-API 1.2.1 – API-Korrekturen und robustere HA-Steuerung**

- Batteriestrom als vorzeichenbehafteten 16-Bit-Wert auswerten, Batteriespannung
  korrekt skalieren und Gerätetemperatur in °C umrechnen; API-Abgleich mit
  zenSDK/OpenAPI 1.0.2. Fehlende Batterie-Diagnosefelder und Discovery-Port ergänzt.
- Identische kürzlich bestätigte Sollwerte optional überspringen. Nullleistungs-
  befehle immer senden; keine zusätzliche Mindestpause oder Totzone.
- Endgültig unbestätigte Befehle als HA-Servicefehler zurückgeben und Diagnosen
  in allen erwarteten Fehlerfällen abschließen.
- Optionale Recovery mit geprüfter AC-Modus-Wiederherstellung auch bei Abbruch.
  Bleibt standardmäßig aus; nur für Ausgangsleistung über 0 W bei bestätigtem
  Entladebetrieb und gemeldeter Rückspeisesperre. Keine Nulleinspeisegarantie.
- Aktuellen Gerätezustand und historisches Befehlsresultat trennen; vier Zähler
  für API-Schreibversuche, vermiedene Doppelbefehle, Wiederholungen und Recovery.
- Deutsche/englische Entitätsnamen, smartMode-Erklärung, gemeldete Leistungsgrenzen
  und 1-W-Schritte für Ausgangs- und AC-Ladeleistung.
- Batterie-Zuordnung mit via_device_id und einzelner Reload bei IP-Änderung;
  vorbereitet für die angekündigten HA-Änderungen 2026.12 und 2027.8.

Bestehende Unique IDs, Auswahlwerte und SOC-Umrechnung bleiben erhalten.
Der separate Regler behält seinen in der Visualisierung veränderbaren Zielbezug
von aktuell 20 W. Es gibt keinen zweiten Zielwert in der API-Integration.
Alte falsch skalierte Spannungsverläufe werden nicht rückwirkend berichtigt;
eigene /100-Korrekturen müssen beim späteren Update entfernt werden.

Validierung: 68 isolierte Tests, Syntax-/JSON-Prüfung, vollständige Ruff-Lint- und
Formatprüfung. Kein vollständiger HA-/Hardwaretest, hassfest oder HACS-Validator.
HA- und Geräteeinstellungen wurden nicht verändert.

Freigabe dieses Releases erst nach erfolgreichem GitHub-Prüfworkflow. Für eine
bestehende HACS-Installation später über HACS aktualisieren und HA vollständig
neu starten. Bestehenden Integrationseintrag und Geräte beibehalten.

Die unveränderte Version v1.2.0 bleibt über HACS auswählbar. Ein Rückrollstand
1.2.2 mit dem ursprünglichen Anwendungscode ist vorbereitet und wird nur bei
Bedarf veröffentlicht. [Update und Rückkehr](docs/HACS-UPDATE-UND-ROLLBACK.md).
