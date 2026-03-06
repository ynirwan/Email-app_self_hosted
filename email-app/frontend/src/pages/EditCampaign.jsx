// src/pages/EditCampaign.jsx
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import API from '../api';
import { Monitor, Smartphone, Tablet } from 'lucide-react';

export default function EditCampaign() {
  /* ---------- routing & id ---------- */
  const { id } = useParams();
  const navigate = useNavigate();

  /* ---------- wizard step ---------- */
  const [step, setStep] = useState(1);          // 1=Content 2=Audience+Template 3=Preview

  /* ---------- form fields ---------- */
  const [title,        setTitle]        = useState('');
  const [subject,      setSubject]      = useState('');
  const [senderName,   setSenderName]   = useState('');
  const [senderEmail,  setSenderEmail]  = useState('');
  const [replyTo,      setReplyTo]      = useState('');
  const isValidEmail = (e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);

  /* ---------- template / preview ---------- */
  const [templates,        setTemplates]        = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [previewHtml,      setPreviewHtml]      = useState('');
  const [dynamicFields,    setDynamicFields]    = useState([]);
  const [fieldMap,         setFieldMap]         = useState({});
  const [fallbackValues,   setFallbackValues]   = useState({});
  const [previewMode,      setPreviewMode]      = useState('desktop');   // desktop | tablet | mobile

  /* ---------- audience (lists & segments) ---------- */
  const [lists,            setLists]            = useState([]);
  const [selectedLists,    setSelectedLists]    = useState([]);
  const [segments,         setSegments]         = useState([]);
  const [selectedSegments, setSelectedSegments] = useState([]);
  const [audienceMode,     setAudienceMode]     = useState('lists');     // lists | segments | both
  const [loadingLists,     setLoadingLists]     = useState(false);
  const [loadingSegments,  setLoadingSegments]  = useState(false);

  /* ---------- available fields ---------- */
  const [availableFields, setAvailableFields] = useState({ universal:[], standard:[], custom:[] });

  /* ---------- status / UX ---------- */
  const [campaignStatus, setCampaignStatus] = useState('draft');
  const [loadingCampaign, setLoadingCampaign] = useState(true);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [error, setError] = useState(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [campaignFound, setCampaignFound] = useState(true);

  /* ---------- test email ---------- */
  const [testEmail,  setTestEmail]  = useState('');
  const [sendingTest,setSendingTest]= useState(false);
  const [testSent,   setTestSent]   = useState(false);

  /* ------------------------------------------------------------------ */
  /*                       side-effect: initial fetch                   */
  /* ------------------------------------------------------------------ */
  useEffect(() => {
    fetchCampaign();          // pulls existing campaign (title, lists, fieldMap, etc.)
    fetchLists();
    fetchSegments();
    fetchTemplates();
  }, [id]);

  /* ------------------------------------------------------------------ */
  /*                 side-effect: handle template change                */
  /* ------------------------------------------------------------------ */
  useEffect(() => {
    if (!selectedTemplate) {
      setPreviewHtml('');
      setDynamicFields([]);
      return;
    }
    setPreviewHtml(extractHtmlFromTemplate(selectedTemplate));

    API.get(`/templates/${selectedTemplate._id || selectedTemplate.id}/fields`)
      .then(res => setDynamicFields(res.data))
      // KEEP fieldMap on edit; do NOT reset here
      .catch(() => setDynamicFields([]));
  }, [selectedTemplate]);

  /* ------------------------------------------------------------------ */
  /*            side-effect: refresh available fields on change         */
  /* ------------------------------------------------------------------ */
  useEffect(() => {
    if (selectedLists.length || selectedSegments.length) {
      getAllColumns().then(setAvailableFields).catch(console.error);
    } else {
      setAvailableFields({ universal:[], standard:[], custom:[] });
    }
  }, [selectedLists, selectedSegments]);

  /* ==================================================================
     ========================  FETCH HELPERS  =========================
     ==================================================================*/
  const fetchCampaign = async () => {
    try {
      setLoadingCampaign(true);
      const res = await API.get(`/campaigns/${id}`);
      const c = res.data;

      /* ---- hydrate form ---- */
      setTitle(c.title || '');
      setSubject(c.subject || '');
      setSenderName(c.sender_name || '');
      setSenderEmail(c.sender_email || '');
      setReplyTo(c.reply_to || '');

      /* audience */
      setSelectedLists(c.target_lists || []);
      setSelectedSegments(c.target_segments || []);
      if ((c.target_lists||[]).length && (c.target_segments||[]).length) setAudienceMode('both');
      else if ((c.target_segments||[]).length)                             setAudienceMode('segments');

      /* status & mapping */
      setCampaignStatus(c.status || 'draft');
      setFieldMap(c.field_map || {});
      setFallbackValues(c.fallback_values || {});

      /* load template later */
      if (c.template_id) window.pendingTemplateId = c.template_id;
    } catch (err) {
      if (err.response?.status === 404) { setCampaignFound(false); setError('Campaign not found'); }
      else setError('Failed to load campaign data');
    } finally { setLoadingCampaign(false); }
  };

  const fetchLists = async () => {
    try {
      setLoadingLists(true);
      const fresh = (await API.get('/subscribers/lists')).data;
      setLists(fresh);
      /* prune removed lists */
      setSelectedLists(prev => prev.filter(id => fresh.some(l => l._id === id)));
    } finally { setLoadingLists(false); }
  };

  const fetchSegments = async () => {
    try {
      setLoadingSegments(true);
      const segData = (await API.get('/segments')).data?.segments || (await API.get('/segments')).data;
      const segs = Array.isArray(segData) ? segData : [];
      setSegments(segs);
      /* prune removed segments */
      setSelectedSegments(prev => prev.filter(id => segs.some(s => s._id === id)));
    } finally { setLoadingSegments(false); }
  };

  const fetchTemplates = async () => {
    try {
      setLoadingTemplates(true);
      const all = (await API.get('/templates')).data;
      setTemplates(all);
      if (window.pendingTemplateId) {
        const t = all.find(t => (t._id||t.id) === window.pendingTemplateId);
        if (t) setSelectedTemplate(t);
        delete window.pendingTemplateId;
      }
    } finally { setLoadingTemplates(false); }
  };

  /* ==================================================================
     =====================  LOCAL HELPERS / UTILS  ====================
     ==================================================================*/
  const extractHtmlFromTemplate = (t) => {
    if (!t) return '';
    const j = t.content_json || {};

    if (j.mode === 'html' && j.content)           return j.content;
    if (j.mode === 'drag-drop' && j.blocks)       return j.blocks.map(b => b.content||'').join('\n');
    if (j.mode === 'visual' && j.content)         return j.content;
    if (t.html)                                   return t.html;

    /* legacy Unlayer */
    try {
      let out='';
      j.body?.rows.forEach(r => r.columns?.forEach(col => col.contents?.forEach(c => {
        if (c.type==='html' && c.values?.html) out+=c.values.html+'\n';
      })));
      return out || '<p>No preview available</p>';
    } catch { return '<p>No preview available</p>'; }
  };

  const getAllColumns = async () => {
    const payload = {};
    if (selectedLists.length)    payload.listIds    = selectedLists;
    if (selectedSegments.length) payload.segmentIds = selectedSegments;

    try { return (await API.post('/subscribers/analyze-fields', payload)).data; }
    catch { return { universal:['email'], standard:[], custom:[] }; }
  };

  /* totals */
  const getTotalRecipients = () => {
    const listCount = lists
      .filter(l => selectedLists.includes(l._id))
      .reduce((s,l) => s + (l.count||0), 0);

    const segCount  = segments
      .filter(s => selectedSegments.includes(s._id))
      .reduce((s,g) => s + (g.subscriber_count||0), 0);

    return listCount + segCount;
  };

  /* ==================================================================
     =========================  VALIDATION  ===========================
     ==================================================================*/
  const validateStep1 = () =>
    title.trim() && subject.trim() && senderEmail.trim() && isValidEmail(senderEmail);

  const validateStep2 = () => {
    if (!selectedTemplate) return false;
    if (!selectedLists.length && !selectedSegments.length) return false;
    return dynamicFields.every(f => fieldMap[f] && fieldMap[f].trim());
  };

  /* ==================================================================
     ========================  UI EVENT HANDLERS  =====================
     ==================================================================*/
  const handleListToggle    = (id) => setSelectedLists(
    prev => prev.includes(id) ? prev.filter(x=>x!==id) : [...prev,id]
  );
  const handleSegmentToggle = (id) => setSelectedSegments(
    prev => prev.includes(id) ? prev.filter(x=>x!==id) : [...prev,id]
  );
  const handleFieldChange   = (f,v)=> setFieldMap(prev => ({...prev,[f]:v}));

  const handleUpdateCampaign = async () => {
    if (!validateStep1() || !validateStep2()) {
      alert('Please complete required fields, select audience/template, map all dynamic fields.');
      return;
    }
    if (campaignStatus==='sent' && !window.confirm(
      'This campaign was already sent. Update anyway? (Sent emails are unaffected)')) return;

    try {
      setIsUpdating(true); setError(null);
      const payload = {
        title, subject,
        sender_name:  senderName,
        sender_email: senderEmail,
        reply_to:     replyTo,
        target_lists: selectedLists,
        target_segments: selectedSegments,
        template_id:  selectedTemplate._id || selectedTemplate.id,
        field_map:    fieldMap,
        fallback_values: fallbackValues,
        status:       campaignStatus
      };
      const res = await API.put(`/campaigns/${id}`, payload);
      setSuccessMsg(
        `Campaign updated! Targeting ${res.data.computed_target_count} subscribers.`
      );
      setTimeout(()=>navigate('/campaigns'), 2000);
    } catch(e){
      setError(e.response?.data?.detail || 'Update failed');
    } finally { setIsUpdating(false); }
  };

  /* ---------- send test email ---------- */
  const sendTestEmail = async () => {
    if (!testEmail.trim())      return alert('Enter destination email.');
    if (!selectedTemplate)      return alert('Select a template first.');
    setSendingTest(true); setTestSent(false);
    try {
      await API.post('/campaigns/send-test', {
        campaign_id: id,
        test_email:  testEmail,
        use_custom_data: !!(selectedLists.length || selectedSegments.length),
        selected_list_id: selectedLists[0] || null
      });
      setTestSent(true);
    } catch(e){
      alert(e.response?.data?.detail || 'Test failed');
    } finally { setSendingTest(false); }
  };

  /* ==================================================================
     ==========================  RENDERERS  ===========================
     ==================================================================*/
  const Step1 = () => (
    <div className="space-y-6">
      {campaignStatus==='sent' && (
        <div className="bg-amber-50 p-3 rounded border border-amber-200 text-amber-800 text-sm">
          ⚠️ <strong>Note:</strong> This campaign was already sent—updates won’t affect previously sent emails.
        </div>
      )}

      {/* fields */}
      {[
        {id:'title',  label:'Campaign Name', val:title, set:setTitle, required:true},
        {id:'subject',label:'Email Subject', val:subject,set:setSubject,required:true}
      ].map(f=>(
        <div key={f.id}>
          <label className="block text-sm font-medium mb-1" htmlFor={f.id}>
            {f.label}{f.required && <span className="text-red-600">*</span>}
          </label>
          <input
            id={f.id} type="text" value={f.val} onChange={e=>f.set(e.target.value)}
            className={`w-full px-3 py-2 border rounded ${f.val.trim() ? 'border-gray-300':'border-red-500'}`}
          />
        </div>
      ))}

      {/* sender / reply-to */}
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">Sender Name</label>
          <input className="w-full px-3 py-2 border rounded border-gray-300"
                 value={senderName} onChange={e=>setSenderName(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">
            Sender Email <span className="text-red-600">*</span>
          </label>
          <input type="email" className={`w-full px-3 py-2 border rounded ${isValidEmail(senderEmail)?'border-gray-300':'border-red-500'}`}
                 value={senderEmail} onChange={e=>setSenderEmail(e.target.value)} />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">Reply-To Email</label>
        <input type="email" className="w-full px-3 py-2 border rounded border-gray-300"
               value={replyTo} onChange={e=>setReplyTo(e.target.value)} />
      </div>
    </div>
  );

  const AudienceSummary = () => (
    <div className="bg-blue-50 p-4 rounded">
      <h4 className="font-medium text-blue-800 mb-2">📊 Audience Summary</h4>
      <div className="grid md:grid-cols-3 gap-4">
        <SummaryCard label="Lists Selected"    value={selectedLists.length}/>
        <SummaryCard label="Segments Selected" value={selectedSegments.length}/>
        <SummaryCard label="Total Recipients"  value={getTotalRecipients().toLocaleString()}/>
      </div>
    </div>
  );
  const SummaryCard = ({label,value})=>(
    <div><p className="font-semibold text-blue-800">{label}</p><p className="text-lg">{value}</p></div>
  );

  const FieldMapper = () => dynamicFields.length>0 && (
    <div className="mb-4">
      <h4 className="font-semibold mb-2">Map Template Dynamic Fields</h4>
      {dynamicFields.map(field=>(
        <div key={field} className="mb-4 p-4 border rounded bg-gray-50">
          <label className="block mb-2 font-medium">{field} <span className="text-red-600">*</span></label>
          <select
            value={fieldMap[field] || ''} onChange={e=>handleFieldChange(field,e.target.value)}
            className={`w-full px-3 py-2 border rounded mb-2 ${fieldMap[field]?'border-gray-300':'border-red-500'}`}
          >
            <option value="" disabled>Select field mapping…</option>
            {['universal','standard','custom'].map(group=>availableFields[group].length>0 && (
              <optgroup key={group} label={
                group==='universal'?'🌍 Universal Fields':
                group==='standard' ?'⭐ Standard Fields':'🔧 Custom Fields'}>
                {availableFields[group].map(f=>(
                  <option key={f} value={group==='universal'?f:`${group}.${f}`}>
                    {f.replace('_',' ').replace(/\b\w/g,l=>l.toUpperCase())}
                  </option>
                ))}
              </optgroup>
            ))}
            <optgroup label="🔄 Fallback Options">
              <option value="__EMPTY__">Leave Empty</option>
              <option value="__DEFAULT__">Use Default Value</option>
            </optgroup>
          </select>

          {/* fallback input */}
          {fieldMap[field]==='__DEFAULT__' && (
            <input type="text" placeholder="Default value"
                   className="w-full px-3 py-2 border rounded border-blue-300 bg-blue-50"
                   value={fallbackValues[field]||''}
                   onChange={e=>setFallbackValues(p=>({...p,[field]:e.target.value}))}/>
          )}
        </div>
      ))}
    </div>
  );

  const Step2 = () => (
    <>
      <h3 className="text-xl font-semibold mb-4">🎯 Edit Audience & Template</h3>
      <AudienceSummary/>

      {/* mode selector */}
      <div className="my-6">
        <label className="block font-medium mb-3">Target Audience Type</label>
        {['lists','segments','both'].map(mode=>(
          <label key={mode} className="inline-flex items-center mr-6">
            <input type="radio" name="audMode" value={mode}
                   className="mr-2" checked={audienceMode===mode}
                   onChange={e=>setAudienceMode(e.target.value)}/>
            {mode==='lists'?'📋 Lists Only':mode==='segments'?'🎯 Segments Only':'📋🎯 Both'}
          </label>
        ))}
      </div>

      {/* list selection */}
      {(audienceMode==='lists'||audienceMode==='both') && (
        <div className="mb-6">
          <h4 className="font-semibold mb-3">📋 Subscriber Lists</h4>
          <div className="max-h-64 overflow-auto border rounded p-3">
            {loadingLists? 'Loading…' :
              lists.length===0 ? 'No subscriber lists' :
              lists.map(l=>(
                <label key={l._id} className="flex items-center mb-2 cursor-pointer hover:bg-gray-100 p-2 rounded">
                  <input type="checkbox" className="mr-3"
                         checked={selectedLists.includes(l._id)}
                         onChange={()=>handleListToggle(l._id)}/>
                  <span className="font-medium">{l._id}</span>
                  <span className="ml-2 text-gray-500">({l.count||0})</span>
                </label>
              ))}
          </div>
        </div>
      )}

      {/* segment selection */}
      {(audienceMode==='segments'||audienceMode==='both') && (
        <div className="mb-6">
          <h4 className="font-semibold mb-3">🎯 Targeted Segments</h4>
          <div className="max-h-80 overflow-auto border rounded p-3">
            {loadingSegments? 'Loading…' :
             segments.length===0? 'No segments' :
             segments.map(s=>(
              <label key={s._id} className="flex items-start mb-2 cursor-pointer hover:bg-gray-50 p-3 rounded border">
                <input type="checkbox" className="mr-3 mt-1"
                       checked={selectedSegments.includes(s._id)}
                       onChange={()=>handleSegmentToggle(s._id)}/>
                <div className="flex-1">
                  <div className="flex justify-between">
                    <span className="font-semibold text-blue-800">{s.name}</span>
                    <span className="text-sm text-gray-700">{s.subscriber_count?.toLocaleString()||0}</span>
                  </div>
                  <p className="text-sm text-gray-600">{s.description}</p>
                </div>
              </label>
             ))}
          </div>
        </div>
      )}

      {/* template selector */}
      <div className="mb-6">
        <label className="block font-medium mb-1">Select Template <span className="text-red-600">*</span></label>
        <select value={selectedTemplate?(selectedTemplate._id||selectedTemplate.id):''}
                onChange={e=>setSelectedTemplate(
                  templates.find(t=>(t._id||t.id)===e.target.value)||null)}
                className={`w-full px-3 py-2 border rounded ${selectedTemplate?'border-gray-300':'border-red-500'}`}>
          <option value="" disabled>-- Select a Template --</option>
          {loadingTemplates? <option>Loading…</option> :
            templates.map(t=>(
              <option key={t._id||t.id} value={t._id||t.id}>
                {t.name} ({t.content_json?.mode||'legacy'})
              </option>
            ))}
        </select>
      </div>

      <FieldMapper/>

      {/* hybrid warning */}
      {selectedLists.length && selectedSegments.length && (
        <div className="p-3 mb-4 bg-amber-50 border border-amber-200 rounded text-amber-700 text-sm">
          ⚠️ Hybrid Targeting: campaign will reach {getTotalRecipients().toLocaleString()} recipients.
        </div>
      )}
    </>
  );

  const Step3 = () => (
    <>
      <h3 className="text-xl font-semibold mb-4">👀 Preview & Test Updated Campaign</h3>

      {/* test email */}
      <div className="mb-6 p-4 bg-green-50 rounded border border-green-300">
        <label className="block font-medium mb-1">Test Email Address</label>
        <input type="email" className="w-full px-3 py-2 border rounded border-green-300 mb-3"
               value={testEmail} onChange={e=>setTestEmail(e.target.value)} />
        <button onClick={sendTestEmail}
                disabled={sendingTest || !testEmail.trim()}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded disabled:opacity-50">
          {sendingTest?'Sending…':'Send Test Email'}
        </button>
        {testSent && <p className="mt-2 text-green-700">Test email sent!</p>}
      </div>

      {/* campaign summary */}
      <div className="mb-6 p-4 bg-gray-50 rounded">
        <h4 className="font-semibold mb-3">📊 Campaign Summary</h4>
        <div className="grid md:grid-cols-2 gap-4 text-sm">
          <div>
            <p><strong>Campaign:</strong> {title}</p>
            <p><strong>Subject:</strong> {subject}</p>
            <p><strong>Template:</strong> {selectedTemplate?.name || '—'}</p>
            <p><strong>Status:</strong> {campaignStatus}</p>
          </div>
          <div>
            <p><strong>Sender:</strong> {senderName || '—'} &lt;{senderEmail||'—'}&gt;</p>
            <p><strong>Reply-To:</strong> {replyTo || '—'}</p>
            <p><strong>Recipients:</strong> {getTotalRecipients().toLocaleString()}</p>
            <p><strong>Targeting:</strong> {selectedLists.length && selectedSegments.length ?
              'Lists + Segments' : selectedLists.length ? 'Lists' :
              selectedSegments.length ? 'Segments' : 'None'}</p>
          </div>
        </div>
      </div>

      {/* HTML preview w/ device toggle */}
      <div className="mb-6 p-4 border rounded bg-white">
        <div className="flex justify-between items-center mb-4">
          <h4 className="font-semibold">📧 Email Preview</h4>
          <div className="flex gap-2">
            {[
              {m:'desktop',icon:<Monitor size={16}/>},
              {m:'tablet', icon:<Tablet size={16}/>},
              {m:'mobile', icon:<Smartphone size={16}/>},
            ].map(b=>(
              <button key={b.m} onClick={()=>setPreviewMode(b.m)}
                      className={`p-2 rounded ${previewMode===b.m?'bg-blue-600 text-white':'hover:bg-gray-200'}`}>
                {b.icon}
              </button>
            ))}
          </div>
        </div>
        <div className="bg-gray-100 p-4 rounded flex justify-center overflow-auto max-h-[600px]">
          {previewHtml
            ? <div dangerouslySetInnerHTML={{__html:previewHtml}}
                   className={`bg-white shadow-lg ${
                     previewMode==='desktop'?'w-full max-w-4xl':
                     previewMode==='tablet' ?'w-[768px]':'w-[375px]'}`
                   }/>
            : <p className="text-gray-500">Select a template to preview</p>}
        </div>
      </div>
    </>
  );

  /* ==================================================================
     =========================  PAGE SKELETON  ========================
     ==================================================================*/
  if (loadingCampaign) return <p className="text-center mt-10">Loading campaign…</p>;
  if (!campaignFound)   return (
    <div className="text-center mt-10">
      <h2 className="text-2xl text-red-600 font-bold mb-4">❌ Campaign Not Found</h2>
      <button className="bg-blue-600 text-white px-6 py-2 rounded" onClick={()=>navigate('/campaigns')}>← Back</button>
    </div>
  );

  return (
    <div className="max-w-5xl mx-auto p-6 bg-white rounded shadow">
      <h2 className="text-2xl font-bold mb-6">📝 Edit Campaign with Advanced Targeting</h2>

      {error      && <p className="mb-4 text-red-600">{error}</p>}
      {successMsg && <p className="mb-4 text-green-700">{successMsg}</p>}

      {/* step nav */}
      <div className="mb-6 flex gap-4 text-sm font-semibold">
        {[1,2,3].map(n=>(
          <button key={n} disabled={step===n}
                  onClick={()=>setStep(n)}
                  className={`px-4 py-2 rounded ${step===n?'bg-blue-600 text-white':'bg-gray-200 hover:bg-gray-300'}`}>
            Step {n}
          </button>
        ))}
      </div>

      {/* form */}
      <form onSubmit={e=>{
        e.preventDefault();
        if (step===1 && validateStep1())          setStep(2);
        else if (step===2 && validateStep2())     setStep(3);
        else if (step===3)                        handleUpdateCampaign();
      }}>
        {step===1 && <Step1/>}
        {step===2 && <Step2/>}
        {step===3 && <Step3/>}

        {/* nav buttons */}
        <div className="flex justify-between mt-6">
          {step>1 && (
            <button type="button" onClick={()=>setStep(s=>s-1)}
                    className="px-6 py-2 bg-gray-300 hover:bg-gray-400 rounded">← Previous</button>
          )}
          <button type="submit" disabled={
              (step===1 && !validateStep1()) ||
              (step===2 && !validateStep2()) ||
              isUpdating}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50">
            {step<3 ? 'Next →' : isUpdating ? '⏳ Updating…' : '💾 Update Campaign'}
          </button>
        </div>
      </form>
    </div>
  );
}

