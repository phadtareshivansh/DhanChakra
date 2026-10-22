import { t } from '../i18n'
import { useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import api from '../utils/api'
import { IngestionJobStatus } from '../types/api'

export default function Ingest() {
  const [source, setSource] = useState<'mca' | 'gst'>('mca')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [job, setJob] = useState<IngestionJobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showPdf, setShowPdf] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // Agentic PDF flow
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [pdfBusy, setPdfBusy] = useState(false)
  const [docJob, setDocJob] = useState<any>(null)
  const [docError, setDocError] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState<Record<string, string>>({})
  const [docResult, setDocResult] = useState<any>(null)
  const pdfRef = useRef<HTMLInputElement>(null)

  const submitPdf = async () => {
    if (!pdfFile) return
    setPdfBusy(true)
    setDocError(null)
    setDocResult(null)
    setDocJob(null)
    const formData = new FormData()
    formData.append('file', pdfFile)
    try {
      const res = await api.post('/ingest/document', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setDocJob(res.data)
      setConfirmed({})
      if (res.data.extraction) {
        const init: Record<string, string> = {}
        Object.entries(res.data.extraction).forEach(([k, v]: any) => { init[k] = v.value })
        setConfirmed(init)
      }
    } catch (err: any) {
      setDocError(err.response?.data?.detail?.message || 'Upload failed')
    } finally {
      setPdfBusy(false)
    }
  }

  const confirmPdf = async () => {
    if (!docJob?.job_id) return
    setPdfBusy(true)
    try {
      const res = await api.post('/ingest/document/confirm', {
        job_id: docJob.job_id,
        extraction: docJob.extraction,
        confirmed,
      })
      setDocResult(res.data)
    } catch (err: any) {
      setDocError(err.response?.data?.detail?.message || 'Confirm failed')
    } finally {
      setPdfBusy(false)
    }
  }

  const confBadge = (conf: number) => (
    <span className={`px-1.5 py-0.5 rounded text-micro font-bold ${conf >= 0.8 ? 'bg-success-500/20 text-success-500' : 'bg-amber/20 text-amber'}`}>
      {Math.round(conf * 100)}%
    </span>
  )

  const poll = async (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/ingest/status/${jobId}`)
        setJob(res.data)
        if (['completed', 'partial_success', 'failed'].includes(res.data.status)) {
          clearInterval(interval)
        }
      } catch {
        clearInterval(interval)
      }
    }, 1500)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return
    const formData = new FormData()
    formData.append('source', source)
    formData.append('file', file)
    setUploading(true)
    setError(null)
    setJob(null)
    try {
      const res = await api.post('/ingest/csv', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setJob({ ...res.data, records_processed: 0, records_failed: 0, started_at: new Date().toISOString() } as unknown as IngestionJobStatus)
      poll(res.data.job_id)
    } catch (err: any) {
      setError(err.response?.data?.detail?.message || t('Upload failed'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl font-bold">{t('Data Ingestion')}</h1>
        <p className="text-sm text-text-secondary mt-1">
          {t('Load structured company (MCA) or transaction (GST) CSV data into the graph. Demo-only admin flow.')}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="panel p-5">
          <h2 className="text-lg font-semibold mb-4">{t('Structured data (CSV)')}</h2>
          <div className="flex gap-2 mb-4">
            <button
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${source === 'mca' ? 'bg-accent text-white' : 'bg-raised text-text-secondary hover:text-text-primary'}`}
              onClick={() => setSource('mca')}
            >
              {t('MCA companies')}
            </button>
            <button
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${source === 'gst' ? 'bg-accent text-white' : 'bg-raised text-text-secondary hover:text-text-primary'}`}
              onClick={() => setSource('gst')}
            >
              {t('GST transactions')}
            </button>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div className="border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-accent-ring transition-colors" onClick={() => fileRef.current?.click()}>
              {file ? (
                <div>
                  <div className="font-mono text-data">{file.name}</div>
                  <div className="text-xs text-text-secondary mt-1">{file.size.toLocaleString()} {t('bytes')}</div>
                </div>
              ) : (
                <div className="text-text-secondary text-sm">
                  <div className="text-2xl mb-1">⇪</div>
                  {t('Click to choose a')} {source === 'mca' ? 'company' : 'transaction'} {t('CSV file')}
                </div>
              )}
              <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            </div>

            {source === 'mca' && (
              <div className="text-xs text-text-secondary bg-raised rounded-lg p-3">
                {t('Expected columns:')} <span className="mono-id">{t('CIN, GSTIN, Company Name, Date of Incorporation, Status, Authorized Capital, Paid Up Capital, NIC Code, ROC')}</span>
              </div>
            )}
            {source === 'gst' && (
              <div className="text-xs text-text-secondary bg-raised rounded-lg p-3">
                {t('Expected columns:')} <span className="mono-id">{t('GSTIN Seller, GSTIN Buyer, Invoice Value, Invoice Date, Return Period')}</span>
              </div>
            )}

            <button className="btn-primary w-full" disabled={!file || uploading}>
              {uploading ? 'Uploading…' : 'Upload & ingest'}
            </button>
          </form>

          {error && (
            <div className="mt-4 px-4 py-3 rounded-lg bg-risk-critical/10 border border-risk-critical/30 text-risk-critical text-sm">{error}</div>
          )}

          {job && (
            <div className="mt-4 panel-raised p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="micro-label">{t('Job')} {job.id.slice(0, 8)}</span>
                <span className={`px-2 py-0.5 rounded-full text-micro font-bold ${job.status === 'completed' ? 'bg-success-500/20 text-success-500' : job.status === 'failed' ? 'bg-risk-critical/20 text-risk-critical' : 'bg-amber/20 text-amber'}`}>
                  {job.status}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="text-text-secondary">{t('Rows ingested')}</div>
                <div className="font-mono text-right">{job.records_processed}</div>
                <div className="text-text-secondary">{t('Rows failed')}</div>
                <div className="font-mono text-right text-risk-critical">{job.records_failed}</div>
              </div>
              {job.error_log && <div className="mt-2 text-xs text-text-secondary">{job.error_log}</div>}
              <Link to="/" className="mt-3 inline-block text-sm text-accent-ring hover:underline">{t('See updated dashboard →')}</Link>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="panel p-5">
            <h2 className="text-lg font-semibold mb-2">{t('Document (PDF) — agentic extraction')}</h2>
            <p className="text-sm text-text-secondary mb-3">
              {t('Phase 5: the extraction agent reads an MCA-style filing PDF and pulls out')}
              <span className="mono-id"> {t('director, DIN, address, shareholding')}</span> {t('with per-field confidence. Low-confidence fields (amber) are held for your review — nothing is committed until you confirm.')}
            </p>

            <div className="border-2 border-dashed border-border rounded-lg p-5 text-center cursor-pointer hover:border-accent-ring transition-colors mb-3" onClick={() => pdfRef.current?.click()}>
              {pdfFile ? (
                <div className="font-mono text-data">{pdfFile.name}</div>
              ) : (
                <div className="text-text-secondary text-sm">
                  <div className="text-2xl mb-1">⇪</div>
                  {t('Choose an MCA filing PDF')}
                </div>
              )}
              <input ref={pdfRef} type="file" accept=".pdf" className="hidden" onChange={(e) => setPdfFile(e.target.files?.[0] || null)} />
            </div>
            <button className="btn-primary w-full" disabled={!pdfFile || pdfBusy} onClick={submitPdf}>
              {pdfBusy ? 'Extracting…' : 'Extract with agent'}
            </button>

            {docError && (
              <div className="mt-3 px-4 py-3 rounded-lg bg-risk-critical/10 border border-risk-critical/30 text-risk-critical text-sm">{docError}</div>
            )}

            {docJob?.extraction && (
              <div className="mt-4 panel-raised p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="micro-label">{t('Extraction ·')} {docJob.backend} {t('backend')}</span>
                  {docJob.needs_review.length > 0 ? (
                    <span className="px-2 py-0.5 rounded-full text-micro font-bold bg-amber/20 text-amber">{t('needs review')}</span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full text-micro font-bold bg-success-500/20 text-success-500">{t('high confidence')}</span>
                  )}
                </div>
                <div className="space-y-2">
                  {Object.entries(docJob.extraction).map(([field, entry]: [string, any]) => {
                    const review = docJob.needs_review.includes(field)
                    return (
                      <div key={field} className="flex items-center gap-2">
                        <span className="w-40 shrink-0 text-xs text-text-secondary">{field}</span>
                        <input
                          className={`input flex-1 text-xs ${review ? 'border-amber/60' : ''}`}
                          value={confirmed[field] ?? ''}
                          onChange={(e) => setConfirmed({ ...confirmed, [field]: e.target.value })}
                        />
                        {confBadge(entry.confidence)}
                      </div>
                    )
                  })}
                </div>
                <button className="btn-primary w-full mt-4" onClick={confirmPdf} disabled={pdfBusy}>
                  {pdfBusy ? 'Committing…' : 'Confirm & create entities'}
                </button>
              </div>
            )}

            {docResult && (
              <div className="mt-3 panel-raised p-4 text-sm">
                <div className="text-success-500 font-semibold mb-2">{t('✓ Committed to graph')}</div>
                <div className="text-xs text-text-secondary space-y-1">
                  <div>{t('Company:')} {docResult.created.companies.join(', ') || '—'}</div>
                  <div>{t('Directors:')} {docResult.created.directors.join(', ') || '—'}</div>
                  <div>{t('Addresses:')} {docResult.created.addresses.join(', ') || '—'}</div>
                </div>
              </div>
            )}

            {showPdf && (
              <div className="mt-3 text-xs text-text-secondary bg-raised rounded-lg p-3">
                {t('The agent runs a deterministic rule backend by default (')}<span className="mono-id">{t('AGENT_INGEST_BACKEND=rules')}</span>{t('); an optional OpenAI-compatible LLM backend is used when')}{' '}
                <span className="mono-id">{t('AGENT_LLM_URL')}</span> {t('is configured. Either way the module never blocks the core demo.')}
              </div>
            )}
            <button className="btn-secondary w-full mt-3" onClick={() => setShowPdf(!showPdf)}>
              {showPdf ? 'Hide backend notes' : 'Backend notes'}
            </button>
          </div>

          <div className="panel p-5">
            <h2 className="text-lg font-semibold mb-3">{t('Run graph analytics')}</h2>
            <p className="text-sm text-text-secondary mb-3">
              {t('Detect & materialize cycles, Louvain communities, centrality, risk scores, and entity-resolution edges (')}{'Phases 1–3'}).
            </p>
            <button
              className="btn-primary"
              onClick={async () => {
                try {
                  const res = await api.post('/analytics/structural')
                  alert(JSON.stringify(res.data.summary || res.data, null, 2))
                } catch (err: any) {
                  alert('Failed: ' + (err.response?.data?.detail?.message || err.message))
                }
              }}
            >
              {t('⚙ Run structural analytics')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}