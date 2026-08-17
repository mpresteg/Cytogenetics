const input = document.getElementById('iscn-input');
const parseBtn = document.getElementById('parse-btn');
const resultsEl = document.getElementById('results');
const exampleSelect = document.getElementById('example-select');
const editionSelect = document.getElementById('edition-select');

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

async function runParse() {
  const value = input.value.trim();
  if (!value) return;
  resultsEl.innerHTML = '<p class="placeholder">Parsing…</p>';
  try {
    const res = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ iscn: value, edition: editionSelect.value || undefined }),
    });
    const data = await res.json();
    render(data);
  } catch (e) {
    resultsEl.innerHTML = `<p class="errors">Request failed: ${e}</p>`;
  }
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s ?? '';
  return div.innerHTML;
}

function render(data) {
  resultsEl.innerHTML = '';

  if (data.errors && data.errors.length && (!data.clones || data.clones.length === 0)) {
    resultsEl.innerHTML = `<div class="errors">${escapeHtml(data.errors.join(' '))}</div>`;
    return;
  }

  if (data.is_mosaic) {
    const banner = document.createElement('p');
    banner.className = 'mosaic-banner';
    banner.innerHTML = `<span class="badge mosaic">Mosaic</span> ${data.clone_count} clones detected`;
    resultsEl.appendChild(banner);
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

    resultsEl.appendChild(card);
  });
}

loadExamples();
loadEditions();
