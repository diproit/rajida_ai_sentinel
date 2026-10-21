import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Play,
  Pause,
  Send,
  Edit3,
  RefreshCw,
  Mail,
  Smartphone,
  ShieldCheck,
  TrendingUp,
  User,
  MapPin,
  ExternalLink,
  ChevronRight,
  Sparkles,
  X,
  Zap,
  Radio,
  Activity,
  Layers,
  ArrowRight
} from 'lucide-react';

const API_BASE = ''; // Uses Vite proxy to backend http://127.0.0.1:8001

export default function App() {
  const [activeTab, setActiveTab] = useState('bottlenecks'); // 'bottlenecks' | 'approvals' | 'history'
  const [bottlenecksData, setBottlenecksData] = useState(null);
  const [interventionsData, setInterventionsData] = useState(null);
  const [metricsData, setMetricsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [editingIntervention, setEditingIntervention] = useState(null);
  const [editSubject, setEditSubject] = useState('');
  const [editBody, setEditBody] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [approvingId, setApprovingId] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [toast, setToast] = useState(null);

  // Real-Time Webhook & Telemetry State
  const [sseConnected, setSseConnected] = useState(false);
  const [webhookEvents, setWebhookEvents] = useState([]);
  const [activeWebhookNotice, setActiveWebhookNotice] = useState(null);
  const [highlightedCaseId, setHighlightedCaseId] = useState(null);
  const [showWebhookModal, setShowWebhookModal] = useState(false);
  const [simulatingWebhook, setSimulatingWebhook] = useState(false);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  const fetchDashboardData = async () => {
    try {
      const [botRes, intRes, metRes] = await Promise.all([
        fetch(`${API_BASE}/api/dashboard/bottlenecks`),
        fetch(`${API_BASE}/api/dashboard/interventions`),
        fetch(`${API_BASE}/api/dashboard/metrics`)
      ]);

      if (botRes.ok) setBottlenecksData(await botRes.json());
      if (intRes.ok) setInterventionsData(await intRes.json());
      if (metRes.ok) setMetricsData(await metRes.json());
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
      showToast('Could not reach backend API. Ensure server is running on port 8001.', 'error');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();

    // Subscribe to real-time Sentinel events via Server-Sent Events (SSE)
    let eventSource;
    try {
      eventSource = new EventSource(`${API_BASE}/api/dashboard/events`);

      eventSource.onopen = () => {
        setSseConnected(true);
      };

      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'CONNECTED') {
            setSseConnected(true);
            return;
          }
          if (payload.type) {
            setSseConnected(true);

            // Record event in live stream buffer
            const newEvent = {
              id: payload.data?.event_id || `evt_${Date.now()}`,
              type: payload.type,
              caseNumber: payload.data?.case_number,
              data: payload.data,
              receivedAt: new Date().toLocaleTimeString(),
            };
            setWebhookEvents((prev) => [newEvent, ...prev.slice(0, 19)]);

            // Highlight affected card in UI
            if (payload.data?.case_number) {
              setHighlightedCaseId(payload.data.case_number);
              setTimeout(() => setHighlightedCaseId(null), 7000);
            }

            // Display persistent banner notice
            setActiveWebhookNotice(payload);
            setTimeout(() => {
              setActiveWebhookNotice((curr) => (curr === payload ? null : curr));
            }, 8000);

            // Auto-refresh telemetry
            fetchDashboardData();

            if (payload.type === 'STATUS_CHANGED') {
              showToast(`⚡ Webhook received: Case ${payload.data?.case_number || ''} status → ${payload.data?.new_status || 'updated'}`);
            } else if (payload.type === 'UNRESPONSIVE_PARTY' || payload.type === 'SLA_DELAY_WARNING') {
              showToast(`⚡ Alert: ${payload.type} on Case ${payload.data?.case_number || ''}`, 'error');
            }
          }
        } catch (e) {
          console.debug('SSE parse error', e);
        }
      };

      eventSource.onerror = () => {
        setSseConnected(false);
      };
    } catch (err) {
      console.debug('SSE connection skipped:', err);
    }

    return () => {
      if (eventSource) eventSource.close();
    };
  }, []);

  // Keyboard accessibility: Close modal on Escape key & manage scroll lock
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setEditingIntervention(null);
        setShowWebhookModal(false);
      }
    };
    if (editingIntervention || showWebhookModal) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
    } else {
      document.body.style.overflow = 'auto';
    }
    return () => {
      document.body.style.overflow = 'auto';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [editingIntervention, showWebhookModal]);

  const handleSimulateWebhook = async (type = 'UNRESPONSIVE_PARTY') => {
    setSimulatingWebhook(true);
    try {
      const sampleCaseNo = 'MK-88A9C12E';
      const payload = {
        event_id: `evt_sim_${Date.now()}`,
        timestamp: new Date().toISOString(),
        source_system: 'mekamu_mowheel',
        environment: 'production',
        event_type: type,
        severity: type === 'STATUS_CHANGED' ? 'MEDIUM' : 'CRITICAL',
        category: type === 'STATUS_CHANGED' ? 'STATUS_TRANSITION' : 'VALUER_UNRESPONSIVE',
        application: {
          id: 'c88f9e20-7214-41bd-8c43-4c919d6756ec',
          application_no: sampleCaseNo,
          status: 'VALUATION_AND_INVESTIGATION_PROCESSING',
          branch_name: 'Kandy Branch',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        assigned_party: {
          role: 'VALUER',
          user_id: 'usr_valuer_01',
          name: 'Sunil Perera',
          phone: '0771234567',
          company_name: 'Lanka Valuers Ltd',
          assigned_at: new Date().toISOString(),
        },
        metrics: {
          elapsed_seconds: 7800,
          sla_threshold_seconds: 7200,
          delay_seconds: 600,
        },
        details: {
          previous_status: 'DRAFT',
          new_status: 'VALUATION_AND_INVESTIGATION_PROCESSING',
          trigger_actor: 'fo@mekamu.com',
          message: 'Valuer Sunil Perera has not submitted a valuation report within the 2-hour SLA window.',
        },
      };

      const res = await fetch(`${API_BASE}/api/v1/webhooks/digivaluer`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer dev_webhook_secret_key_2026',
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        showToast(`Simulated ${type} webhook dispatched successfully!`);
      } else {
        showToast('Webhook simulation request failed', 'error');
      }
    } catch (err) {
      showToast('Error sending simulated webhook', 'error');
    } finally {
      setSimulatingWebhook(false);
    }
  };

  const handleManualScan = async () => {
    setScanning(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/workflows/scan-now`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        showToast(`Scan complete: ${data.actionable_overdue_cases} bottlenecks detected, ${data.drafts_created} reminders drafted.`);
        await fetchDashboardData();
      } else {
        showToast('Scan request failed.', 'error');
      }
    } catch (err) {
      showToast('Failed to trigger scan.', 'error');
    } finally {
      setScanning(false);
    }
  };

  const handleApprove = async (id) => {
    setApprovingId(id);
    try {
      const res = await fetch(`${API_BASE}/api/dashboard/interventions/${id}/approve`, {
        method: 'POST'
      });
      if (res.ok) {
        showToast(`Intervention #${id} successfully approved and dispatched!`);
        await fetchDashboardData();
      } else {
        showToast(`Approval failed for #${id}`, 'error');
      }
    } catch (err) {
      showToast('Error approving intervention', 'error');
    } finally {
      setApprovingId(null);
    }
  };

  const openEditModal = (inv) => {
    setEditingIntervention(inv);
    let subject = '';
    let body = inv.drafted_message || '';
    if (body.startsWith('Subject: ')) {
      const parts = body.split('\n\n');
      subject = parts[0].replace('Subject: ', '').trim();
      body = parts.slice(1).join('\n\n');
    } else {
      subject = `Valuation Update: Stage SLA Notice for Case ${inv.case_id}`;
    }
    setEditSubject(subject);
    setEditBody(body);
  };

  const handleSaveEdit = async (autoApprove = false) => {
    if (!editingIntervention) return;
    setSavingEdit(true);
    const combinedMessage = editSubject ? `Subject: ${editSubject}\n\n${editBody}` : editBody;
    try {
      const res = await fetch(`${API_BASE}/api/dashboard/interventions/${editingIntervention.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ drafted_message: combinedMessage })
      });
      if (res.ok) {
        if (autoApprove) {
          await handleApprove(editingIntervention.id);
        } else {
          showToast(`Intervention #${editingIntervention.id} updated successfully.`);
          await fetchDashboardData();
        }
        setEditingIntervention(null);
      } else {
        showToast('Failed to save drafted changes', 'error');
      }
    } catch (err) {
      showToast('Error saving intervention draft', 'error');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleTogglePause = async (caseId) => {
    try {
      const res = await fetch(`${API_BASE}/api/dashboard/cases/${caseId}/pause-agent`, {
        method: 'POST'
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`Case ${caseId}: ${data.is_paused ? 'Monitoring Paused' : 'Monitoring Resumed'}`);
        await fetchDashboardData();
      }
    } catch (err) {
      showToast('Failed to toggle monitoring state', 'error');
    }
  };

  const draftedInterventions = interventionsData?.interventions?.filter(i => i.status === 'DRAFTED') || [];
  const sentInterventions = interventionsData?.interventions?.filter(i => i.status === 'SENT') || [];

  return (
    <div className="min-h-screen bg-[#09090b] text-[#fafafa] flex flex-col font-sans">
      {/* Toast Notification */}
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl shadow-2xl text-xs font-medium border flex items-center gap-2.5 transition-all backdrop-blur-md ${
          toast.type === 'error'
            ? 'bg-rose-950/90 text-rose-200 border-rose-800/80 shadow-rose-950/40'
            : 'bg-emerald-950/90 text-emerald-200 border-emerald-800/80 shadow-emerald-950/40'
        }`}>
          {toast.type === 'error' ? <AlertTriangle className="w-4 h-4 text-rose-400" /> : <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
          <span>{toast.message}</span>
        </div>
      )}

      {/* Top Navbar */}
      <header className="border-b border-[#27272a] bg-[#0c0c0f]/80 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center shadow-lg shadow-emerald-500/20 border border-emerald-400/30">
              <ShieldCheck className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-bold text-base sm:text-lg text-zinc-100 tracking-tight">DigiValuer Sentinel</h1>
                <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
                  Ops Console
                </span>
              </div>
              <p className="text-xs text-zinc-400">Autonomous Workflow Bottleneck Watchdog</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Live Webhook Ingestion Indicator */}
            <button
              onClick={() => setShowWebhookModal(true)}
              className={`px-3 py-1.5 rounded-lg border text-xs font-medium flex items-center gap-2 transition cursor-pointer ${
                sseConnected
                  ? 'bg-emerald-950/50 text-emerald-300 border-emerald-800/60 hover:bg-emerald-900/40 shadow-sm'
                  : 'bg-zinc-900/80 text-zinc-400 border-zinc-800 hover:bg-zinc-800'
              }`}
              title="Click to inspect real-time webhook ingestion log"
            >
              <span className="relative flex h-2 w-2">
                {sseConnected && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                )}
                <span className={`relative inline-flex rounded-full h-2 w-2 ${sseConnected ? 'bg-emerald-400' : 'bg-zinc-500'}`}></span>
              </span>
              <Zap className="w-3.5 h-3.5 text-emerald-400" />
              <span className="hidden sm:inline">{sseConnected ? 'Live Webhook Sync' : 'Sync Disconnected'}</span>
              {webhookEvents.length > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-300 text-[10px] font-mono border border-emerald-500/30">
                  {webhookEvents.length}
                </span>
              )}
            </button>

            <button
              onClick={() => { setRefreshing(true); fetchDashboardData(); }}
              disabled={refreshing}
              className="p-2 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 rounded-lg transition border border-transparent hover:border-zinc-700"
              title="Refresh Data"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin text-emerald-400' : ''}`} />
            </button>
            <button
              onClick={handleManualScan}
              disabled={scanning}
              className="sentinel-btn-primary text-xs"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
              <span>{scanning ? 'Scanning Pipeline...' : 'Run Sentinel Scan'}</span>
            </button>
          </div>
        </div>

        {/* Tab Navigation (Underline Style adhering to React Framework guide) */}
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 flex gap-8 border-t border-[#1e1e24] text-xs">
          <button
            onClick={() => setActiveTab('bottlenecks')}
            className={`py-3.5 font-medium border-b-2 flex items-center gap-2 transition ${
              activeTab === 'bottlenecks'
                ? 'border-emerald-500 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200 hover:border-zinc-700'
            }`}
          >
            <span>Bottleneck Map</span>
            {bottlenecksData?.summary?.total_bottlenecks > 0 && (
              <span className="sentinel-badge-rose font-mono">
                {bottlenecksData.summary.total_bottlenecks}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('approvals')}
            className={`py-3.5 font-medium border-b-2 flex items-center gap-2 transition ${
              activeTab === 'approvals'
                ? 'border-emerald-500 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200 hover:border-zinc-700'
            }`}
          >
            <span>Pending Approvals</span>
            {draftedInterventions.length > 0 && (
              <span className="sentinel-badge-amber font-mono">
                {draftedInterventions.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('history')}
            className={`py-3.5 font-medium border-b-2 flex items-center gap-2 transition ${
              activeTab === 'history'
                ? 'border-emerald-500 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200 hover:border-zinc-700'
            }`}
          >
            <span>Intervention History</span>
            <span className="px-2 py-0.5 text-[11px] rounded-full bg-zinc-800 text-zinc-400 font-mono border border-zinc-700">
              {sentInterventions.length}
            </span>
          </button>
        </div>
      </header>

      {/* Real-Time Webhook Flash Banner */}
      {activeWebhookNotice && (
        <div className="bg-gradient-to-r from-emerald-950/90 via-zinc-900 to-zinc-950 border-b border-emerald-800/50 px-4 sm:px-6 lg:px-8 py-2.5 flex items-center justify-between text-xs transition-all shadow-lg shadow-emerald-950/20">
          <div className="flex items-center gap-3">
            <span className="p-1.5 rounded-md bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center">
              <Zap className="w-4 h-4 animate-bounce" />
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-emerald-300">Live Webhook Received:</span>
              <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded bg-zinc-800 text-zinc-200 border border-zinc-700">
                {activeWebhookNotice.type}
              </span>
              <span className="text-zinc-300">
                Case <strong className="text-zinc-100 font-mono">{activeWebhookNotice.data?.case_number}</strong>
                {activeWebhookNotice.data?.new_status && ` → ${activeWebhookNotice.data.new_status}`}
                {activeWebhookNotice.data?.category && ` (${activeWebhookNotice.data.category})`}
              </span>
              <span className="text-[11px] text-emerald-400/80 font-mono">
                • Telemetry auto-refreshed
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowWebhookModal(true)}
              className="text-xs text-emerald-400 hover:text-emerald-300 underline font-medium cursor-pointer"
            >
              Inspect Event
            </button>
            <button
              onClick={() => setActiveWebhookNotice(null)}
              className="p-1 text-zinc-500 hover:text-zinc-300 transition cursor-pointer"
              title="Dismiss"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Main Container */}
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full space-y-8">
        {/* KPI Metrics Summary Cards */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="sentinel-card p-5">
            <div className="flex items-center justify-between text-zinc-400 mb-2">
              <span className="text-xs uppercase tracking-wider font-semibold text-zinc-400">Total Reminders Sent</span>
              <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <Send className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold font-mono text-zinc-100">
              {metricsData?.total_reminders_sent ?? 0}
            </div>
            <p className="text-xs text-zinc-500 mt-1.5">Automated multi-channel interventions</p>
          </div>

          <div className="sentinel-card p-5">
            <div className="flex items-center justify-between text-zinc-400 mb-2">
              <span className="text-xs uppercase tracking-wider font-semibold text-zinc-400">Avg Turnaround Post-Nudge</span>
              <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
                <Clock className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold font-mono text-zinc-100">
              {metricsData?.average_response_time_hours ?? 3.2} <span className="text-sm font-sans font-normal text-zinc-400">hours</span>
            </div>
            <p className="text-xs text-zinc-500 mt-1.5">Recipient action resolution speed</p>
          </div>

          <div className="sentinel-card p-5">
            <div className="flex items-center justify-between text-zinc-400 mb-2">
              <span className="text-xs uppercase tracking-wider font-semibold text-zinc-400">Duration Saved</span>
              <div className="p-2 rounded-lg bg-teal-500/10 text-teal-400 border border-teal-500/20">
                <TrendingUp className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold font-mono text-zinc-100">
              {metricsData?.duration_saved_hours ?? 48.0} <span className="text-sm font-sans font-normal text-zinc-400">hours</span>
            </div>
            <p className="text-xs text-zinc-500 mt-1.5">Cumulative bottleneck time saved</p>
          </div>

          <div className="sentinel-card p-5">
            <div className="flex items-center justify-between text-zinc-400 mb-2">
              <span className="text-xs uppercase tracking-wider font-semibold text-zinc-400">Active Bottlenecks</span>
              <div className="p-2 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
                <AlertTriangle className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold font-mono text-rose-400">
              {bottlenecksData?.summary?.total_bottlenecks ?? 0}
            </div>
            <p className="text-xs text-zinc-500 mt-1.5">
              {bottlenecksData?.summary?.critical_breaches ?? 0} Critical SLA breaches
            </p>
          </div>
        </section>

        {/* Tab 1: Bottleneck Map */}
        {activeTab === 'bottlenecks' && (
          <section className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-zinc-100">Active Workflow Bottlenecks</h2>
                <p className="text-xs text-zinc-400">Valuation cases currently exceeding stage duration SLA thresholds</p>
              </div>
            </div>

            {loading ? (
              <div className="py-20 text-center text-zinc-500 font-mono text-xs">Loading bottleneck telemetry...</div>
            ) : bottlenecksData?.cases?.length === 0 ? (
              <div className="sentinel-card p-12 text-center">
                <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
                <h3 className="text-base font-medium text-zinc-200">All Pipelines Healthy</h3>
                <p className="text-xs text-zinc-500 mt-1">No active cases are currently exceeding stage SLA parameters.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {bottlenecksData?.cases?.map((c) => (
                  <div
                    key={c.case_id}
                    className={`sentinel-card p-5 flex flex-col justify-between transition-all duration-300 ${
                      highlightedCaseId === c.case_id
                        ? 'ring-2 ring-emerald-400 shadow-xl shadow-emerald-500/20 scale-[1.01]'
                        : ''
                    } ${
                      c.is_paused
                        ? 'opacity-60 border-zinc-800'
                        : c.is_breached
                        ? 'border-rose-900/60 hover:border-rose-700/80 shadow-rose-950/10'
                        : 'border-amber-900/60 hover:border-amber-700/80 shadow-amber-950/10'
                    }`}
                  >
                    <div>
                      {/* Card Header */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-zinc-300 px-2 py-0.5 rounded bg-zinc-800/80 border border-zinc-700">
                            {c.case_id}
                          </span>
                          {highlightedCaseId === c.case_id && (
                            <span className="sentinel-badge-emerald animate-pulse">
                              ⚡ Webhook Synced
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          {c.is_paused ? (
                            <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700">
                              Monitoring Paused
                            </span>
                          ) : c.is_breached ? (
                            <span className="sentinel-badge-rose">
                              SLA Breached
                            </span>
                          ) : (
                            <span className="sentinel-badge-amber">
                              SLA Warning
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Property Address */}
                      <div className="flex items-start gap-2 mb-3">
                        <MapPin className="w-4 h-4 text-zinc-400 mt-0.5 shrink-0" />
                        <div>
                          <h4 className="text-sm font-medium text-zinc-200 line-clamp-1">{c.property_address}</h4>
                          <span className="text-xs text-zinc-500">{c.property_type}</span>
                        </div>
                      </div>

                      {/* Stage Telemetry */}
                      <div className="bg-[#121217] rounded-lg p-3.5 border border-[#1e1e24] space-y-2.5 mb-4">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-zinc-400">Current Stage:</span>
                          <span className="font-medium text-zinc-200">{c.stage_name}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-zinc-400">Time in Stage:</span>
                          <span className="font-mono font-semibold text-rose-400">
                            {c.elapsed_hours}h <span className="text-zinc-500 font-normal">/ {c.target_duration_hours}h SLA</span>
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-zinc-400">Next Reminder:</span>
                          <span className="font-mono text-zinc-300">#{c.next_reminder_count}</span>
                        </div>

                        {/* Progress Bar */}
                        <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${c.is_breached ? 'bg-rose-500' : 'bg-amber-400'}`}
                            style={{ width: `${Math.min(100, (c.elapsed_hours / c.target_duration_hours) * 100)}%` }}
                          />
                        </div>
                      </div>

                      {/* Assigned Officer */}
                      <div className="text-xs text-zinc-400 flex items-center justify-between pb-3 border-b border-[#1e1e24]">
                        <span className="flex items-center gap-1.5">
                          <User className="w-3.5 h-3.5 text-zinc-500" />
                          <span>Owner: {c.assigned_owner.name}</span>
                        </span>
                        {c.should_escalate && (
                          <span className="text-xs font-semibold text-amber-400">
                            Escalating: {c.escalate_to_role}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Card Actions */}
                    <div className="pt-3 flex items-center justify-between">
                      <button
                        onClick={() => handleTogglePause(c.case_id)}
                        className={`text-xs px-2.5 py-1.5 rounded-lg border flex items-center gap-1.5 transition ${
                          c.is_paused
                            ? 'bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border-zinc-700'
                            : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border-zinc-800'
                        }`}
                      >
                        {c.is_paused ? <Play className="w-3 h-3 text-emerald-400" /> : <Pause className="w-3 h-3 text-amber-400" />}
                        <span>{c.is_paused ? 'Resume Monitoring' : 'Pause Agent'}</span>
                      </button>

                      <a
                        href={`https://portal.digivaluer.example.com/cases/${c.case_id}/workflow`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-zinc-400 hover:text-emerald-400 flex items-center gap-1 transition"
                      >
                        <span>Core Portal</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Tab 2: Pending Approval Queue */}
        {activeTab === 'approvals' && (
          <section className="space-y-6">
            <div>
              <h2 className="text-base font-semibold text-zinc-100">Pending Reminder Approval Queue</h2>
              <p className="text-xs text-zinc-400">Human-in-the-Loop review: Inspect, edit, or customize AI-generated messages before transmission</p>
            </div>

            {draftedInterventions.length === 0 ? (
              <div className="sentinel-card p-12 text-center">
                <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
                <h3 className="text-base font-medium text-zinc-200">No Pending Approvals</h3>
                <p className="text-xs text-zinc-500 mt-1">All agent-drafted reminders have been reviewed or dispatched.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {draftedInterventions.map((inv) => (
                  <div
                    key={inv.id}
                    className={`sentinel-card p-5 space-y-4 hover:border-zinc-700/80 transition-all duration-300 ${
                      highlightedCaseId === inv.case_id
                        ? 'ring-2 ring-emerald-400 shadow-xl shadow-emerald-500/20 scale-[1.005]'
                        : ''
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#1e1e24] pb-3">
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-xs font-bold text-zinc-200 bg-zinc-800/90 px-2.5 py-1 rounded border border-zinc-700">
                          {inv.case_id}
                        </span>
                        {highlightedCaseId === inv.case_id && (
                          <span className="sentinel-badge-emerald animate-pulse">
                            ⚡ Webhook Staged
                          </span>
                        )}
                        <span className="text-xs font-medium text-zinc-400">
                          Stage: <strong className="text-zinc-200">{inv.stage}</strong>
                        </span>
                        <span className="sentinel-badge-emerald">
                          Reminder #{inv.reminder_count}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-zinc-800 text-zinc-300 border border-zinc-700 flex items-center gap-1.5">
                          {inv.channel === 'SMS' ? <Smartphone className="w-3.5 h-3.5 text-blue-400" /> : <Mail className="w-3.5 h-3.5 text-emerald-400" />}
                          <span>{inv.channel}</span>
                        </span>
                        <span className="text-xs text-zinc-400">
                          To: <span className="text-zinc-200 font-medium">{inv.recipient_id}</span> ({inv.recipient_role})
                        </span>
                      </div>
                    </div>

                    {/* Message Preview */}
                    <div className="bg-[#121217] border border-[#1e1e24] rounded-lg p-4 font-mono text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed">
                      {inv.drafted_message}
                    </div>

                    {/* Action Bar */}
                    <div className="flex items-center justify-end gap-3 pt-1">
                      <button
                        onClick={() => openEditModal(inv)}
                        className="sentinel-btn-secondary text-xs"
                      >
                        <Edit3 className="w-3.5 h-3.5 text-zinc-400" />
                        <span>Edit Draft</span>
                      </button>

                      <button
                        onClick={() => handleApprove(inv.id)}
                        disabled={approvingId === inv.id}
                        className="sentinel-btn-primary text-xs"
                      >
                        <Send className="w-3.5 h-3.5" />
                        <span>{approvingId === inv.id ? 'Dispatching...' : 'Approve & Send'}</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Tab 3: Intervention History */}
        {activeTab === 'history' && (
          <section className="space-y-6">
            <div>
              <h2 className="text-base font-semibold text-zinc-100">Dispatched Intervention History</h2>
              <p className="text-xs text-zinc-400">Complete audit log of dispatched valuation notifications and delivery confirmations</p>
            </div>

            {sentInterventions.length === 0 ? (
              <div className="sentinel-card p-12 text-center text-zinc-500 text-xs">
                No dispatched interventions on record.
              </div>
            ) : (
              <div className="sentinel-card overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#121217] border-b border-[#27272a] text-zinc-400 uppercase font-semibold">
                    <tr>
                      <th className="px-4 py-3.5">ID</th>
                      <th className="px-4 py-3.5">Case</th>
                      <th className="px-4 py-3.5">Recipient</th>
                      <th className="px-4 py-3.5">Stage</th>
                      <th className="px-4 py-3.5">Channel</th>
                      <th className="px-4 py-3.5">Status</th>
                      <th className="px-4 py-3.5">Dispatched At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1e1e24] font-mono">
                    {sentInterventions.map((item) => (
                      <tr key={item.id} className="hover:bg-zinc-800/25 transition">
                        <td className="px-4 py-3 text-zinc-500">#{item.id}</td>
                        <td className="px-4 py-3 font-bold text-zinc-200">{item.case_id}</td>
                        <td className="px-4 py-3 font-sans text-zinc-300">{item.recipient_id}</td>
                        <td className="px-4 py-3 font-sans text-zinc-400">{item.stage}</td>
                        <td className="px-4 py-3 text-zinc-300">{item.channel}</td>
                        <td className="px-4 py-3">
                          <span className="sentinel-badge-emerald font-sans">
                            {item.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-zinc-400">
                          {item.sent_at ? new Date(item.sent_at).toLocaleString() : 'N/A'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </main>

      {/* Standard UI CSS Modal System */}
      {editingIntervention && (
        <div
          className="sentinel-modal-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) setEditingIntervention(null);
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
        >
          <div className="sentinel-modal-container">
            {/* Modal Header */}
            <div className="sentinel-modal-header">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shadow-sm">
                  <Edit3 className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 id="modal-title" className="text-sm font-semibold text-zinc-100">
                      Edit Reminder Notice
                    </h3>
                    <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                      {editingIntervention.case_id}
                    </span>
                    <span className="sentinel-badge-amber">
                      Reminder #{editingIntervention.reminder_count}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Stage: <span className="text-zinc-200 font-medium">{editingIntervention.stage}</span>
                  </p>
                </div>
              </div>
              <button
                onClick={() => setEditingIntervention(null)}
                className="sentinel-modal-close"
                title="Close (Esc)"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="sentinel-modal-body">
              {/* Recipient & Channel Info Bar */}
              <div className="bg-[#121217] border border-[#27272a] rounded-lg p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-zinc-400">Recipient:</span>
                  <span className="text-zinc-200 font-medium">{editingIntervention.recipient_id}</span>
                  <span className="text-zinc-500">({editingIntervention.recipient_role})</span>
                </div>
                <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-mono text-[11px] border border-zinc-700 self-start sm:self-auto">
                  {editingIntervention.channel === 'SMS' ? <Smartphone className="w-3 h-3 text-blue-400" /> : <Mail className="w-3 h-3 text-emerald-400" />}
                  <span>{editingIntervention.channel}</span>
                </div>
              </div>

              {/* Subject Input */}
              <div>
                <label className="sentinel-label">Notice Subject</label>
                <input
                  type="text"
                  value={editSubject}
                  onChange={(e) => setEditSubject(e.target.value)}
                  placeholder="Enter message subject line..."
                  className="sentinel-input font-medium"
                />
              </div>

              {/* Message Body */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="sentinel-label" style={{ marginBottom: 0 }}>Message Body</label>
                  <span className="text-[11px] font-mono text-zinc-500">
                    {editBody.length} characters • {editBody.trim().split(/\s+/).filter(Boolean).length} words
                  </span>
                </div>
                <textarea
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  rows={8}
                  placeholder="Write the reminder or follow-up notice message..."
                  className="sentinel-textarea"
                />
              </div>

              {/* Urgency Guidance Tip */}
              <div className="text-[11px] text-zinc-400 bg-amber-500/5 rounded-lg p-2.5 border border-amber-500/20 flex items-start gap-2">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                <span>
                  <strong>Tip:</strong> Keep tone context-aware and specific about missing uploads or approvals. Avoid aggressive language for external borrowers.
                </span>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="sentinel-modal-footer">
              <button
                onClick={() => setEditingIntervention(null)}
                disabled={savingEdit}
                className="sentinel-btn-secondary text-xs"
              >
                Cancel
              </button>
              <button
                onClick={() => handleSaveEdit(false)}
                disabled={savingEdit}
                className="sentinel-btn-secondary text-xs bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
              >
                {savingEdit ? 'Saving...' : 'Save Draft'}
              </button>
              <button
                onClick={() => handleSaveEdit(true)}
                disabled={savingEdit}
                className="sentinel-btn-primary text-xs"
              >
                <Send className="w-3.5 h-3.5" />
                <span>{savingEdit ? 'Processing...' : 'Save & Dispatch Now'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Real-Time Webhook Activity Modal */}
      {showWebhookModal && (
        <div
          className="sentinel-modal-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowWebhookModal(false);
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="webhook-modal-title"
        >
          <div className="sentinel-modal-container max-w-2xl">
            {/* Modal Header */}
            <div className="sentinel-modal-header">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shadow-sm">
                  <Zap className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 id="webhook-modal-title" className="text-sm font-semibold text-zinc-100">
                      DigiValuer Webhook Live Feed
                    </h3>
                    <span className={`px-2 py-0.5 text-[11px] font-semibold rounded-full border ${
                      sseConnected
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25'
                        : 'bg-zinc-800 text-zinc-400 border-zinc-700'
                    }`}>
                      {sseConnected ? 'SSE Connected' : 'Disconnected'}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Real-time ingestion pipeline from DigiValuer (<code className="text-zinc-300">mekamu_mowheel</code>)
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowWebhookModal(false)}
                className="sentinel-modal-close"
                title="Close (Esc)"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="sentinel-modal-body space-y-4">
              {/* Simulation Quick Bar */}
              <div className="bg-[#121217] border border-[#27272a] rounded-lg p-3.5 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-zinc-300 flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Webhook Simulator (Test Live Indication)</span>
                  </span>
                  <span className="text-[11px] text-zinc-500 font-mono">POST /api/v1/webhooks/digivaluer</span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed">
                  Test the real-time visual pulse, toast notifications, card highlighting, and automatic data reload by dispatching a sample payload:
                </p>
                <div className="flex flex-wrap gap-2 pt-1">
                  <button
                    onClick={() => handleSimulateWebhook('UNRESPONSIVE_PARTY')}
                    disabled={simulatingWebhook}
                    className="text-xs px-3 py-1.5 rounded-md bg-rose-950/60 text-rose-300 border border-rose-800/80 hover:bg-rose-900/60 transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <Zap className="w-3 h-3 text-rose-400" />
                    <span>{simulatingWebhook ? 'Sending...' : 'Simulate UNRESPONSIVE_PARTY'}</span>
                  </button>
                  <button
                    onClick={() => handleSimulateWebhook('STATUS_CHANGED')}
                    disabled={simulatingWebhook}
                    className="text-xs px-3 py-1.5 rounded-md bg-blue-950/60 text-blue-300 border border-blue-800/80 hover:bg-blue-900/60 transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <RefreshCw className="w-3 h-3 text-blue-400" />
                    <span>{simulatingWebhook ? 'Sending...' : 'Simulate STATUS_CHANGED'}</span>
                  </button>
                </div>
              </div>

              {/* Ingested Events Stream */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                    Live Session Ingested Events ({webhookEvents.length})
                  </h4>
                  {webhookEvents.length > 0 && (
                    <button
                      onClick={() => setWebhookEvents([])}
                      className="text-[11px] text-zinc-500 hover:text-zinc-300 underline cursor-pointer"
                    >
                      Clear Log
                    </button>
                  )}
                </div>

                {webhookEvents.length === 0 ? (
                  <div className="bg-[#121217] border border-dashed border-[#27272a] rounded-lg p-8 text-center text-xs text-zinc-500 space-y-2">
                    <Radio className="w-6 h-6 text-zinc-600 mx-auto animate-pulse" />
                    <p>No webhooks received in this browser session yet.</p>
                    <p className="text-[11px] text-zinc-600">
                      Use the simulator buttons above or send a POST request with Bearer authentication.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2.5 max-h-[280px] overflow-y-auto pr-1">
                    {webhookEvents.map((ev, idx) => (
                      <div
                        key={ev.id + idx}
                        className="bg-[#121217] border border-[#27272a] rounded-lg p-3 text-xs space-y-1.5 transition-all hover:border-zinc-700"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono border ${
                              ev.type === 'STATUS_CHANGED'
                                ? 'bg-blue-950/80 text-blue-300 border-blue-800'
                                : 'bg-rose-950/80 text-rose-300 border-rose-800'
                            }`}>
                              {ev.type}
                            </span>
                            <span className="font-mono font-bold text-zinc-200">
                              {ev.caseNumber || 'General'}
                            </span>
                          </div>
                          <span className="text-[11px] font-mono text-zinc-500">{ev.receivedAt}</span>
                        </div>
                        <p className="text-zinc-400 text-[11px] line-clamp-2">
                          {ev.data?.message || ev.data?.details || `Status transition event for ${ev.caseNumber}`}
                        </p>
                        <div className="text-[10px] text-zinc-500 font-mono flex items-center justify-between border-t border-[#1e1e24] pt-1">
                          <span>Event ID: {ev.id}</span>
                          <span className="text-emerald-400">Processed & Synced</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="sentinel-modal-footer">
              <button
                onClick={() => setShowWebhookModal(false)}
                className="sentinel-btn-secondary text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
