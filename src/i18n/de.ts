/**
 * German interface copy and the vocabulary that keeps it consistent.
 *
 * Clerks see the words in the left column. The engine-room terms in the right
 * column remain in code and technical documentation, never on a user screen:
 *
 * | Auf dem Bildschirm | Im Maschinenraum |
 * |---|---|
 * | Belegart | Dokumenttyp, Template, Vorlage |
 * | Arbeitsweise | Profil, Pipeline-Profil |
 * | Angabe | Feld |
 * | Beleg | Dokument |
 * | sicher erkannt | Konfidenz ≥ Schwellwert |
 * | nicht eindeutig | Konfidenz unter Schwellwert |
 * | wartet auf Prüfung | Review-Queue |
 * | abgelegt | exportiert |
 * | Alle Belege bleiben auf diesem Gerät | Air-Gap-Modus |
 *
 * Model names, reading stages, numeric confidence, `snake_case`, JSON keys,
 * locators, provenance, bounding boxes and OCR are reserved for
 * “Einstellungen → Technische Details”. Error copy is resolved through the
 * stable RFC 9457 `key`, so sidecar wording cannot leak into the interface.
 */

// Small counts are written as words, as in the approved concept.
const COUNT_DE: Record<number, string> = {
  2: 'Zwei', 3: 'Drei', 4: 'Vier', 5: 'Fünf', 6: 'Sechs',
}

export const de = {
  app: {
    title: 'Substrakt',
    version: 'Version',
    promise: 'Alle Belege bleiben auf diesem Gerät.',
  },

  places: {
    overview: 'Übersicht',
    review: 'Prüfen',
    templates: 'Belegarten',
    settings: 'Einstellungen',
  },

  theme: {
    toggle: 'Hell oder dunkel',
  },

  keys: {
    enter: 'Enter',
  },

  time: {
    justNow: 'gerade eben',
    minuteAgo: 'vor einer Minute',
    minutesAgo: (minutes: number) => `vor ${minutes} Minuten`,
    hourAgo: 'vor einer Stunde',
    hoursAgo: (hours: number) => `vor ${hours} Stunden`,
    yesterday: 'gestern',
    daysAgo: (days: number) => `vor ${days} Tagen`,
  },

  state: {
    running: 'Alles läuft',
    starting: 'Substrakt startet',
    startingDetail: 'Einen Augenblick — das Lesewerk wird bereitgemacht.',
    unavailable: 'Substrakt läuft nicht',
    unavailableDetail: 'Bitte starten Sie die Anwendung neu.',
    ready: (templates: number) =>
      templates === 1
        ? '1 Vorlage eingerichtet'
        : `${templates} Vorlagen eingerichtet`,
    noTemplates: 'Noch keine Vorlage eingerichtet',
  },

  overview: {
    lastRead: 'zuletzt gelesen',
    reviewNow: 'Jetzt prüfen',
  },

  review: {
    empty: 'Nichts zu prüfen',
    emptyDetail: 'Alle gelesenen Angaben waren eindeutig.',
    documentOf: (n: number, total: number) => `Beleg ${n} von ${total}`,
    readAt: (time: string) => `${time} Uhr gelesen`,
    unclear: 'Eine Angabe ist nicht eindeutig',
    looksRight: 'Stimmt so',
    change: 'Ändern',
    accept: 'Übernehmen',
    discard: 'Verwerfen',
    isMissing: 'Diese Angabe fehlt im Beleg',
    rest: 'Alles Übrige wurde sicher erkannt',
    noMore: 'Weitere Angaben gibt es in dieser Vorlage nicht.',
    none: 'nichts gefunden',
    appliesHere:
      'Was Sie hier eintragen, gilt nur für diesen Beleg, nicht für die Belegart.',
    reason: {
      noValue:
        'An der markierten Stelle stand nichts Lesbares. Tragen Sie den Wert ein oder halten Sie fest, dass er im Beleg fehlt.',
      noEvidence:
        'Der Wert wurde gefunden, aber keine Stelle im Beleg dazu. Ohne Fundstelle lässt er sich nicht nachprüfen.',
      uncertain: 'Die Stelle im Beleg weicht von der gewohnten ab. Die Markierung sehen Sie links.',
      type: 'Der gefundene Wert passt nicht zu dem, was hier stehen sollte.',
      weak:
        'Die Schrift an dieser Stelle war schlecht lesbar. Bitte gleichen Sie den Wert mit dem Beleg ab.',
    },
  },

  // Review of an entry from the watched folder (broker pilot).
  inboxReview: {
    documentOf: (n: number, total: number, customer: string | null) =>
      `Beleg ${n} von ${total}` + (customer ? ` · Kunde ${customer}` : ''),
    recognisedAs: 'Erkannt als',
    unclear: (n: number) => (n === 1 ? 'Eine Angabe ist nicht eindeutig' : `${COUNT_DE[n] ?? n} Angaben sind nicht eindeutig`),
    questionFor: (label: string) => `Stimmt die Angabe „${label}“?`,
    reason: {
      noValue: 'Im Beleg wurde dazu nichts gefunden. Tragen Sie ein, was dort steht.',
      unclear:
        'Der gelesene Wert ist nicht eindeutig. Links ist markiert, wo er gelesen wurde.',
      noLocation: 'Der Wert wurde gelesen, aber keine Stelle im Beleg dazu.',
      unclearUnmarked: 'Der gelesene Wert ist nicht eindeutig.',
    },
    rest: 'Weitere Angaben',
    clickShows: 'Ein Klick auf eine Angabe zeigt ihre Stelle im Beleg und öffnet sie zum Ändern.',
    noPlace: 'Für diese Angabe gibt es keine Stelle im Beleg.',
    dateForm: 'TT.MM.JJJJ',
    dateHint: 'Bitte als TT.MM.JJJJ eingeben, zum Beispiel 01.04.2025. Dieses Datum gibt es nicht oder es ist unvollständig.',
    numberHint: 'Das ist kein Betrag. Bitte als Zahl eingeben, zum Beispiel 250,94.',
    typeHint: 'Diese Eingabe passt nicht zu der Angabe. Bitte prüfen Sie sie.',
    settled: 'Alle Angaben sind geklärt',
    settledDetail:
      'Ein Klick auf eine Angabe zeigt ihre Stelle im Beleg und öffnet sie; was nicht stimmt, ändern Sie vor der Freigabe.',
    boldChanged: 'Fett: von Ihnen geändert.',
    approve: 'Beleg freigeben',
    changeValue: (label: string) => `${label} ändern`,
    approveMeans:
      'Freigegeben heißt: bereit zur Übergabe. Geschrieben wird erst, wenn Sie die Übergabe gesehen und bestätigt haben.',
    later: 'Später entscheiden',
    missing: 'fehlt im Beleg',
    settledMark: 'geklärt',
    waitingMark: 'wartet auf Sie',
    noKindQuestion: 'Als was soll dieser Beleg gelesen werden?',
    noDocument: 'Der Beleg lässt sich hier nicht anzeigen.',
    firstRead: 'Zuerst gelesen',
    nowRead: 'Jetzt gelesen',
    sameQuestion: 'Ist das derselbe Beleg?',
    sameDetail: (count: number) =>
      `${count === 1 ? 'Eine Angabe stimmt' : `${COUNT_DE[count] ?? count} Angaben stimmen`} mit einem schon gelesenen Beleg überein. Die Datei selbst ist eine andere – zum Beispiel ein zweiter Scan. Das entscheiden Sie, nicht das Programm.`,
    same: 'Derselbe Beleg',
    sameMeans: 'Er wird nicht noch einmal übergeben.',
    different: 'Ein neuer Beleg',
    differentMeans: 'Er wird wie jeder andere geprüft und freigegeben.',
    emptyDetail: 'Alle gelesenen Belege sind freigegeben oder entschieden.',
    emptyCard: 'Was freigegeben ist, steht in der Übersicht',
    emptyCardDetail: (target: string) => `Dort sehen Sie auch, was an ${target} übergeben würde.`,
    toOverview: 'Zur Übersicht',
    identical: 'Derselbe Inhalt',
    identicalDetail:
      'Diese Datei ist genau gleich wie der zuerst gelesene Beleg und wird weder gelesen noch übergeben.',
    chooseKindDetail: 'Die Belegart wurde nicht sicher erkannt.',
    readWith: 'Damit lesen',
    approveAfter: (n: number) => (n === 1 ? 'Freigeben geht, wenn noch eine Angabe bestätigt oder korrigiert ist.' : `Freigeben geht, wenn noch ${COUNT_DE[n]?.toLowerCase() ?? n} Angaben bestätigt oder korrigiert sind.`),
    refused: {
      'entry-changed':
        'Der Beleg wurde inzwischen an anderer Stelle geändert. Sie sehen jetzt den neuen Stand; Ihre Eingabe bleibt erhalten.',
      'entry-not-waiting':
        'Dieser Beleg wartet nicht mehr auf Prüfung. Er wurde inzwischen freigegeben oder entschieden.',
      'kind-not-in-profile': 'Diese Belegart passt nicht zu diesem Ordner.',
      'value-unknown': 'Diese Angabe gehört nicht zu dieser Belegart.',
      'value-empty': 'Eine leere Angabe kann nicht übernommen werden.',
      'values-not-settled': 'Eine benötigte Angabe fehlt noch oder ist nicht eindeutig.',
      'kind-missing': 'Wählen Sie zuerst, als was der Beleg gelesen werden soll.',
      'possible-duplicate-undecided': 'Entscheiden Sie zuerst, ob das derselbe Beleg ist.',
      'no-possible-duplicate': 'Dieser Beleg ist inzwischen schon entschieden.',
      'hand-over-not-possible': 'Dieser Beleg kann so nicht übergeben werden.',
    } as Record<string, string>,
  },

  templates: {
    title: 'Vorlagen',
    subtitle:
      'Eine Vorlage sagt dem Programm, wo in einem Beleg welche Angabe steht — und was damit geschehen soll.',
    newLabel: 'Neue Vorlage',
    search: 'Vorlage suchen',
    count: (n: number) => (n === 1 ? '1 Vorlage' : `${n} Vorlagen`),
    lastUsed: 'Zuletzt verwendet',
    all: 'Alle Vorlagen · A–Z',
    none: 'Noch keine Vorlage',
    noneDetail:
      'Öffnen Sie einen typischen Beleg, ziehen Sie Rahmen um die Stellen, die Sie brauchen — den Rest erledigt die Vorlage.',
    nothingFound: 'Keine Vorlage passt zu dieser Suche.',
    values: (n: number) => (n === 1 ? '1 Angabe' : `${n} Angaben`),
    changed: 'zuletzt geändert',
    readDocument: 'Beleg mit dieser Vorlage lesen',
    changeValues: 'Angaben ändern',
    delete: 'Vorlage löschen',
    deleteQuestion: (name: string) =>
      `Die Vorlage „${name}“ wird mit allen Angaben gelöscht. Das lässt sich nicht rückgängig machen.`,
    confirmDelete: 'Endgültig löschen',
    cancel: 'Abbrechen',
    reading: 'Beleg wird gelesen …',
  },

  kinds: {
    title: 'Belegarten',
    listSubtitle: 'Diese Belegarten liest das Programm im überwachten Ordner.',
    none: 'Noch keine Belegart',
    noneDetail: 'In den Einstellungen wählen Sie, was eingelesen wird. Dann stehen hier die Belegarten dazu.',
    toSettings: 'Einstellungen öffnen',
    toOverview: 'Zur Übersicht',
    values: (n: number) => (n === 1 ? '1 Angabe' : `${n} Angaben`),
    back: 'Belegarten',
    leaveQuestion: 'Ihre Änderungen sind noch nicht gespeichert. Verwerfen?',
    discard: 'Verwerfen',
    keepEditing: 'Weiter bearbeiten',
    kindTitle: (kind: string) => `Das wird aus „${kind}“ gelesen`,
    subtitle:
      'Was Sie hier umbenennen, entfernen oder hinzufügen, gilt ab dem nächsten gelesenen Beleg.',
    goesTo: (target: string) => `geht an ${target}`,
    onlyShown: 'nur zur Ansicht',
    remove: 'Entfernen',
    restore: 'Zurückholen',
    warning: (target: string) => `${target} erhält diese Angabe dann nicht mehr.`,
    newPlaceholder: 'Neue Angabe, zum Beispiel Selbstbeteiligung',
    newHint: 'so, wie es im Beleg steht',
    add: 'Hinzufügen',
    renameHint: 'Zum Umbenennen schreiben Sie einfach in die Zeile.',
    save: 'Änderungen speichern',
    saved: 'Gespeichert. Bereits gelesene Belege bleiben, wie sie sind.',
    refused: {
      'no-value-left': 'Eine Belegart braucht mindestens eine Angabe.',
      'label-empty': 'Jede Angabe braucht einen Namen.',
      'label-twice': 'Zwei Angaben heißen gleich. Bitte geben Sie jeder einen eigenen Namen.',
      'value-unknown': 'Die Angaben haben sich inzwischen geändert. Bitte öffnen Sie die Belegart neu.',
      'target-needs-a-value': 'Das Zielprogramm braucht mindestens eine dieser Angaben.',
      invalid: 'So kann die Belegart nicht gespeichert werden.',
    } as Record<string, string>,
  },

  assistant: {
    title: 'Neue Vorlage einrichten',
    editTitle: 'Vorlage ändern',
    backToTemplates: 'Vorlagen',
    steps: {
      document: 'Musterbeleg',
      values: 'Angaben markieren',
      result: 'Ergebnis',
      finish: 'Abschluss',
    },
    nextStep: 'Weiter',
    back: 'Zurück',

    document: {
      title: 'Ziehen Sie einen typischen Beleg hierher',
      subtitle:
        'Eine Rechnung, ein Lieferschein, eine Tabelle — irgendein Beispiel dieser Art. PDF, Foto, Scan oder Tabelle. Der Beleg bleibt auf diesem Gerät.',
      choose: 'Beleg auswählen',
      notice:
        'Sie richten das einmal ein. Jeden weiteren Beleg derselben Art lesen Sie danach mit einem Handgriff.',
      loaded: 'Dieser Beleg dient als Muster',
      other: 'Anderen Beleg wählen',
    },

    values: {
      title: 'Diese Angaben will ich haben',
      question: 'Was steht an dieser Stelle?',
      placeholder: 'z. B. Rechnungsnummer',
      accept: 'Übernehmen',
      cancel: 'Abbrechen',
      suggestions: ['Rechnungsnummer', 'Datum', 'Betrag', 'Absender', 'IBAN'],
      notice:
        'Ziehen Sie mit der Maus einen Rahmen um die Stelle im Beleg und sagen Sie, was dort steht. Mehr ist nicht nötig.',
      empty: 'Noch keine Angabe markiert.',
      marked: (n: number) =>
        n === 1 ? '1 Angabe markiert' : `${n} Angaben markiert`,
      notFound: 'an dieser Stelle steht nichts Lesbares',
      remove: 'Angabe entfernen',
      waiting: 'Ziehen Sie jetzt einen Rahmen im Beleg',
    },

    result: {
      title: 'Was soll aus jedem Beleg werden?',
      table: 'Eine Tabelle',
      tableDetail: 'Jeder Beleg wird eine Zeile. Zum Öffnen, Sortieren und Weitergeben.',
      file: 'Eine Datei je Beleg',
      fileDetail: 'Wenn ein anderes Programm die Daten einliest.',
      custom: 'Eigenes Format',
      customDetail: 'Nach Vorgabe Ihrer IT. Kommt in einer späteren Ausbaustufe.',
      preview: 'So sieht das Ergebnis aus',
      keyName: 'Namen im Ergebnis',
      keyDetail:
        'So heißen die Angaben in der Datei, die andere Programme einlesen. Der Vorschlag entsteht aus dem Klarnamen; ändern Sie ihn, wenn Ihre IT eine bestimmte Schreibweise verlangt.',
      keyError:
        'Erlaubt sind Buchstaben, Ziffern und Unterstriche; das erste Zeichen darf keine Ziffer sein.',
      duplicateKey: 'Diesen Namen trägt bereits eine andere Angabe.',
    },

    finish: {
      name: 'Name der Vorlage',
      namePlaceholder: 'z. B. Rechnung — Nordwind Maschinenbau',
      nameMissing: 'Geben Sie der Vorlage einen Namen.',
      summary: {
        template: 'Vorlage',
        values: 'Angaben',
        result: 'Ergebnis',
        unclear: 'Unklare Belege',
        unclearValue: 'kommen in die Prüfliste',
        unclearDetail: 'Der Rest läuft weiter durch.',
      },
      promise:
        'Beleg, Vorlage und Ergebnis bleiben auf diesem Gerät. Es besteht keine Verbindung nach außen.',
      save: 'Vorlage speichern',
      running: 'Wird gespeichert …',
    },
  },

  settings: {
    title: 'Einstellungen',
    appearance: 'Erscheinungsbild',
    light: 'Hell',
    dark: 'Dunkel',
    lightDetail: 'Die Voreinstellung. Ruhiges Papiergrau.',
    darkDetail: 'Gleichwertig gepflegt, für dunkle Räume.',
    language: 'Sprache',
    german: 'Deutsch',
    germanCode: 'DE',
    germanDetail: 'Die Voreinstellung.',
    english: 'Englisch',
    englishCode: 'EN',
    englishDetail: 'Die englische Oberfläche.',
    privacy: 'Datenschutz und Technik',
    noConnection: 'Es besteht keine Verbindung nach außen',
    noConnectionDetail:
      'Belege, Angaben und Ergebnisse verlassen dieses Gerät nicht. Es gibt keinen Netzwerkzugang, der sich einschalten ließe.',
    technical: 'Technische Details',
    technicalDetail:
      'Ab hier stehen die Begriffe des Maschinenraums. Sie sind für die IT gedacht, nicht für den Arbeitsalltag.',
    textRecognition: 'Texterkennung',
    localEngine: 'lokal · Tesseract',
    storageLocation: 'Speicherort',
    thisDevice: 'dieses Gerät',
  },

  document: {
    state: {
      filed: 'abgelegt',
      read: 'gelesen',
      waiting: 'wartet auf Prüfung',
    },
    saveResult: 'Ergebnis sichern',
    loading: 'Beleg wird gelesen …',
    formats: 'PDF, Tabellen und Bilder',
  },

  viewer: {
    page: 'Seite',
    of: 'von',
    previous: 'Vorherige Seite',
    next: 'Nächste Seite',
    zoomOut: 'Verkleinern',
    zoomIn: 'Vergrößern',
    resetZoom: 'Ansicht zurücksetzen',
    rotate: 'Seite drehen',
    sheet: 'Blatt',
  },

  highlight: {
    newLabel: 'Rahmen aufziehen',
    delete: 'Markierung entfernen',
    none: 'Noch nichts markiert',
    count: (n: number) => (n === 1 ? '1 Markierung' : `${n} Markierungen`),
  },

  info: {
    pages: 'Seiten',
    mode: 'Betriebsart',
    sidecar: 'Backend',
  },

  mode: {
    airgap: 'Air-Gap — keine ausgehenden Verbindungen',
    onprem: 'On-Premise',
    cloud: 'Cloud freigeschaltet',
  },

  // Overview of the broker pilot: the watched folder and its imports.
  pilotOverview: {
    startTitle: 'Noch wurde nichts eingelesen',
    startSubtitle:
      'Das Programm liest alles im gewählten Ordner von selbst.',
    startCard: 'Ein Ordner, darin ein Unterordner je Kunde',
    startCardDetail:
      'Mehr braucht es nicht. Später hinzugelegte Belege liest das Programm nach, solange es geöffnet ist.',
    chooseFolder: 'Ordner einlesen',
    readingTitle: (read: number) =>
      read === 1 ? 'Es wird gelesen: 1 Beleg bisher' : `Es wird gelesen: ${read} Belege bisher`,
    readingSubtitle:
      'Sie können sofort prüfen, was unten schon gelesen ist.',
    waitingTitle: (waiting: number) =>
      waiting === 1
        ? '1 Beleg wartet auf Ihre Freigabe'
        : `${waiting} Belege warten auf Ihre Freigabe`,
    waitingSubtitle:
      'Nichts wird übergeben, bevor Sie es gesehen und freigegeben haben.',
    readyTitle: 'Alles geprüft – bereit zur Übergabe',
    readySubtitle: (approved: number) =>
      approved === 1 ? 'Ein Beleg ist freigegeben.' : `${approved} Belege sind freigegeben.`,
    quietTitle: 'Nichts zu tun',
    quietSubtitle: 'Neue Belege im Ordner erscheinen hier von selbst.',
    watching: 'Der Ordner wird überwacht, solange das Programm geöffnet ist.',
    notWatching: 'Der Ordner wird gerade nicht überwacht.',
    withErrors: (count: number) => (count === 1 ? '1 Beleg mit Fehler' : `${count} Belege mit Fehler`),
    errorsTitle: 'Nicht alles konnte gelesen werden',
    errorsSubtitle: 'Die Belege mit Fehler stehen unten, mit dem Grund.',
    showErrors: 'Fehler zeigen',
    imported: 'Eingelesen',
    importOf: (date: string, time: string) => `Einlesen vom ${date}, ${time} Uhr`,
    customersAndDocuments: (customers: number, documents: number) =>
      `${customers === 1 ? '1 Kunde' : `${customers} Kunden`} · ${documents === 1 ? '1 Beleg' : `${documents} Belege`}`,
    laterArrivals: (count: number) => `${count} später hinzugekommen`,
    duplicates: (count: number) => `${count} doppelt`,
    possibleDuplicates: (count: number) => `${count} möglicherweise doppelt`,
    beingRead: (count: number) => `${count} werden gerade gelesen`,
    allStates: 'Alle Zustände',
    period: 'Zeitraum',
    periods: {
      latest: 'Zuletzt eingelesen',
      days3: '3 Tage',
      week: 'Eine Woche',
      month: 'Ein Monat',
      months3: '3 Monate',
    },
    showAll: (count: number) => `Alle ${count} Belege zeigen`,
    state: 'Zustand',
    search: 'Suchen nach Datei, Versicherer oder Nummer',
    searchLabel: 'Suchen',
    hits: (hits: number, all: number) => `${hits} von ${all} Belegen`,
    resetFilter: 'Filter zurücksetzen',
    noMatch: 'Kein Beleg passt zu diesem Filter.',
    file: 'Datei',
    recognisedAs: 'Erkannt als',
    noCustomer: 'ohne Kunde',
    documents: (count: number) => (count === 1 ? '1 Beleg' : `${count} Belege`),
    notRead: 'nicht gelesen',
    notRecognised: 'nicht erkannt',
    sameContentAs: (file: string) => `derselbe Inhalt wie „${file}“`,
    compare: 'vergleichen',
    states: {
      reading: 'wird gelesen …',
      waiting: 'wartet auf Prüfung',
      ready: 'bereit zur Übergabe',
      filed: 'abgelegt',
      possible: 'möglicherweise doppelt',
      error: 'Fehler',
      duplicate: 'doppelt',
    },
    unclear: 'nicht eindeutig',
    laterArrival: 'später hinzugekommen',
    unclearValues: (count: number) =>
      count === 1 ? '1 Angabe nicht eindeutig' : `${count} Angaben nicht eindeutig`,
    certain: 'sicher erkannt',
    approvedState: 'freigegeben',
    manual: 'Von Hand gelesen',
    showHandOver: 'Übergabe ansehen',
    handedOverTitle: (customers: number, target: string) =>
      customers === 1
        ? `1 Übergabe liegt für ${target} bereit`
        : `${customers} Übergaben liegen für ${target} bereit`,
    handedOverSubtitle: (target: string) =>
      `Lesen Sie die Dateien in ${target} ein und halten Sie danach hier fest, ob es geklappt hat.`,
    giveFeedback: 'Rückmeldung geben',
    resultTitle: (done: number, failed: number) =>
      `${done === 1 ? '1 Übergabe' : `${done} Übergaben`} erledigt, ${failed} fehlgeschlagen`,
    resultSubtitle:
      'Eine fehlgeschlagene Übergabe bleibt liegen, bis Sie sie erneut freigeben.',
    releaseFailed: 'Fehlgeschlagene Übergabe erneut freigeben',
    handedOverGroup: 'übergeben · Rückmeldung offen',
    handedOverRow: 'übergeben',
    done: 'erledigt',
    importFailed: 'fehlgeschlagen',
    failedBecause: (reason: string) => `fehlgeschlagen · ${reason}`,
  },

  // Before and after a hand-over: what it would write, and what importing it did.
  handOver: {
    title: (target: string) => `Das würde an ${target} übergeben`,
    subtitle:
      'Noch ist nichts geschrieben: Hier steht Angabe für Angabe, was für welchen Kunden und Vertrag ankäme und aus welchem Beleg es stammt.',
    preparing: 'Es wird zusammengestellt, was übergeben würde …',
    nothingTitle: 'Nichts liegt zur Übergabe bereit',
    nothingDetail: 'Sobald Sie einen Beleg eines Kunden freigeben, steht er hier.',
    contractsFrom: (contracts: number, documents: number) =>
      `${contracts === 1 ? '1 Vertrag' : `${contracts} Verträge`} aus ${documents === 1 ? '1 Beleg' : `${documents} Belegen`}`,
    notYet: 'wird noch nicht übergeben',
    source: (kind: string, page: number) => `${kind}, Seite ${page}`,
    changed: 'von Ihnen geändert',
    aValue: 'eine Angabe',
    missing: (label: string) => `Für die Übergabe fehlt die Angabe „${label}“.`,
    unknownInsurer: (value: string, target: string) =>
      `Für ${value ? `„${value}“` : 'den Versicherer'} ist nicht hinterlegt, unter welchem Namen ${target} diesen Versicherer führt. Der Vertrag bleibt liegen, bis das eingetragen ist. Geraten wird nichts.`,
    unknownLine: (value: string, target: string) =>
      `Für ${value ? `die Sparte „${value}“` : 'diese Sparte'} ist nicht hinterlegt, wie ${target} sie führt. Der Vertrag bleibt liegen, bis das eingetragen ist. Geraten wird nichts.`,
    unknownPaymentMode: (value: string, target: string) =>
      `Für ${value ? `die Zahlweise „${value}“` : 'diese Zahlweise'} ist nicht hinterlegt, wie ${target} sie führt. Der Vertrag bleibt liegen, bis das eingetragen ist. Geraten wird nichts.`,
    annualOnly:
      'Bekannt ist nur der Jahresbeitrag, übergeben wird der Beitrag je Zahlung. Bei Ratenzahlung lässt er sich nicht ausrechnen; bitte tragen Sie ihn im Beleg nach.',
    doesNotFit: (label: string) =>
      `Die Angabe „${label}“ passt nicht in die Übergabe. Gekürzt wird nichts; bitte prüfen Sie sie im Beleg.`,
    twoPolicies:
      'Zwei Policen tragen dieselbe Versicherungsscheinnummer. Bitte prüfen Sie, welche Nummer stimmt.',
    twoHolders:
      'Die Belege dieses Vertrags nennen verschiedene Versicherungsnehmer. Bitte prüfen Sie, welcher stimmt.',
    kindNotHandedOver: (kind: string, target: string) =>
      `${kind} wird noch nicht übergeben – tragen Sie die Änderung bitte von Hand in ${target} ein.`,
    cannotWrite: 'Dieser Beleg kann so nicht übergeben werden.',
    problems: {
      'hand-over-settings-invalid':
        'Die Übergabe ist für diese Arbeitsweise noch nicht vollständig beschrieben. Bis das nachgetragen ist, wird für diesen Kunden nichts geschrieben.',
      'hand-over-table-invalid':
        'Eine Zuordnungstabelle für die Übergabe ist fehlerhaft. Bis sie berichtigt ist, wird für diesen Kunden nichts geschrieben.',
      'hand-over-without-customer': 'Ohne Kunde wird nichts übergeben.',
      'hand-over-folder-missing':
        'Im gewählten Ordner fehlt der Unterordner „Ausgabe“. Wählen Sie den Ordner unter Einstellungen noch einmal, dann wird er angelegt.',
      'hand-over-name-taken':
        'Im Ordner „Ausgabe“ liegt schon eine fremde Datei mit dem Namen dieser Übergabe. Sie bleibt unverändert; bitte benennen Sie sie um und geben Sie den Beleg wieder frei.',
    },
    fileIn: 'Es entsteht eine Datei je Kunde im Ordner',
    importYourself: (target: string) => `Das Einlesen in ${target} machen Sie selbst.`,
    write: 'Übergabe schreiben',
    feedbackTitle: (target: string) => `Sind die Übergaben in ${target} angekommen?`,
    feedbackSubtitle: (target: string) =>
      `Das Programm sieht nicht in ${target} hinein. Halten Sie je Kunde fest, wie das Einlesen dort ausgegangen ist.`,
    customer: 'Kunde',
    handOverColumn: 'Übergabe',
    done: 'Erledigt',
    failed: 'Fehlgeschlagen',
    writtenAt: (date: string, time: string) => `${date}, ${time} Uhr`,
    reason: 'Was ist passiert?',
    reasonPlaceholder: 'Zum Beispiel: Kunde nicht gefunden',
    reasonNote: 'Die Übergabe bleibt liegen, bis Sie sie erneut freigeben.',
    feedbackFooter: 'Was Sie offen lassen, bleibt in der Übersicht als „Rückmeldung offen“ stehen.',
    saveFeedback: 'Rückmeldung speichern',
  },

  // Settings of the broker pilot: the profile (on screen „Arbeitsweise“) in plain words and retention.
  pilotSettings: {
    saved: 'Gespeichert.',
    toOverview: 'Zur Übersicht',
    reading: 'Einlesen',
    profile: 'Arbeitsweise',
    chooseProfile: 'Bitte wählen',
    readFrom: 'Gelesen wird',
    noFolder: 'noch kein Ordner gewählt',
    change: 'ändern',
    choose: 'wählen',
    folderStructure: (level: number | null) =>
      `Ordnerstruktur: ${level === null ? '' : `${'Ordner/'.repeat(level - 1)}Kundenname/`}Belege`,
    retention: 'Aufbewahrung',
    retentionLabel: 'Erledigte Einträge löschen nach',
    retentionDetail:
      'Gelöscht werden die gelesenen Angaben, Ihre Korrekturen und die Übergabedateien. Die eingescannten Dateien bleiben im Ordner.',
    days: (days: number) =>
      days === 365 ? 'einem Jahr' : days === 1 ? '1 Tag' : `${days} Tagen`,
    profileFile: 'Datei der Arbeitsweise',
    kindFiles: 'Belegart-Dateien',
  },

  // The path „Ordner einlesen“ from Overview.
  readFolder: {
    title: 'Welcher Ordner soll eingelesen werden?',
    subtitle:
      'Die Arbeitsweise legt fest, wie der Ordner aufgebaut ist und wohin die Angaben am Ende gehen.',
    way: 'Arbeitsweise',
    reads: (kinds: string[]) =>
      `Liest ${kinds.length > 1 ? `${kinds.slice(0, -1).join(', ')} und ${kinds.at(-1)}` : kinds.join('')}.`,
    customerNone: 'Kein Ordner nennt den Kunden.',
    customerFirst: 'Der Name des Unterordners ist der Kunde.',
    customerLevel: (level: number) =>
      `Der Name des Ordners auf der ${level}. Ebene unter dem gewählten Ordner ist der Kunde.`,
    goesTo: (target: string) => `Freigegebenes geht an ${target}.`,
    noWay: 'Noch ist keine Arbeitsweise gewählt. Sie wird in den Einstellungen gewählt.',
    folder: 'Ordner',
    noFolder: 'Noch kein Ordner gewählt',
    choose: 'Ordner wählen',
    chooseOther: 'Anderen Ordner wählen',
    filesStay:
      'Die eingescannten Dateien bleiben, wo sie liegen. Gespeichert werden nur die gelesenen Angaben und die Stelle im Beleg, an der sie stehen.',
    runsOn: 'Das Einlesen beginnt sofort und läuft weiter, während Sie arbeiten.',
    start: 'Einlesen starten',
  },

  errors: {
    title: 'Es ist ein Fehler aufgetreten',
    showDetails: 'Technische Details',
    close: 'Hinweis schließen',
    messages: {
      'file-not-found':
        'Der Beleg wurde nicht gefunden. Möglicherweise wurde er verschoben oder gelöscht.',
      'format-not-supported':
        'Dieses Format lässt sich nicht lesen. Möglich sind PDF, Tabellen (xlsx, xls, csv) und Bilder (png, jpg, tiff).',
      'file-too-large':
        'Der Beleg ist zu groß. Sehr große Scans lassen sich oft seitenweise aufteilen.',
      'document-corrupt':
        'Der Beleg ist beschädigt oder unlesbar. Er lässt sich mit einem anderen Programm möglicherweise reparieren.',
      'document-password-protected':
        'Der Beleg ist mit einem Kennwort geschützt. Bitte entfernen Sie den Schutz und öffnen Sie ihn erneut.',
      'document-empty': 'Der Beleg enthält nichts, was sich auswerten ließe.',
      'unknown-document': 'Der Beleg ist nicht mehr geöffnet. Bitte wählen Sie ihn erneut.',
      'page-not-found': 'Diese Seite gibt es im Beleg nicht.',
      'output-name-taken':
        'In diesem Ordner liegt eine Datei namens „Ausgabe“. Substrakt braucht den Namen für den Ordner, in den die Übergaben geschrieben werden. Die Datei bleibt unverändert; bitte benennen Sie sie um und wählen Sie den Ordner noch einmal.',
      'path-not-allowed':
        'Der Beleg liegt außerhalb der für diese Sitzung freigegebenen Ordner.',
      'not-authorized': 'Die Sitzung ist abgelaufen. Bitte starten Sie die Anwendung neu.',
      'egress-denied':
        'Es sind keine ausgehenden Verbindungen erlaubt. Das ist so vorgesehen — alle Belege bleiben auf diesem Gerät.',
      'document-kind-invalid':
        'Die Beschreibung einer Belegart ist fehlerhaft. Einzelheiten stehen im lokalen Protokoll.',
      'document-kind-unknown': 'Diese Belegart ist auf diesem Gerät nicht beschrieben.',
      'pipeline-profile-invalid':
        'Die Beschreibung einer Arbeitsweise ist fehlerhaft. Einzelheiten stehen im lokalen Protokoll.',
      'hand-over-table-invalid':
        'Eine Zuordnungstabelle für die Übergabe ist fehlerhaft. Einzelheiten stehen im lokalen Protokoll.',
      'pipeline-profile-unknown':
        'Es ist keine Arbeitsweise gewählt, oder die gewählte ist auf diesem Gerät nicht beschrieben.',
      'file-name-unreadable':
        'Der Dateiname enthält Zeichen, die nicht gelesen werden können. Bitte benennen Sie die Datei um.',
      'document-too-many-pages':
        'Die Datei hat zu viele Seiten und wurde nicht gelesen. Bitte teilen Sie sie auf.',
      'reading-interrupted':
        'Das Lesen dieser Datei wurde unterbrochen. Sie wird nicht von selbst erneut gelesen.',
      'inbox-entry-unknown': 'Dieser Beleg ist nicht mehr im Eingang.',
      'kind-change-refused': 'Die Angaben der Belegart wurden nicht geändert.',
      'correction-refused':
        'Die Änderung wurde nicht übernommen. Der Beleg ist bereits freigegeben, oder die Angabe passt nicht zu dieser Belegart.',
      'approval-refused':
        'Der Beleg kann noch nicht freigegeben werden. Eine benötigte Angabe fehlt oder ist nicht eindeutig.',
      'file-changed':
        'Die Datei wurde seit dem Lesen verändert. Sie wurde nicht angetastet.',
      'job-unknown': 'Diese Übergabe gibt es nicht mehr.',
      'job-transition-invalid': 'Diese Übergabe kann jetzt nicht erneut freigegeben werden.',
      'import-reason-missing':
        'Bitte schreiben Sie zu jeder fehlgeschlagenen Übergabe, was passiert ist.',
      'sidecar-not-connected': 'Substrakt läuft nicht. Bitte starten Sie die Anwendung neu.',
      'sidecar-unreachable': 'Substrakt antwortet nicht. Bitte starten Sie die Anwendung neu.',
      'response-unreadable': 'Die Antwort war unlesbar.',
      'unknown-error': 'Ein unerwarteter Fehler ist aufgetreten.',
      'internal-error':
        'Ein unerwarteter Fehler ist aufgetreten. Einzelheiten stehen im lokalen Protokoll.',
      'unexpected-error':
        'Ein unerwarteter Fehler ist aufgetreten. Einzelheiten stehen im lokalen Protokoll.',
    } as Record<string, string>,
  },
}
