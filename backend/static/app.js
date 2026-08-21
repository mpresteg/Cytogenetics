const input = document.getElementById('iscn-input');
const parseBtn = document.getElementById('parse-btn');
const resultsEl = document.getElementById('results');
const exampleSelect = document.getElementById('example-select');
const editionSelect = document.getElementById('edition-select');
const uploadBtn = document.getElementById('upload-btn');
const fileInput = document.getElementById('file-input');
const uploadStatus = document.getElementById('upload-status');
const uploadPdfBtn = document.getElementById('upload-pdf-btn');
const pdfFileInput = document.getElementById('pdf-file-input');
const uploadPdfSpinner = document.getElementById('upload-pdf-spinner');
const ocrReviewPanel = document.getElementById('ocr-review-panel');

// task 25: subject/demographic fields for FHIR export. Free text for
// name/specimen ID; native <input type="date"> for every date field so
// whatever reaches /api/export-fhir is already an unambiguous ISO date
// (see fhir_export.py's normalize_date() docstring) -- the browser's
// own date picker/validation does the disambiguation work this tool
// would otherwise have to guess at from free text.
const subjectFields = {
  patient_name: document.getElementById('subject-patient-name'),
  date_of_birth: document.getElementById('subject-dob'),
  specimen_id: document.getElementById('subject-specimen-id'),
  collection_date: document.getElementById('subject-collection-date'),
  report_date: document.getElementById('subject-report-date'),
};
const subjectDateHints = {
  date_of_birth: document.getElementById('subject-dob-hint'),
  collection_date: document.getElementById('subject-collection-date-hint'),
  report_date: document.getElementById('subject-report-date-hint'),
};

function currentSubjectFields() {
  const out = {};
  Object.entries(subjectFields).forEach(([key, el]) => { out[key] = el.value || ''; });
  return out;
}

// task 10: the lab's own written interpretation, extracted from the most
// recently uploaded PDF (if any), held here so it can be shown alongside
// this tool's generated assessment once the user clicks Parse -- the two
// happen at different times (upload vs. parse), so this bridges them.
// undefined = no PDF uploaded this session (don't show a comparison at
// all); null = a PDF was uploaded but no interpretation section was
// found in it (say so plainly); a string = the extracted section text.
let currentLabInterpretation;
let currentLabInterpretationUsedOcr = false;

async function loadEditions() {
  try {
    const res = await fetch('/api/editions');
    const data = await res.json();
    data.editions.forEach(ed => {
      const opt = document.createElement('option');
      opt.value = ed;
      opt.textContent = ed === data.default ? `${ed} (default)` : ed;
      if (ed === data.default) opt.selected = true;
      editionSelect.appendChild(opt);
    });
  } catch (e) {
    console.error('Could not load editions', e);
  }
}

async function loadExamples() {
  try {
    const res = await fetch('/api/examples');
    const data = await res.json();
    const addGroup = (label, items) => {
      const group = document.createElement('optgroup');
      group.label = label;
      items.forEach(ex => {
        const opt = document.createElement('option');
        opt.value = ex;
        opt.textContent = ex;
        group.appendChild(opt);
      });
      exampleSelect.appendChild(group);
    };
    addGroup('Karyotype', data.karyotype);
    addGroup('FISH', data.fish);
  } catch (e) {
    console.error('Could not load examples', e);
  }
}

exampleSelect.addEventListener('change', () => {
  if (exampleSelect.value) {
    input.value = exampleSelect.value;
    runParse();
  }
});

parseBtn.addEventListener('click', runParse);
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) runParse();
});

// File upload: reads a local plain-text file (one ISCN string per line —
// same shape the textarea already expects) client-side via FileReader and
// loads it into the textarea for review. No upload to the backend,
// nothing persisted.
//
// Deliberately does NOT auto-run parse, even though this content is read
// verbatim rather than extracted/guessed at (contrast PDF/OCR). The
// content still hasn't been seen *inside this tool* yet, same as a PDF
// upload -- and unlike the example dropdown (picking a specific known
// string from a visible list, which itself is the deliberate "run this"
// action), there's no principled reason a file load should skip the
// review step a paste or a PDF upload both require. One consistent rule
// now: anything loaded from outside the box (paste, .txt, PDF) needs an
// explicit Parse click; anything chosen from inside the box (the example
// dropdown) runs immediately, since choosing it *is* the action.
uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (!file) return;

  // A .txt upload switches to a plain-text source with no PDF/OCR/lab-
  // report context, so drop anything left over from a previous PDF
  // upload (including stale results from a previous document) rather
  // than show it stale.
  hideOcrReviewPanel();
  currentLabInterpretation = undefined;
  clearSubjectFields();
  resultsEl.innerHTML = '';

  const reader = new FileReader();
  reader.onload = () => {
    input.value = reader.result;
    showUploadStatus(`Loaded "${file.name}" — review before parsing.`);
    if (reader.result.split('\n').some(l => l.trim())) {
      renderPendingParsePlaceholder(resultsEl);
    }
  };
  reader.onerror = () => {
    showUploadStatus(`Could not read "${file.name}": ${reader.error}.`, true);
  };
  reader.readAsText(file);

  // Reset so choosing the same file again still fires 'change'.
  fileInput.value = '';
});

// Shown in the results area -- the same spot renderAssessment() fills in
// after Parse runs, using the same "This tool's interpretation" eyebrow
// label -- whenever content has just been loaded but not yet parsed
// (.txt or PDF upload; both require an explicit Parse click, see the
// comments above those handlers). Without this, a PDF upload in
// particular can look complete once the lab-reported interpretation
// panel renders: something visibly appeared in the results area, so
// there's no obvious cue that this tool's own interpretation --
// including whether anything matched the hematologic-malignancy
// reference table -- hasn't been generated yet.
function renderPendingParsePlaceholder(container) {
  const panel = document.createElement('div');
  panel.className = 'assessment-panel pending-parse';

  const label = document.createElement('p');
  label.className = 'eyebrow assessment-label';
  label.textContent = "This tool's interpretation";
  panel.appendChild(label);

  const body = document.createElement('p');
  body.className = 'placeholder';
  body.innerHTML = 'Not generated yet — click <strong>Parse</strong> above to check the loaded string(s), including any hematologic-malignancy reference flag.';
  panel.appendChild(body);

  container.appendChild(panel);
}

function clearSubjectFields() {
  Object.values(subjectFields).forEach(el => { el.value = ''; });
  Object.values(subjectDateHints).forEach(el => { el.textContent = ''; });
}

// task 25: pre-fills the subject-field inputs from a PDF's extracted
// candidates (extract_subject_candidates() in fhir_export.py) --
// editable, not locked, and never something the user has to hunt for:
// same "surface for review" treatment the ISCN candidates themselves
// already get in the textarea. Text fields (name, specimen ID) get the
// raw extracted string directly. Date fields only get pre-filled when
// the backend could confidently normalize the extracted text to ISO
// (see normalize_date()'s doc on why it only trusts unambiguous
// formats) -- when it couldn't, the date input is left blank and the
// raw extracted text is shown next to it as a hint, so nothing found in
// the PDF is silently lost even when it can't be safely auto-filled.
function applySubjectCandidates(candidates) {
  clearSubjectFields();
  if (!candidates) return;
  if (candidates.patient_name) subjectFields.patient_name.value = candidates.patient_name;
  if (candidates.specimen_id) subjectFields.specimen_id.value = candidates.specimen_id;
  ['date_of_birth', 'collection_date', 'report_date'].forEach(key => {
    const normalized = candidates[`${key}_normalized`];
    const raw = candidates[key];
    if (normalized) {
      subjectFields[key].value = normalized;
    } else if (raw) {
      subjectDateHints[key].textContent = `PDF text found: "${raw}" — enter above if this looks right.`;
    }
  });
}

function showUploadStatus(message, isError = false) {
  uploadStatus.textContent = message;
  uploadStatus.className = isError ? 'upload-status error' : 'upload-status';
  uploadStatus.hidden = false;
}

// PDF report upload (task 8; OCR fallback for scanned PDFs is task 11):
// sends the file to the backend (PDF text/OCR extraction needs Python
// libraries, so this can't be client-side the way the .txt upload above
// is), gets back candidate karyotype-shaped lines — each tagged with
// whether it came from the PDF's text layer or from OCR — and loads them
// into the textarea for review. Deliberately does NOT auto-run parse the
// way the .txt upload does — text pulled from a real-world PDF layout is
// a guess, not a trusted input, so the user should see exactly what was
// found before anything gets interpreted.
//
// OCR's error rate on dense, punctuation-heavy ISCN strings is materially
// higher than direct text extraction, so OCR-sourced lines need *more*
// scrutiny before parsing, not the same amount. An earlier version of
// this flagged that by prefixing those lines with "# OCR — verify
// against original: " directly in the textarea — but that mutated the
// actual parseable content: the prefix isn't valid ISCN syntax, so
// Parse would reliably fail on that line even after the user had
// reviewed and confirmed it was fine, unless they first hand-edited the
// prefix back out. The textarea is meant to hold exactly what a user
// would type or paste themselves, ready to parse — not content we've
// decorated. So instead: the textarea gets the plain, unmodified
// extracted text, and OCR provenance is called out separately, in
// ocrReviewPanel (see renderOcrReviewPanel below) — visible, but outside
// the parseable input.
//
// Also captures the lab's own written interpretation, if the PDF has one
// (task 10) — held in currentLabInterpretation so it can be shown
// alongside this tool's generated assessment for the user to compare.
// Rendered immediately once extraction finishes, not gated behind
// Parse: it comes straight from the PDF's own text, independent of
// which candidate lines get parsed (or whether the user parses at all),
// so there's no reason to hide it until Parse runs -- unlike candidates,
// there's no "trust it less" reason to delay this one, just a "this info
// exists" one. Parse re-renders the same panel afterward (see
// runParse()) using this same currentLabInterpretation value, so the two
// renders never disagree. Never auto-compared or scored; just shown
// together for a human to read both.
uploadPdfBtn.addEventListener('click', () => pdfFileInput.click());

function hideOcrReviewPanel() {
  ocrReviewPanel.hidden = true;
  ocrReviewPanel.innerHTML = '';
}

// Lists the OCR-sourced candidate lines (raw text, unmodified) in their
// own panel below the upload status, separate from the textarea, so the
// caution to double-check them against the original document is visible
// without touching what actually gets parsed. Hidden entirely when no
// candidate came from OCR.
function renderOcrReviewPanel(ocrCandidates) {
  if (!ocrCandidates.length) {
    hideOcrReviewPanel();
    return;
  }
  const plural = ocrCandidates.length === 1 ? '' : 's';
  ocrReviewPanel.innerHTML = `
    <p>${ocrCandidates.length} line${plural} came from OCR — verify against the original document before parsing:</p>
    <ul>${ocrCandidates.map(c => `<li>${escapeHtml(c.text)}</li>`).join('')}</ul>
  `;
  ocrReviewPanel.hidden = false;
}

// task 20: the only prior sign of work happening was the status text
// swap to "Reading ...", easy to miss -- for a text-layer PDF that
// resolves fast enough it barely matters, but the OCR fallback (task 11)
// rasterizes and OCRs each image-only page and can take several seconds
// per page, during which nothing changed and the upload button stayed
// clickable (a second click mid-request could fire an overlapping
// upload). Now: the button + file input are disabled and a spinner
// shows for the duration of the request, cleared via `finally` so it
// resets on every exit path -- success, a handled error response, or a
// thrown exception -- not just the happy path.
pdfFileInput.addEventListener('change', async () => {
  const file = pdfFileInput.files[0];
  if (!file) return;
  pdfFileInput.value = '';

  hideOcrReviewPanel();
  currentLabInterpretation = undefined;
  clearSubjectFields();
  resultsEl.innerHTML = '';
  showUploadStatus(`Reading "${file.name}"…`);
  const formData = new FormData();
  formData.append('file', file);

  uploadPdfBtn.disabled = true;
  pdfFileInput.disabled = true;
  uploadPdfSpinner.hidden = false;

  try {
    const res = await fetch('/api/extract-pdf', { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showUploadStatus(`Could not read "${file.name}": ${err.detail || res.statusText}`, true);
      return;
    }
    const data = await res.json();
    currentLabInterpretation = data.lab_interpretation ?? null;
    currentLabInterpretationUsedOcr = !!data.lab_interpretation_used_ocr;
    renderLabInterpretationPanel(currentLabInterpretation, currentLabInterpretationUsedOcr, resultsEl);
    applySubjectCandidates(data.subject_candidates);

    if (data.candidates.length === 0) {
      showUploadStatus(`No karyotype-shaped lines found in "${file.name}" (${data.page_count} page(s)).`, true);
      return;
    }

    input.value = data.candidates.map(c => c.text).join('\n');
    renderPendingParsePlaceholder(resultsEl);

    const ocrCandidates = data.candidates.filter(c => c.source === 'ocr');
    const textCount = data.candidates.length - ocrCandidates.length;
    const parts = [];
    if (textCount) parts.push(`${textCount} from the text layer`);
    if (ocrCandidates.length) parts.push(`${ocrCandidates.length} from OCR — verify against the original`);
    const plural = data.candidates.length === 1 ? '' : 's';
    showUploadStatus(
      `Found ${data.candidates.length} candidate line${plural} in "${file.name}" ` +
      `(${parts.join(', ')}) — review before parsing.`
    );
    renderOcrReviewPanel(ocrCandidates);
  } catch (e) {
    showUploadStatus(`Request failed: ${e}`, true);
  } finally {
    uploadPdfBtn.disabled = false;
    pdfFileInput.disabled = false;
    uploadPdfSpinner.hidden = true;
  }
});

async function parseOne(value) {
  const res = await fetch('/api/parse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ iscn: value, edition: editionSelect.value || undefined }),
  });
  return res.json();
}

// task 10: the lab's own written interpretation (from the most recently
// uploaded PDF, if any), shown once at the top of the results — it's a
// whole-document thing, not tied to any one batch line, so it doesn't
// repeat per "Input N of M" block. Rendered distinctly from this tool's
// assessment panel(s) below (see renderAssessment()'s "This tool's
// interpretation" label) so the two voices are never conflated; never
// auto-compared, just placed together for a human to read both.
function renderLabInterpretationPanel(interpretation, usedOcr, container) {
  const panel = document.createElement('div');
  panel.className = 'lab-interpretation-panel';

  const label = document.createElement('p');
  label.className = 'eyebrow lab-interpretation-label';
  label.textContent = 'Lab-reported interpretation';
  panel.appendChild(label);

  if (interpretation) {
    const body = document.createElement('pre');
    body.className = 'lab-interpretation-text';
    body.textContent = interpretation;
    panel.appendChild(body);
    if (usedOcr) {
      const caveat = document.createElement('p');
      caveat.className = 'lab-interpretation-caveat';
      caveat.textContent = 'Extracted via OCR — verify against the original document.';
      panel.appendChild(caveat);
    }
  } else {
    const empty = document.createElement('p');
    empty.className = 'placeholder';
    empty.textContent = 'No lab-reported interpretation section was found in this PDF.';
    panel.appendChild(empty);
  }

  container.appendChild(panel);
}

// task 14: batch mode's contract (task 6) is "one line = one entry," which
// breaks when a *single* ISCN string has been copy-pasted from a source
// that word-wrapped it across several physical lines (a PDF viewer, a
// Word doc, some EMR "copy" buttons) -- confirmed live with a real
// user-reported string that got shredded into broken fragments instead
// of parsing as one. Ported from the same structural signal
// `_candidate_needs_continuation()` / `_continuation_separator()` in
// `iscn_parser.py` already use for the analogous PDF-text-extraction
// problem (task 16): a line can't legally have ended where it did if
// it has an unclosed '(', a trailing list comma, or ends in "ish" (ISCN
// grammar always follows that word with more content) -- a structural
// signal, not a guess about what the content means.
//
// Batch mode's "one line = one entry" is a *stronger* assumption to
// bend than PDF-text scanning's "no per-line contract at all" (task 16
// itself flagged this), so this only ever folds a line into the
// immediately preceding entry when that entry itself looks
// structurally incomplete -- it never merges two lines that both look
// complete on their own, so genuinely separate, intentional batch
// entries are never at risk of a false merge. Capped the same way (see
// MAX_LINE_WRAP_CONTINUATIONS) so a single unresolved unclosed paren
// (e.g. a genuine typo, not a wrap) can't silently swallow every
// subsequent entry into one candidate. A blank line is treated as a
// deliberate separator and always breaks folding, even mid-wrap --
// there's no legitimate reason a real line wrap would land on a blank
// line, so this is a free, unambiguous extra safety margin.
const MAX_LINE_WRAP_CONTINUATIONS = 15;

function lineNeedsContinuation(candidate) {
  const stripped = candidate.replace(/\s+$/, '');
  if (!stripped) return false;
  const opens = (stripped.match(/\(/g) || []).length;
  const closes = (stripped.match(/\)/g) || []).length;
  if (opens > closes) return true;
  if (stripped.endsWith(',')) return true;
  if (/\bish$/.test(stripped)) return true;
  return false;
}

function continuationSeparator(candidate) {
  // Defaults to no separator (most real-world wraps land mid-token,
  // e.g. "TP53x" + "2" -> "TP53x2"); "ish" is the one case ISCN grammar
  // guarantees a following space ("nuc ish "/"ish " always precede the
  // probe/rearrangement content).
  return /\bish$/.test(candidate.replace(/\s+$/, '')) ? ' ' : '';
}

function foldLineWrappedEntries(rawText) {
  const folded = [];
  let continuations = 0;
  // True whenever the *immediately preceding physical line* was blank (or
  // there isn't a previous entry yet) -- folding is only allowed right
  // after a genuinely non-blank line, so a blank line always breaks it,
  // regardless of what the structural-continuation check on its own
  // would otherwise say.
  let blockedByBlankLine = true;
  for (const rawLine of rawText.split('\n')) {
    const trimmed = rawLine.trim();
    if (!trimmed) {
      blockedByBlankLine = true;
      continue;
    }
    const prev = folded.length ? folded[folded.length - 1] : null;
    if (!blockedByBlankLine && prev !== null && lineNeedsContinuation(prev) && continuations < MAX_LINE_WRAP_CONTINUATIONS) {
      folded[folded.length - 1] = prev.replace(/\s+$/, '') + continuationSeparator(prev) + trimmed;
      continuations += 1;
    } else {
      folded.push(trimmed);
      continuations = 0;
    }
    blockedByBlankLine = false;
  }
  return folded;
}

// Batch mode is a client-side loop over the existing single-string
// /api/parse endpoint, one request per non-blank line — no new backend
// endpoint. The parser and API already model exactly one ISCN string per
// call, and each line is independent (own errors/warnings/mosaic state),
// so looping client-side avoids inventing a batch request/response shape
// in main.py for what is really just "run parse N times".
async function runParse() {
  const lines = foldLineWrappedEntries(input.value);
  if (!lines.length) return;
  resultsEl.innerHTML = '<p class="placeholder">Parsing…</p>';
  try {
    const results = await Promise.all(lines.map(parseOne));
    resultsEl.innerHTML = '';
    if (currentLabInterpretation !== undefined) {
      renderLabInterpretationPanel(currentLabInterpretation, currentLabInterpretationUsedOcr, resultsEl);
    }
    results.forEach((data, idx) => {
      const block = document.createElement('div');
      block.className = 'batch-block';
      if (lines.length > 1) {
        const label = document.createElement('p');
        label.className = 'batch-label';
        label.textContent = `Input ${idx + 1} of ${lines.length}`;
        block.appendChild(label);
      }
      renderClones(data, block, lines[idx]);
      resultsEl.appendChild(block);
    });
  } catch (e) {
    resultsEl.innerHTML = `<p class="errors">Request failed: ${e}</p>`;
  }
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s ?? '';
  return div.innerHTML;
}

// Renders the case-level clinical assessment (task 9): a summary line
// always, and — only when the reference-table lookup actually matched
// something — a clearly-labeled, visually distinct list of the matches.
// Never rendered as a diagnosis; every match's own note text already
// carries a "Reference note (not diagnostic)" prefix from the backend.
// Always labeled "This tool's interpretation" (task 10) — not just when
// a lab-reported interpretation is also shown — so the label is
// predictable rather than appearing/disappearing based on hidden state.
function renderAssessment(assessment, container) {
  const panel = document.createElement('div');
  panel.className = `assessment-panel${assessment.flagged ? ' flagged' : ''}`;

  const label = document.createElement('p');
  label.className = 'eyebrow assessment-label';
  label.textContent = "This tool's interpretation";
  panel.appendChild(label);

  const summary = document.createElement('p');
  summary.className = 'assessment-summary';
  if (assessment.flagged) {
    summary.innerHTML = `<span class="badge malignancy">Reference flag</span> ${escapeHtml(assessment.summary)}`;
  } else {
    summary.textContent = assessment.summary;
  }
  panel.appendChild(summary);

  if (assessment.flagged) {
    const list = document.createElement('ul');
    list.className = 'assessment-matches';
    assessment.matches.forEach(m => {
      const li = document.createElement('li');
      const findingBit = m.finding_raw ? ` <code>${escapeHtml(m.finding_raw)}</code>` : '';
      li.innerHTML = `
        <div class="assessment-match-label"><strong>${escapeHtml(m.label)}</strong>${findingBit}</div>
        <div class="assessment-note">${escapeHtml(m.note)}</div>
      `;
      list.appendChild(li);
    });
    panel.appendChild(list);
  }

  container.appendChild(panel);
}

// Renders one /api/parse result (mosaic banner + clone cards) into the
// given container. Split out from runParse so batch mode can render each
// line's result into its own labeled block using the same markup as
// single-string mode. `rawInput` is the exact string that was sent to
// /api/parse to produce `data` -- threaded through so the export panel
// (task 25) can re-submit it to /api/export-fhir, which re-parses
// server-side rather than trusting a client-held copy of the result
// (see main.py's comment on that endpoint).
function renderClones(data, container, rawInput) {
  if (data.errors && data.errors.length && (!data.clones || data.clones.length === 0)) {
    const errBox = document.createElement('div');
    errBox.className = 'errors';
    errBox.textContent = data.errors.join(' ');
    container.appendChild(errBox);
    return;
  }

  if (data.assessment) renderAssessment(data.assessment, container);

  if (data.is_mosaic) {
    const banner = document.createElement('p');
    banner.className = 'mosaic-banner';
    banner.innerHTML = `<span class="badge mosaic">Mosaic</span> ${data.clone_count} clones detected`;
    container.appendChild(banner);
  }

  data.clones.forEach((clone, idx) => {
    const card = document.createElement('div');
    card.className = 'clone-card';

    const hasErrors = clone.errors && clone.errors.length > 0;
    const hasUnrecognized = clone.findings.some(f => f.category === 'unrecognized');
    const statusOk = !hasErrors && !hasUnrecognized;

    const header = document.createElement('div');
    header.className = 'clone-header';
    header.innerHTML = `
      <code>${escapeHtml(clone.raw)}</code>
      <span class="badge ${statusOk ? 'ok' : 'err'}">${statusOk ? 'Parsed cleanly' : 'Needs review'}</span>
    `;
    card.appendChild(header);

    const metaBits = [];
    if (!clone.fish_only) {
      metaBits.push(`Modal number: ${clone.modal_number ?? '—'}`);
      metaBits.push(`Sex chromosomes: ${clone.sex_chromosomes ?? '—'}`);
    } else {
      metaBits.push('FISH-only clone (no karyotype count given)');
    }
    if (clone.cell_count != null) metaBits.push(`${clone.cell_count} cells`);
    if (clone.fish_cell_count != null) metaBits.push(`${clone.fish_cell_count} FISH nuclei`);
    const meta = document.createElement('div');
    meta.className = 'meta-row';
    meta.textContent = metaBits.join(' · ');
    card.appendChild(meta);

    if (hasErrors) {
      const errBox = document.createElement('div');
      errBox.className = 'errors';
      errBox.innerHTML = `<strong>Errors</strong><ul>${clone.errors.map(e => `<li>${escapeHtml(e)}</li>`).join('')}</ul>`;
      card.appendChild(errBox);
    }
    if (clone.warnings && clone.warnings.length) {
      const warnBox = document.createElement('div');
      warnBox.className = 'warnings';
      warnBox.innerHTML = `<strong>Warnings</strong><ul>${clone.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}</ul>`;
      card.appendChild(warnBox);
    }
    if (clone.edition_notes && clone.edition_notes.length) {
      const editionBox = document.createElement('div');
      editionBox.className = 'warnings';
      editionBox.innerHTML = `<strong>Edition note</strong><ul>${clone.edition_notes.map(n => `<li>${escapeHtml(n)}</li>`).join('')}</ul>`;
      card.appendChild(editionBox);
    }

    if (clone.findings.length === 0) {
      const p = document.createElement('p');
      p.className = 'placeholder';
      p.textContent = 'No abnormalities listed — normal karyotype for the stated sex chromosomes.';
      card.appendChild(p);
    }

    clone.findings.forEach(f => {
      const fEl = document.createElement('div');
      fEl.className = `finding ${f.category}`;
      fEl.innerHTML = `
        <span class="raw">${escapeHtml(f.raw)}</span>
        <span class="category-tag">${escapeHtml(f.category)}</span>
        ${f.interpretation ? `<div class="interp">${escapeHtml(f.interpretation)}</div>` : ''}
        ${(f.warnings && f.warnings.length) ? f.warnings.map(w => `<div class="finding-warn">⚠ ${escapeHtml(w)}</div>`).join('') : ''}
      `;
      card.appendChild(fEl);
    });

    container.appendChild(card);
  });

  if (rawInput && data.clones && data.clones.length) {
    renderExportPanel(data, rawInput, container);
  }
}

// task 25 (stage 1): "Export FHIR (mCODE)" button for one parsed result
// (covers every clone in `data`, mosaic or not -- /api/export-fhir wraps
// them all into one DiagnosticReport, one Observation per clone, see
// fhir_export.py). Blocked by default whenever any clone needs review
// (errors, or an unrecognized finding) -- matching exactly the same
// "Needs review" badge condition each clone-card above already shows --
// with an explicit, visibly-cautionary override checkbox to export
// anyway, same discipline as the backend's own QC gate in
// build_mcode_export(). Re-sends the subject fields fresh on every
// click, so editing them after this panel first renders is honored.
function renderExportPanel(data, rawInput, container) {
  const needsReview = data.clones.some(c =>
    (c.errors && c.errors.length) || c.findings.some(f => f.category === 'unrecognized'));

  const panel = document.createElement('div');
  panel.className = 'export-panel';

  const controls = document.createElement('div');
  controls.className = 'export-controls';
  const exportBtn = document.createElement('button');
  exportBtn.type = 'button';
  exportBtn.className = 'secondary';
  exportBtn.textContent = 'Export FHIR (mCODE)…';
  controls.appendChild(exportBtn);
  panel.appendChild(controls);

  let overrideCheckbox = null;
  if (needsReview) {
    const row = document.createElement('div');
    row.className = 'override-row';
    overrideCheckbox = document.createElement('input');
    overrideCheckbox.type = 'checkbox';
    overrideCheckbox.id = `export-override-${Math.random().toString(36).slice(2)}`;
    const lbl = document.createElement('label');
    lbl.htmlFor = overrideCheckbox.id;
    lbl.textContent = 'Export anyway, despite the validation issue(s) flagged above';
    row.appendChild(overrideCheckbox);
    row.appendChild(lbl);
    panel.appendChild(row);
    exportBtn.disabled = true;
    overrideCheckbox.addEventListener('change', () => {
      exportBtn.disabled = !overrideCheckbox.checked;
    });
  }

  const status = document.createElement('p');
  status.className = 'export-status';
  status.hidden = true;
  panel.appendChild(status);

  exportBtn.addEventListener('click', async () => {
    status.hidden = false;
    status.className = 'export-status';
    status.textContent = 'Exporting…';
    exportBtn.disabled = true;
    const existingJson = panel.querySelector('.export-json');
    if (existingJson) existingJson.remove();
    const existingCaveats = panel.querySelector('.export-caveats');
    if (existingCaveats) existingCaveats.remove();

    try {
      const res = await fetch('/api/export-fhir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          iscn: rawInput,
          edition: editionSelect.value || undefined,
          subject: currentSubjectFields(),
          override: !!(overrideCheckbox && overrideCheckbox.checked),
        }),
      });
      const result = await res.json();
      if (!res.ok) {
        status.className = 'export-status error';
        status.textContent = result.detail || 'Export failed.';
        return;
      }
      status.textContent = 'Exported.';

      if (result.caveats && result.caveats.length) {
        const caveatBox = document.createElement('div');
        caveatBox.className = 'export-caveats';
        caveatBox.innerHTML = `<p>Stage-1 export caveats — review before relying on this JSON:</p>
          <ul>${result.caveats.map(c => `<li>${escapeHtml(c)}</li>`).join('')}</ul>`;
        panel.appendChild(caveatBox);
      }

      const jsonText = JSON.stringify(result.bundle, null, 2);
      const pre = document.createElement('pre');
      pre.className = 'export-json';
      pre.textContent = jsonText;
      panel.appendChild(pre);
    } catch (e) {
      status.className = 'export-status error';
      status.textContent = `Request failed: ${e}`;
    } finally {
      exportBtn.disabled = !!(needsReview && !(overrideCheckbox && overrideCheckbox.checked));
    }
  });

  container.appendChild(panel);
}

loadExamples();
loadEditions();
