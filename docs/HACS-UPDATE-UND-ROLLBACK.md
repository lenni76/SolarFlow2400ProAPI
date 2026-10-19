# Update und Rückkehr im produktiven Home Assistant

Die Veröffentlichung unterscheidet drei Stände:

| Version | Zweck |
|---|---|
| **1.2.0** | Unveränderter ursprünglicher Code, dauerhaft als Release erhalten. Direkt über die HACS-Versionsauswahl wieder installierbar. |
| **1.2.1** | Neues Update mit API-Korrekturen und den vier Verbesserungen. Freigabe erst nach erfolgreichen automatischen Prüfungen. |
| **1.2.2 – vorbereitet** | Anwendungscode der bisherigen 1.2.0 mit höherer Versionsnummer. Wird nur bei Bedarf als Rückroll-Update veröffentlicht; bis dahin kein neuer Release. |

Die ursprüngliche Referenz ist Commit
`59b8ee3aae43a28be15a12a5d813d4975a3d7c42`. Beim vorbereiteten Rückrollstand sind
alle elf Python-Anwendungsdateien bytegleich zu diesem Commit. Lediglich das
Versionsfeld im Manifest wird erhöht; generierte Python-Cachedateien werden
nicht übernommen. Ein Hash-Vergleich dokumentiert dies.

Die höhere Rückrollnummer ist absichtlich noch nicht veröffentlicht: Sonst würde
HACS sie sofort als neueres Update anbieten und das neue Verhalten wieder ersetzen.

## Vor dem Test

1. Unter **Einstellungen → System → Backups** ein vollständiges Backup einschließlich
   der Home-Assistant-Datenbank erstellen und dessen erfolgreichen Abschluss prüfen.
   Eine Kopie außerhalb der HA-VM vorhalten. Dies ist die Rückkehrmöglichkeit für
   Einstellungen und Daten; ein reiner Codewechsel genügt dafür nicht.
2. Falls HACS-Updates für diese Integration automatisch installiert werden, diese
   Automatisierung für den betreuten Test aussetzen. Erst kontrolliert aktualisieren.
3. Entitätsnamen/-IDs, die verwendete Ausgangsleistungsbegrenzung und die aktuell
   eingestellten 20 W Ziel-Netzbezug dokumentieren. Eigene zusätzliche Umrechnungen
   für Batteriespannung `totalVol`, Rohwert `hyperTmp` oder `batcur` berücksichtigen.
4. Die Änderungen und Bedienung in
   [VERBESSERUNGEN-UND-BEDIENUNG.md](../VERBESSERUNGEN-UND-BEDIENUNG.md) ansehen.
   Recovery für den ersten Test ausgeschaltet lassen.

## Neue Version installieren

1. In **HACS → SolarFlow2400-API → ⋮ → Informationen aktualisieren** den
   Repository-Stand neu einlesen. Dadurch wird noch kein Code installiert.
2. Über **Aktualisieren** oder **⋮ → Erneut herunterladen** den Versionsdialog
   öffnen. Unter **Andere Version benötigt?** beziehungsweise der entsprechenden
   englischen Beschriftung **v1.2.1** auswählen und herunterladen.
3. Home Assistant vollständig neu starten. Die Integration und ihre Geräte
   nicht löschen und nicht neu anlegen.
4. Version 1.2.1 unter **Einstellungen → Geräte & Dienste → SolarFlow2400-API**
   kontrollieren. Neue Fehlermeldungen unter **Einstellungen → System → Protokolle**
   prüfen und tatsächliche Netzleistung, Ziel-Netzbezug 20 W, Ausgangsleistung,
   Sollwert und Befehlsbestätigung gemeinsam beobachten.

## Sofort auf bisherigen Code zurück

1. In **HACS → SolarFlow2400-API → ⋮ → Erneut herunterladen** die Version
   **v1.2.0** auswählen und herunterladen.
2. Home Assistant vollständig neu starten und Version/Verhalten kontrollieren.
3. Während einer Fehlfunktion den separaten Regler bei Bedarf über seinen
   vorhandenen Schalter aussetzen, damit er keine weiteren Stellbefehle sendet.
   Das allein setzt einen bereits im Gerät gespeicherten Ausgangssollwert nicht
   automatisch zurück. Eine erfolgreiche Geräteabschaltung wird nicht unterstellt.
4. Neue Diagnose-Entitäten können nach Rückkehr zum alten Code ohne Daten bleiben.
   Die bestehenden Geräte und Entitäten deshalb nicht vorschnell löschen.

Alternativ können wir den vorbereiteten Stand **1.2.2** als reguläres neues Release
veröffentlichen. HACS bietet dann wieder ein normales Update an. Dies geschieht
erst auf deinen Auftrag nach dem Test, nicht automatisch bei einem Einzelbefund.

## Grenzen einer Code-Rückkehr

- Neue Messwerte von Batteriespannung/-strom und Gerätetemperatur haben teilweise
  eine korrigierte Skalierung. Bereits gespeicherte Zustände und Statistiken werden
  weder beim Update noch bei Rückkehr rückwirkend umgerechnet. Für eine vollständige
  Rückkehr zum Datenstand vor dem Test ist das Backup maßgeblich.
- Geräteeinstellungen und bereits an die SolarFlow gesendete Befehle sind nicht
  durch das Herunterladen älteren Codes rückgängig gemacht.
- Die ursprüngliche Version enthält wieder deren bekannte Fehler und künftig
  abgekündigte HA-Aufrufe. Sie ist ein Rückkehrstand für deine derzeitige Umgebung,
  keine dauerhaft gepflegte Alternative für spätere HA-Versionen.
- Automatische Tests einschließlich echtem HA können die Kombination aus deiner
  Hardware, Firmware, Zählerlatenz und produktiven Automationen nicht vollständig
  ersetzen. Eine fehlerfreie Produktion wird nicht garantiert.

Quellen:
[HACS-Versionsauswahl](https://www.hacs.xyz/docs/use/repositories/dashboard/#downloading-a-specific-version-of-a-repository),
[HA-Backups](https://www.home-assistant.io/common-tasks/os/#backups).
