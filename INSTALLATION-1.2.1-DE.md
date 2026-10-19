**SolarFlow2400-API 1.2.1 – vorbereitetes Update für deine HACS-Installation**

Der gemeinsame lokale Stand enthält die API-Korrekturen, die beiden angekündigten
HA-Anpassungen und die vier anschließend beauftragten Verbesserungen. Basis ist
Version 1.2.0, Commit `59b8ee3aae43a28be15a12a5d813d4975a3d7c42`.
Mindestziel: Home Assistant Core 2026.10.2.

GitHub, dein HA und die SolarFlow sind unverändert. Es wurde nichts veröffentlicht.
Auf deinen Wunsch erfolgt derzeit kein Commit, Push, Pull Request, Tag oder Release.
Das Update kann daher noch nicht über HACS heruntergeladen werden.

Die Details stehen in [Umsetzung und Bedienung](VERBESSERUNGEN-UND-BEDIENUNG.md)
und [API-Abgleich](API-ABGLEICH-2026-10-19.md).

**Was beim späteren Update zu beachten ist**

- Geräte-Identifier, Entitäts-Unique-IDs und Auswahltexte bleiben erhalten. Die
  bestehende Integration und ihre beiden Geräte beibehalten.
- Ausgangs- und AC-Ladeleistung haben 1-W-Schritte; gemeldete Leistungsgrenzen
  werden in der Oberfläche berücksichtigt.
- Unterdrückung gleicher kürzlich bestätigter Sollwerte ist standardmäßig an und
  konfigurierbar; 0 W werden immer gesendet. Keine zusätzliche Mindestpause/Totzone.
- Endgültig unbestätigte Befehle lösen bei aktiver Prüfung jetzt einen HA-Fehler
  aus. Der separate Regler kann diesen Fehler dadurch tatsächlich verarbeiten.
- Recovery bleibt standardmäßig aus; bestehende Optionen bleiben erhalten. Wenn
  sie bereits eingeschaltet war, gelten die neuen Voraussetzungen. Für die erste
  Kontrolle ausgeschaltet lassen.
- Ziel-Netzbezug bleibt **20 W**, über die Visualisierung deines separaten Reglers
  veränderbar. Keine neue konkurrierende Zielwert-Einstellung ergänzt.
- `totalVol` liefert künftig den korrekten Spannungswert. Eigene zusätzliche
  /100-Umrechnungen beim Update entfernen. Historische Zustände/Statistiken werden
  nicht rückwirkend korrigiert. Auch aktivierte Rohwertverwendungen von `hyperTmp`
  und `batcur` anhand der neuen °C-/Stromwerte prüfen.
- Vier neue Hauptgeräte-Diagnosen sowie `packType` an der Batterie. Bei gleichem
  Bericht sind voraussichtlich 68 Hauptgeräte- und 10 Batterie-Entitäten vorhanden,
  einschließlich deaktivierter Entitäten. Gemeldete Felder bestimmen die genaue Zahl.

**Späterer Ablauf nach ausdrücklichem Veröffentlichungsauftrag**

1. Den dann aktuellen GitHub-Stand mit dem geprüften lokalen Stand abgleichen,
   die Änderungen veröffentlichen und eine passende Version bereitstellen.
2. In HA unter **Einstellungen → System → Backups** ein Backup erstellen.
3. In **HACS → SolarFlow2400-API** auf die veröffentlichte Version aktualisieren,
   sobald sie angeboten wird. Dialogbeschriftungen hängen von deiner HACS-Version ab.
4. Home Assistant vollständig neu starten. Keine Integration oder Geräte löschen.
5. Unter **Einstellungen → Geräte & Dienste → SolarFlow2400-API** Version,
   Geräte, Entitäts-IDs und Optionen kontrollieren. Recovery zunächst aus lassen.
6. In deiner Visualisierung Ziel-Netzbezug 20 W, tatsächliche Netzleistung,
   Ausgangsleistung, Leistungsbegrenzung, letzten Steuerbefehl und neue Zähler
   gemeinsam anzeigen. Anleitung im verlinkten Bedienungsdokument.
7. Unter **Einstellungen → System → Protokolle** auf neue Integrationsfehler achten.
   Einen ausgelösten Servicefehler von einem Gerätefehler unterscheiden.

**Prüfung**

68 isolierte Tests erfolgreich, darunter API-/HA-Kompatibilität, echter
anonymisierter Report, Befehlsfehler, Recovery-Abbrüche, Rückstellung, UI-Limits,
Übersetzungen und Optionen. Syntax und JSON gültig; vollständiger Integrations-
und Testcode besteht Ruff-Lint und Formatprüfung. Ein vollständiger HA-Test,
Hardwaretest, hassfest- oder HACS-Validator-Lauf wurde nicht durchgeführt.
Python 3.12.14 und aiohttp 3.14.5, HA-Dienste als Test-Doubles.

Der Patch enthält die Änderungen an bestehenden Dateien; das vollständige
Quellstand-ZIP enthält auch neue Tests und Dokumentation. ZIP-Dateien dienen
jetzt der Prüfung, nicht als Aufforderung zu einer manuellen Installation.

Quellen:
[HA-Gerätezuordnung](https://contributors.home-assistant.io/blog/2026/08/24/device-registry-follow-up-changes/),
[HA-Neuladeänderung](https://contributors.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods/),
[HACS-Veröffentlichung](https://www.hacs.xyz/docs/publish/integration/),
[HA-Backups](https://www.home-assistant.io/common-tasks/os/).
