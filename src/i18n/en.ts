/**
 * English interface copy and the vocabulary that keeps it consistent.
 *
 * | German screen word | English screen word |
 * |---|---|
 * | Übersicht, Prüfen, Belegarten, Einstellungen | Overview, Review, Document kinds, Settings |
 * | Beleg | document |
 * | Belegart | document kind |
 * | Arbeitsweise | way of working |
 * | Angabe | detail |
 * | sicher erkannt | recognised |
 * | nicht eindeutig | unclear |
 * | wartet auf Prüfung | waiting for review |
 * | abgelegt | filed |
 * | Alle Belege bleiben auf diesem Gerät. | All documents stay on this device. |
 *
 * Engine-room terms remain under “Settings → Technical details”. The other
 * screens use the short words a clerk needs to finish the work.
 */

import type { Texts } from './index'

// Small counts are written as words, as in the approved concept.
const COUNT_EN: Record<number, string> = {
  2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five', 6: 'Six',
}

export const en: Texts = {
  app: {
    title: 'Substrakt',
    version: 'Version',
    promise: 'All documents stay on this device.',
  },

  places: {
    overview: 'Overview',
    review: 'Review',
    templates: 'Document kinds',
    settings: 'Settings',
  },

  theme: {
    toggle: 'Light or dark',
  },

  keys: {
    enter: 'Enter',
  },

  time: {
    justNow: 'just now',
    minuteAgo: '1 minute ago',
    minutesAgo: (minutes: number) => `${minutes} minutes ago`,
    hourAgo: '1 hour ago',
    hoursAgo: (hours: number) => `${hours} hours ago`,
    yesterday: 'yesterday',
    daysAgo: (days: number) => `${days} days ago`,
  },

  state: {
    running: 'Everything is running',
    starting: 'Substrakt is starting',
    startingDetail: 'One moment — the reader is getting ready.',
    unavailable: 'Substrakt is not running',
    unavailableDetail: 'Please restart the application.',
    ready: (templates: number) =>
      templates === 1 ? '1 template set up' : `${templates} templates set up`,
    noTemplates: 'No template set up yet',
  },

  overview: {
    lastRead: 'last read',
    reviewNow: 'Review now',
  },

  review: {
    empty: 'Nothing to review',
    emptyDetail: 'All details were recognised clearly.',
    documentOf: (n: number, total: number) => `Document ${n} of ${total}`,
    readAt: (time: string) => `read at ${time}`,
    unclear: 'One detail is unclear',
    looksRight: 'Looks right',
    change: 'Change',
    accept: 'Accept',
    discard: 'Discard',
    isMissing: 'This detail is missing from the document',
    rest: 'Everything else was recognised',
    noMore: 'There are no other details in this template.',
    none: 'nothing found',
    appliesHere:
      'What you enter here applies to this document only, not to its document kind.',
    reason: {
      noValue:
        'There was nothing readable in the marked area. Enter the value or mark it as missing from the document.',
      noEvidence:
        'The value was found, but its place in the document was not. It cannot be checked without that place.',
      uncertain: 'The place differs from the usual one. The mark is shown on the left.',
      type: 'The value does not match what should be here.',
      weak: 'The text here was hard to read. Please compare the value with the document.',
    },
  },

  // Review of an entry from the watched folder (broker pilot).
  inboxReview: {
    documentOf: (n: number, total: number, customer: string | null) =>
      `Document ${n} of ${total}` + (customer ? ` · Customer ${customer}` : ''),
    recognisedAs: 'Recognised as',
    unclear: (n: number) => (n === 1 ? 'One detail is unclear' : `${COUNT_EN[n] ?? n} details are unclear`),
    questionFor: (label: string) => `Is “${label}” right?`,
    reason: {
      noValue: 'Nothing was found for it in the document. Enter what it says there.',
      unclear: 'The value read is not unambiguous. The left side marks where it was read.',
      noLocation: 'The value was read, but without a place in the document.',
      unclearUnmarked: 'The value read is not unambiguous.',
    },
    rest: 'Other details',
    clickShows: 'Click a detail to see its place in the document and change it.',
    noPlace: 'The document has no place for this detail.',
    dateForm: 'DD.MM.YYYY',
    dateHint: 'Please enter as DD.MM.YYYY, for example 01.04.2025. This date does not exist or is incomplete.',
    numberHint: 'This is not an amount. Please enter a number, for example 250.94.',
    typeHint: 'This entry does not fit the detail. Please check it.',
    settled: 'All details are settled',
    settledDetail:
      'Click a detail to see its place in the document and open it; change what is wrong before you approve.',
    boldChanged: 'Bold: changed by you.',
    approve: 'Approve document',
    changeValue: (label: string) => `Change ${label}`,
    approveMeans:
      'Approved means ready for hand-over. Nothing is written until you have seen and confirmed the hand-over.',
    later: 'Decide later',
    missing: 'missing in the document',
    settledMark: 'settled',
    waitingMark: 'waits for you',
    noKindQuestion: 'What should this document be read as?',
    noDocument: 'This document cannot be shown here.',
    firstRead: 'Read first',
    nowRead: 'Read now',
    sameQuestion: 'Is this the same document?',
    sameDetail: (count: number) =>
      `${count === 1 ? 'One detail matches' : `${COUNT_EN[count] ?? count} details match`} a document already read. The file itself is a different one, for example a second scan. You decide this, not the program.`,
    same: 'The same document',
    sameMeans: 'It is not handed over a second time.',
    different: 'A new document',
    differentMeans: 'It is reviewed and approved like any other.',
    emptyDetail: 'All documents read are approved or decided.',
    emptyCard: 'What is approved is listed in the overview',
    emptyCardDetail: (target: string) => `There you also see what would be handed over to ${target}.`,
    toOverview: 'To the overview',
    identical: 'The same content',
    identicalDetail:
      'This file is exactly the same as the document read first and is neither read nor handed over.',
    chooseKindDetail: 'The document kind was not recognised for sure.',
    readWith: 'Read with it',
    approveAfter: (n: number) => (n === 1 ? 'You can approve once one more detail is confirmed or corrected.' : `You can approve once ${COUNT_EN[n]?.toLowerCase() ?? n} more details are confirmed or corrected.`),
    refused: {
      'entry-changed':
        'The document was changed elsewhere in the meantime. You now see the new state; your input is kept.',
      'entry-not-waiting':
        'This document no longer waits for review. It was approved or decided in the meantime.',
      'kind-not-in-profile': 'This document kind does not belong to this folder.',
      'value-unknown': 'This detail does not belong to this document kind.',
      'value-empty': 'An empty detail cannot be accepted.',
      'values-not-settled': 'A required detail is still missing or unclear.',
      'kind-missing': 'First choose what the document should be read as.',
      'possible-duplicate-undecided': 'First decide whether this is the same document.',
      'no-possible-duplicate': 'This document has already been decided.',
      'hand-over-not-possible': 'This document cannot be handed over like this.',
    } as Record<string, string>,
  },

  templates: {
    title: 'Templates',
    subtitle:
      'A template tells the application where each detail is in a document and what to do with it.',
    newLabel: 'New template',
    search: 'Search templates',
    count: (n: number) => (n === 1 ? '1 template' : `${n} templates`),
    lastUsed: 'Last used',
    all: 'All templates · A–Z',
    none: 'No template yet',
    noneDetail:
      'Open a typical document and draw boxes around the details you need. The template does the rest.',
    nothingFound: 'No template matches this search.',
    values: (n: number) => (n === 1 ? '1 detail' : `${n} details`),
    changed: 'last changed',
    readDocument: 'Read a document with this template',
    changeValues: 'Change details',
    delete: 'Delete template',
    deleteQuestion: (name: string) =>
      `The template “${name}” and all its details will be deleted. This cannot be undone.`,
    confirmDelete: 'Delete permanently',
    cancel: 'Cancel',
    reading: 'Reading document …',
  },

  kinds: {
    title: 'Document kinds',
    listSubtitle: 'The program reads these document kinds in the watched folder.',
    none: 'No document kind yet',
    noneDetail: 'In Settings you choose what is read. Then its document kinds appear here.',
    toSettings: 'Open Settings',
    toOverview: 'Go to Overview',
    values: (n: number) => (n === 1 ? '1 detail' : `${n} details`),
    back: 'Document kinds',
    leaveQuestion: 'Your changes are not saved yet. Discard them?',
    discard: 'Discard',
    keepEditing: 'Keep editing',
    kindTitle: (kind: string) => `What is read from “${kind}”`,
    subtitle:
      'What you rename, remove or add here applies from the next document read.',
    goesTo: (target: string) => `goes to ${target}`,
    onlyShown: 'only shown',
    remove: 'Remove',
    restore: 'Restore',
    warning: (target: string) => `${target} will then no longer receive this detail.`,
    newPlaceholder: 'New detail, for example Excess',
    newHint: 'as it stands in the document',
    add: 'Add',
    renameHint: 'To rename, simply type in the line.',
    save: 'Save changes',
    saved: 'Saved. Documents already read stay as they are.',
    refused: {
      'no-value-left': 'A document kind needs at least one detail.',
      'label-empty': 'Every detail needs a name.',
      'label-twice': 'Two details have the same name. Please give each its own.',
      'value-unknown': 'The details have changed in the meantime. Please open the document kind again.',
      'target-needs-a-value': 'The target program needs at least one of these details.',
      invalid: 'The document kind cannot be saved like this.',
    } as Record<string, string>,
  },

  assistant: {
    title: 'Set up a new template',
    editTitle: 'Change template',
    backToTemplates: 'Templates',
    steps: {
      document: 'Sample document',
      values: 'Mark details',
      result: 'Result',
      finish: 'Finish',
    },
    nextStep: 'Next',
    back: 'Back',

    document: {
      title: 'Drop a typical document here',
      subtitle:
        'Use an invoice, delivery note or spreadsheet of this kind. PDF, photo, scan and spreadsheet files work. The document stays on this device.',
      choose: 'Choose document',
      notice:
        'Set this up once. After that, you can read every document of the same kind in one step.',
      loaded: 'This document is the sample',
      other: 'Choose another document',
    },

    values: {
      title: 'These are the details I need',
      question: 'What is shown here?',
      placeholder: 'For example, invoice number',
      accept: 'Accept',
      cancel: 'Cancel',
      suggestions: ['Invoice number', 'Date', 'Amount', 'Sender', 'IBAN'],
      notice:
        'Draw a box around a place in the document and say what it contains. That is all you need to do.',
      empty: 'No detail marked yet.',
      marked: (n: number) => (n === 1 ? '1 detail marked' : `${n} details marked`),
      notFound: 'there is nothing readable here',
      remove: 'Remove detail',
      waiting: 'Draw a box in the document now',
    },

    result: {
      title: 'What should each document become?',
      table: 'One table',
      tableDetail: 'Each document becomes one row. Easy to open, sort and share.',
      file: 'One file per document',
      fileDetail: 'Use this when another application reads the data.',
      custom: 'Custom format',
      customDetail: 'Defined by your IT team. This will come in a later stage.',
      preview: 'This is what the result looks like',
      keyName: 'Names in the result',
      keyDetail:
        'These names identify the details in files read by other applications. The suggestion comes from the display name. Change it if your IT team requires another spelling.',
      keyError:
        'Use letters, numbers and underscores. The first character cannot be a number.',
      duplicateKey: 'Another detail already uses this name.',
    },

    finish: {
      name: 'Template name',
      namePlaceholder: 'For example, Invoice — Northwind Engineering',
      nameMissing: 'Give the template a name.',
      summary: {
        template: 'Template',
        values: 'Details',
        result: 'Result',
        unclear: 'Unclear documents',
        unclearValue: 'go to the review list',
        unclearDetail: 'Everything else continues.',
      },
      promise:
        'The document, template and result stay on this device. There is no outside connection.',
      save: 'Save template',
      running: 'Saving …',
    },
  },

  settings: {
    title: 'Settings',
    appearance: 'Appearance',
    light: 'Light',
    dark: 'Dark',
    lightDetail: 'The default. A calm paper grey.',
    darkDetail: 'Equally complete, for dark rooms.',
    language: 'Language',
    german: 'German',
    germanCode: 'DE',
    germanDetail: 'The default.',
    english: 'English',
    englishCode: 'EN',
    englishDetail: 'The English interface.',
    privacy: 'Privacy and technology',
    noConnection: 'There is no outside connection',
    noConnectionDetail:
      'Documents, details and results never leave this device. There is no network access to turn on.',
    technical: 'Technical details',
    technicalDetail:
      'The terms below describe the engine room. They are for IT staff, not everyday work.',
    textRecognition: 'Text recognition',
    localEngine: 'local · Tesseract',
    storageLocation: 'Storage location',
    thisDevice: 'this device',
  },

  document: {
    state: {
      filed: 'filed',
      read: 'read',
      waiting: 'waiting for review',
    },
    saveResult: 'Save result',
    loading: 'Reading document …',
    formats: 'PDF, spreadsheets and images',
  },

  viewer: {
    page: 'Page',
    of: 'of',
    previous: 'Previous page',
    next: 'Next page',
    zoomOut: 'Zoom out',
    zoomIn: 'Zoom in',
    resetZoom: 'Reset view',
    rotate: 'Rotate page',
    sheet: 'Sheet',
  },

  highlight: {
    newLabel: 'Draw box',
    delete: 'Remove mark',
    none: 'Nothing marked yet',
    count: (n: number) => (n === 1 ? '1 mark' : `${n} marks`),
  },

  info: {
    pages: 'Pages',
    mode: 'Mode',
    sidecar: 'Backend',
  },

  mode: {
    airgap: 'Air-gap — no outgoing connections',
    onprem: 'On-premise',
    cloud: 'Cloud enabled',
  },

  // Overview of the broker pilot: the watched folder and its imports.
  pilotOverview: {
    startTitle: 'Nothing has been read yet',
    startSubtitle:
      'The program reads everything in the chosen folder by itself.',
    startCard: 'One folder, with one subfolder per customer',
    startCardDetail:
      'That is all it takes. Documents added later are read while the program is open.',
    chooseFolder: 'Read folder',
    readingTitle: (read: number) =>
      read === 1 ? 'Reading: 1 document so far' : `Reading: ${read} documents so far`,
    readingSubtitle:
      'You can start reviewing what is already listed below.',
    waitingTitle: (waiting: number) =>
      waiting === 1
        ? '1 document is waiting for your approval'
        : `${waiting} documents are waiting for your approval`,
    waitingSubtitle: 'Nothing is handed over before you have seen and approved it.',
    readyTitle: 'Everything reviewed – ready to hand over',
    readySubtitle: (approved: number) =>
      approved === 1 ? 'One document is approved.' : `${approved} documents are approved.`,
    quietTitle: 'Nothing to do',
    quietSubtitle: 'New documents in the folder appear here by themselves.',
    watching: 'The folder is watched while the program is open.',
    notWatching: 'The folder is not being watched right now.',
    withErrors: (count: number) => (count === 1 ? '1 document with an error' : `${count} documents with an error`),
    errorsTitle: 'Not everything could be read',
    errorsSubtitle: 'The documents with an error are listed below, with the reason.',
    showErrors: 'Show errors',
    imported: 'Read',
    importOf: (date: string, time: string) => `Read on ${date}, ${time}`,
    customersAndDocuments: (customers: number, documents: number) =>
      `${customers === 1 ? '1 customer' : `${customers} customers`} · ${documents === 1 ? '1 document' : `${documents} documents`}`,
    laterArrivals: (count: number) => `${count} added later`,
    duplicates: (count: number) => `${count} duplicate`,
    possibleDuplicates: (count: number) => `${count} possibly duplicate`,
    beingRead: (count: number) => `${count} being read`,
    allStates: 'All states',
    period: 'Period',
    periods: {
      latest: 'Most recent import',
      days3: '3 days',
      week: '1 week',
      month: '1 month',
      months3: '3 months',
    },
    showAll: (count: number) => `Show all ${count} documents`,
    state: 'State',
    search: 'Search by file, insurer or number',
    searchLabel: 'Search',
    hits: (hits: number, all: number) => `${hits} of ${all} documents`,
    resetFilter: 'Reset filter',
    noMatch: 'No document matches this filter.',
    file: 'File',
    recognisedAs: 'Recognised as',
    noCustomer: 'no customer',
    documents: (count: number) => (count === 1 ? '1 document' : `${count} documents`),
    notRead: 'not read',
    notRecognised: 'not recognised',
    sameContentAs: (file: string) => `same content as “${file}”`,
    compare: 'compare',
    states: {
      reading: 'being read …',
      waiting: 'waiting for review',
      ready: 'ready to hand over',
      filed: 'filed',
      possible: 'possibly duplicate',
      error: 'Error',
      duplicate: 'duplicate',
    },
    unclear: 'unclear',
    laterArrival: 'added later',
    unclearValues: (count: number) =>
      count === 1 ? '1 detail unclear' : `${count} details unclear`,
    certain: 'recognised',
    approvedState: 'approved',
    manual: 'Read by hand',
    showHandOver: 'Show hand-over',
    handedOverTitle: (customers: number, target: string) =>
      customers === 1
        ? `1 hand-over is ready for ${target}`
        : `${customers} hand-overs are ready for ${target}`,
    handedOverSubtitle: (target: string) =>
      `Import the files in ${target}, then record here whether it worked.`,
    giveFeedback: 'Report the result',
    resultTitle: (done: number, failed: number) =>
      `${done === 1 ? '1 hand-over' : `${done} hand-overs`} done, ${failed} failed`,
    resultSubtitle:
      'A failed hand-over waits until you release it again.',
    releaseFailed: 'Release failed hand-over again',
    handedOverGroup: 'handed over · result open',
    handedOverRow: 'handed over',
    done: 'done',
    importFailed: 'failed',
    failedBecause: (reason: string) => `failed · ${reason}`,
  },

  // Before and after a hand-over: what it would write, and what importing it did.
  handOver: {
    title: (target: string) => `This would be handed over to ${target}`,
    subtitle:
      'Nothing is written yet: here you see, detail by detail, what would arrive for which customer and contract, and from which document.',
    preparing: 'Putting together what would be handed over …',
    nothingTitle: 'Nothing is ready to hand over',
    nothingDetail: 'As soon as you approve a document of a customer, it appears here.',
    contractsFrom: (contracts: number, documents: number) =>
      `${contracts === 1 ? '1 contract' : `${contracts} contracts`} from ${documents === 1 ? '1 document' : `${documents} documents`}`,
    notYet: 'not handed over yet',
    source: (kind: string, page: number) => `${kind}, page ${page}`,
    changed: 'changed by you',
    aValue: 'a detail',
    missing: (label: string) => `The hand-over needs the detail “${label}”.`,
    unknownInsurer: (value: string, target: string) =>
      `It is not recorded under which name ${target} keeps ${value ? `the insurer “${value}”` : 'this insurer'}. The contract waits until that is entered. Nothing is guessed.`,
    unknownLine: (value: string, target: string) =>
      `It is not recorded how ${target} keeps ${value ? `the line of business “${value}”` : 'this line of business'}. The contract waits until that is entered. Nothing is guessed.`,
    unknownPaymentMode: (value: string, target: string) =>
      `It is not recorded how ${target} keeps ${value ? `the payment mode “${value}”` : 'this payment mode'}. The contract waits until that is entered. Nothing is guessed.`,
    annualOnly:
      'Only the annual premium is known, but the premium per payment is handed over. With instalments it cannot be worked out; please add it in the document.',
    doesNotFit: (label: string) =>
      `The detail “${label}” does not fit into the hand-over. Nothing is cut; please check it in the document.`,
    twoPolicies:
      'Two policies carry the same policy number. Please check which number is right.',
    twoHolders:
      'The documents of this contract name different policyholders. Please check which one is right.',
    kindNotHandedOver: (kind: string, target: string) =>
      `${kind} is not handed over yet – please enter the change in ${target} by hand.`,
    cannotWrite: 'This document cannot be handed over like this.',
    problems: {
      'hand-over-settings-invalid':
        'The hand-over is not fully described for this way of working yet. Until it is, nothing is written for this customer.',
      'hand-over-table-invalid':
        'A mapping table for the hand-over is broken. Until it is corrected, nothing is written for this customer.',
      'hand-over-without-customer': 'Nothing is handed over without a customer.',
      'hand-over-folder-missing':
        'The chosen folder has no subfolder “Ausgabe”. Choose the folder again in Settings and it is created.',
      'hand-over-name-taken':
        'A foreign file in the folder “Ausgabe” already has the name of this hand-over. It stays as it is; please rename it and release the document again.',
    },
    fileIn: 'One file per customer is created in the folder',
    importYourself: (target: string) => `You import it into ${target} yourself.`,
    write: 'Write hand-over',
    feedbackTitle: (target: string) => `Did the hand-overs arrive in ${target}?`,
    feedbackSubtitle: (target: string) =>
      `The program cannot look into ${target}. Record for each customer how the import went there.`,
    customer: 'Customer',
    handOverColumn: 'Hand-over',
    done: 'Done',
    failed: 'Failed',
    writtenAt: (date: string, time: string) => `${date}, ${time}`,
    reason: 'What happened?',
    reasonPlaceholder: 'For example: customer not found',
    reasonNote: 'The hand-over waits until you release it again.',
    feedbackFooter: 'Whatever you leave open stays in the overview as “result open”.',
    saveFeedback: 'Save result',
  },

  // Settings of the broker pilot: the profile (on screen “way of working”) in plain words and retention.
  pilotSettings: {
    saved: 'Saved.',
    toOverview: 'Go to Overview',
    reading: 'Reading',
    profile: 'Way of working',
    chooseProfile: 'Please choose',
    readFrom: 'Reads from',
    noFolder: 'no folder chosen yet',
    change: 'change',
    choose: 'choose',
    folderStructure: (level: number | null) =>
      `Folder structure: ${level === null ? '' : `${'folder/'.repeat(level - 1)}customer name/`}documents`,
    retention: 'Retention',
    retentionLabel: 'Delete finished entries after',
    retentionDetail:
      'This deletes the details read, your corrections and the hand-over files. The scanned files stay in the folder.',
    days: (days: number) => (days === 365 ? 'one year' : days === 1 ? '1 day' : `${days} days`),
    profileFile: 'Way of working file',
    kindFiles: 'Document kind files',
  },

  readFolder: {
    title: 'Which folder should be read?',
    subtitle: 'The way of working sets how the folder is laid out and where the details go in the end.',
    way: 'Way of working',
    reads: (kinds: string[]) =>
      `Reads ${kinds.length > 1 ? `${kinds.slice(0, -1).join(', ')} and ${kinds.at(-1)}` : kinds.join('')}.`,
    customerNone: 'No folder names the customer.',
    customerFirst: 'The name of the subfolder is the customer.',
    customerLevel: (level: number) =>
      `The name of the folder ${level} levels below the chosen one is the customer.`,
    goesTo: (target: string) => `Approved details go to ${target}.`,
    noWay: 'No way of working is chosen yet. Settings chooses it.',
    folder: 'Folder',
    noFolder: 'No folder chosen yet',
    choose: 'Choose folder',
    chooseOther: 'Choose another folder',
    filesStay:
      'The scanned files stay where they are. Only the details read and the place in the document where they stand are stored.',
    runsOn: 'Reading starts at once and goes on while you work.',
    start: 'Start reading',
  },

  errors: {
    title:'Something went wrong',
    showDetails: 'Technical details',
    close: 'Close message',
    messages: {
      'file-not-found': 'The document was not found. It may have been moved or deleted.',
      'format-not-supported':
        'This format cannot be read. You can use PDF, spreadsheets (xlsx, xls, csv) and images (png, jpg, tiff).',
      'file-too-large': 'The document is too large. Splitting a large scan into pages may help.',
      'document-corrupt':
        'The document is damaged or unreadable. Another application may be able to repair it.',
      'document-password-protected':
        'The document is password protected. Remove the protection and open it again.',
      'document-empty': 'The document contains nothing that can be read.',
      'unknown-document': 'The document is no longer open. Please choose it again.',
      'page-not-found': 'This page is not in the document.',
      'output-name-taken':
        'This folder holds a file named “Ausgabe”. Substrakt needs the name for the folder the hand-overs are written to. The file stays as it is; please rename it and choose the folder again.',
      'path-not-allowed': 'The document is outside the folders allowed for this session.',
      'not-authorized': 'The session has expired. Please restart the application.',
      'egress-denied':
        'Outgoing connections are not allowed. This is intentional — all documents stay on this device.',
      'document-kind-invalid':
        'A document description is invalid. Details are in the local log.',
      'document-kind-unknown': 'This document kind is not described on this device.',
      'pipeline-profile-invalid':
        'A description of a way of working is invalid. Details are in the local log.',
      'hand-over-table-invalid':
        'A mapping table for the hand-over is invalid. Details are in the local log.',
      'pipeline-profile-unknown':
        'No way of working is chosen, or the chosen one is not described on this device.',
      'file-name-unreadable':
        'The file name contains characters that cannot be read. Please rename the file.',
      'document-too-many-pages':
        'The file has too many pages and was not read. Please split it.',
      'reading-interrupted':
        'Reading this file was interrupted. It is not read again by itself.',
      'inbox-entry-unknown': 'This document is no longer in the inbox.',
      'kind-change-refused': 'The details of the document kind were not changed.',
      'correction-refused':
        'The change was not stored. The document is already approved, or the detail does not fit this document kind.',
      'approval-refused':
        'The document cannot be approved yet. A required detail is missing or unclear.',
      'file-changed': 'The file has changed since it was read. It was left untouched.',
      'job-unknown': 'This hand-over no longer exists.',
      'job-transition-invalid': 'This hand-over cannot be released again now.',
      'import-reason-missing': 'Please write down what happened for every failed hand-over.',
      'sidecar-not-connected': 'Substrakt is not running. Please restart the application.',
      'sidecar-unreachable': 'Substrakt is not responding. Please restart the application.',
      'response-unreadable': 'The response could not be read.',
      'unknown-error': 'An unexpected error occurred.',
      'internal-error': 'An unexpected error occurred. Details are in the local log.',
      'unexpected-error': 'An unexpected error occurred. Details are in the local log.',
    },
  },
}
