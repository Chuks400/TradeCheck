(() => {
  'use strict';
  let activeTab = 'sample';
  let lastReport = null;
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (s) => String(s === null || s === undefined ? '—' : s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tabs = [...document.querySelectorAll('[data-tab]')];
  tabs.forEach(tab => tab.addEventListener('click', () => {
    activeTab = tab.dataset.tab;
    tabs.forEach(t => { const selected = t === tab; t.classList.toggle('active',selected); t.setAttribute('aria-selected', String(selected)); });
    ['sample','upload','text'].forEach(n => $('tab-'+n).classList.toggle('hidden', n !== activeTab));
    $('errorBox').classList.add('hidden');
  }));

  async function getSamples() {
    try {
      const response = await fetch('/api/samples');
      const list = await response.json();
      const descriptions = Object.fromEntries(list.map(it => [it.id, it.description]));
      const update = () => { $('caseDescription').textContent = descriptions[$('sampleCase').value] || ''; };
      $('sampleCase').addEventListener('change', update);
      update();
    } catch (e) { /* Defaults still work if catalogue fetch fails */ }
  }
  getSamples();

  [['invoiceFile','invoiceName'],['packingFile','packingName'],['bolFile','bolName'],['cooFile','cooName']].forEach(([input,label]) => {
    $(input).addEventListener('change', () => { $(label).textContent = $(input).files?.[0]?.name || 'Choose PDF (max 8 MB)'; });
  });
  const toBase64 = async file => {
    if (!file) throw new Error('Choose both PDF documents.');
    if (!file.name.toLowerCase().endsWith('.pdf')) throw new Error('Only PDF files are supported.');
    if (file.size > 8*1024*1024) throw new Error('Each PDF must be 8 MB or smaller.');
    const bytes = await file.arrayBuffer();
    let chunk = '';
    const raw = new Uint8Array(bytes);
    for (let i=0;i<raw.length;i+=8192) chunk += String.fromCharCode(...raw.subarray(i,i+8192));
    return btoa(chunk);
  };

  $('runButton').addEventListener('click', async () => {
    $('errorBox').classList.add('hidden');
    $('runButton').disabled = true;
    $('runLabel').textContent = 'Checking documents...';
    $('runIcon').textContent = '◌';
    try {
      let data;
      if (activeTab === 'sample') data = {mode:'sample',sample:$('sampleCase').value,extra_case:$('extraCase').value};
      else if (activeTab === 'text') data = {mode:'text',invoice_text:$('invoiceText').value, packing_text:$('packingText').value,bol_text:$('bolText').value,coo_text:$('cooText').value};
      else {
        const inv = $('invoiceFile').files?.[0], pack = $('packingFile').files?.[0];
        if (!inv || !pack) throw new Error('Please select both an invoice and a packing list PDF.');
        const [i,p] = await Promise.all([toBase64(inv),toBase64(pack)]);
        data = {mode:'upload',invoice_base64:i,packing_base64:p,invoice_name:inv.name,packing_name:pack.name};
        for (const kind of ['bol','coo']) {
          const f = $(kind+'File').files?.[0];
          if (f) {
            data[kind+'_base64'] = await toBase64(f);
            data[kind+'_name'] = f.name;
          }
        }
      }
      data.use_llm = $('useLlm').checked;
      data.llm_model = $('llmModel').value.trim() || 'qwen2.5:3b';
      const response = await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to review documents.');
      lastReport = result;
      renderReport(result);
      $('results').scrollIntoView({behavior:'smooth',block:'start'});
    } catch(e) {
      $('errorBox').textContent = e.message || 'An unexpected error occurred.';
      $('errorBox').classList.remove('hidden');
    } finally {
      $('runButton').disabled = false;
      $('runLabel').textContent = 'Run document checks';
      $('runIcon').textContent = '↗';
    }
  });

  function renderReport(result) {
    $('emptyState').classList.add('hidden');
    $('reportView').classList.remove('hidden');
    ['exportJson','exportCsv'].forEach(id => $(id).disabled = false);
    const risk = result.status;
    $('riskBanner').className='risk-banner '+risk;
    const llm = result.llm || {status:'disabled'};
    let llmMessage = 'LLM OFF — deterministic rules and basic NLP similarity only.';
    if (llm.status === 'applied') {
      const added = Object.values(llm.added_fields || {}).reduce((n,fields) => n + fields.length, 0);
      llmMessage = 'LOCAL LLM ACTIVE ('+String(llm.model)+') — '+String(llm.documents_processed)+' document(s) processed; '+added+' new field(s) extracted and source-checked. Verify original documents.';
    } else if (llm.status === 'fallback') {
      llmMessage = 'LLM UNAVAILABLE — rule-only review completed. '+String(llm.warning || 'Check Ollama installation.');
    }
    $('llmStatus').textContent = llmMessage;
    $('llmStatus').className = 'llm-status '+(llm.status === 'applied' ? 'active' : llm.status === 'fallback' ? 'fallback' : '');
    const labels = {green:'GREEN — NO ISSUES DETECTED',amber:'AMBER — HUMAN REVIEW NEEDED',red:'RED — INVESTIGATE BEFORE APPROVAL'};
    const notes = {green:'No problems were detected by the checks available in this prototype. Not a customs approval.',amber:'One or more fields need human confirmation before the documents are finalised.',red:'One or more discrepancies or invalid fields were found. Correct them before finalising.'};
    $('riskLabel').textContent=labels[risk]||risk;
    $('riskNote').textContent=notes[risk]||'';
    $('riskIcon').textContent={green:'✓',amber:'!',red:'×'}[risk]||'●';
    $('checks').textContent=result.summary.checks;
    $('passed').textContent=result.summary.passed;
    $('flags').textContent=result.summary.flags;
    $('speed').textContent=result.summary.processing_ms+' ms';
    $('issueCount').textContent=`${result.issues.length} issue${result.issues.length===1?'':'s'}`;
    if (result.issues.length===0) $('issuesList').innerHTML='<div class="no-issues">✓ No issues detected by the implemented checks. This is not a guarantee that documents are legally correct.</div>';
    else $('issuesList').innerHTML=result.issues.map(it => `<div class="issue ${escapeHtml(it.severity)}"><div class="title"><span>${escapeHtml(it.label)} — ${escapeHtml(it.code.replaceAll('_',' ').toLowerCase())}</span><span class="level">${escapeHtml(it.severity).toUpperCase()}</span></div><p>${escapeHtml(it.detail)}</p><p><strong>Recommended action:</strong> ${escapeHtml(it.action)}</p></div>`).join('');
    $('compareRows').innerHTML=result.comparisons.map(it => `<tr><td>${escapeHtml(it.label)}</td><td>${escapeHtml(it.invoice)}</td><td>${escapeHtml(it.packing)}</td><td><span class="status ${escapeHtml(it.status)}">${escapeHtml(it.status)}</span></td></tr>`).join('');
    $('invoiceFields').textContent=JSON.stringify(result.invoice_fields,null,2);
    $('packingFields').textContent=JSON.stringify(result.packing_fields,null,2);
    const extra = result.extra_comparisons || [];
    $('extraResults').classList.toggle('hidden', !extra.length);
    $('extraRows').innerHTML=extra.map(it => `<tr><td>${escapeHtml(it.document)}</td><td>${escapeHtml(it.label)}</td><td>${escapeHtml(it.reference_source)}: ${escapeHtml(it.reference)}</td><td>${escapeHtml(it.document_value)}</td><td><span class="status ${escapeHtml(it.status)}">${escapeHtml(it.status)}</span></td></tr>`).join('');
    $('extraFields').textContent=JSON.stringify(result.extra_fields || {},null,2);
    $('limitations').innerHTML=result.limitations.map(i=>'<li>'+escapeHtml(i)+'</li>').join('');
  }
  function download(name,type,contents) {
    const blob = new Blob([contents],{type});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');a.href=url;a.download=name;a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1500);
  }
  $('exportJson').addEventListener('click',()=>{if(lastReport)download('tradecheck_review.json','application/json',JSON.stringify(lastReport,null,2));});
  $('exportCsv').addEventListener('click',()=>{
    if (!lastReport) return;
    const csvEscape=s => {
      let t=String(s??'');
      if (/^[=+@\-\t\r]/.test(t)) t="'"+t; // avoid spreadsheet formula injection
      return '"'+t.replaceAll('"','""')+'"';
    };
    let rows=[['Document','Field','Reference','Observed value','Status']];
    lastReport.comparisons.forEach(i=>rows.push(['Invoice vs packing list',i.label,i.invoice,i.packing,i.status]));
    (lastReport.extra_comparisons || []).forEach(i=>rows.push([i.document,i.label,i.reference,i.document_value,i.status]));
    download('tradecheck_comparison.csv','text/csv;charset=utf-8','\ufeff'+rows.map(row=>row.map(csvEscape).join(',')).join('\r\n'));
  });
})();
