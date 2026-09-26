import { useState, useEffect } from 'react';

export interface GeminiSource {
  title: string;
  url: string;
}

export interface GeminiResult {
  verdict: 'TAK' | 'NIE' | 'NIEPEWNE';
  is_developer: boolean | null;
  confidence: 'WYSOKA' | 'ŚREDNIA' | 'NISKA';
  summary: string;
  details: string[];
  sources: GeminiSource[];
  search_queries: string[];
  raw_text: string;
  model_used?: string;
  verified_at?: string;
}

export function getStoredGeminiKey(): string {
  try {
    return typeof window !== 'undefined' ? window.localStorage.getItem('company-lab:gemini-api-key') || '' : '';
  } catch {
    return '';
  }
}

export function setStoredGeminiKey(key: string) {
  try {
    if (typeof window !== 'undefined') {
      if (key) {
        window.localStorage.setItem('company-lab:gemini-api-key', key.trim());
      } else {
        window.localStorage.removeItem('company-lab:gemini-api-key');
      }
      window.dispatchEvent(new CustomEvent('company-lab:gemini-key-change'));
    }
  } catch {}
}

export function getCachedGeminiResult(krs: string): GeminiResult | null {
  try {
    const raw = typeof window !== 'undefined' ? window.localStorage.getItem(`company-lab:gemini-result:${krs}`) : null;
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setCachedGeminiResult(krs: string, result: GeminiResult | null) {
  try {
    if (typeof window !== 'undefined') {
      if (result) {
        window.localStorage.setItem(`company-lab:gemini-result:${krs}`, JSON.stringify(result));
      } else {
        window.localStorage.removeItem(`company-lab:gemini-result:${krs}`);
      }
    }
  } catch {}
}

interface GeminiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export function GeminiKeyModal({ isOpen, onClose, onSaved }: GeminiKeyModalProps) {
  const [key, setKey] = useState(() => getStoredGeminiKey());
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (isOpen) {
      setKey(getStoredGeminiKey());
      setStatusMsg('');
      setErrorMsg('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = async () => {
    setErrorMsg('');
    setStatusMsg('');
    const trimmed = key.trim();
    if (!trimmed) {
      setErrorMsg('Wprowadź klucz API.');
      return;
    }
    if (!trimmed.startsWith('AIza')) {
      setErrorMsg('Klucz Google AI Studio powinien zaczynać się od "AIza". Sprawdź czy skopiowałeś poprawny klucz.');
      return;
    }

    setSaving(true);
    setStoredGeminiKey(trimmed);

    // Also persist to backend .env for server-side persistence
    try {
      const resp = await fetch('/api/profiles/gemini/key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: trimmed }),
      });
      if (resp.ok) {
        setStatusMsg('Klucz zapisany w przeglądarce i na serwerze (.env)!');
      } else {
        setStatusMsg('Klucz zapisany w przeglądarce.');
      }
    } catch {
      setStatusMsg('Klucz zapisany w przeglądarce.');
    } finally {
      setSaving(false);
      setTimeout(() => {
        onSaved();
        onClose();
      }, 700);
    }
  };

  const handleClear = () => {
    setStoredGeminiKey('');
    setKey('');
    setStatusMsg('Klucz został usunięty.');
    setTimeout(() => {
      onSaved();
      onClose();
    }, 600);
  };

  return (
    <div className="gemini-modal-overlay" onClick={onClose}>
      <div className="gemini-modal-card" onClick={e => e.stopPropagation()}>
        <div className="gemini-modal-header">
          <div className="gemini-sparkle-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
              <path d="M12 2L14.4 9.6L22 12L14.4 14.4L12 22L9.6 14.4L2 12L9.6 9.6L12 2Z" />
            </svg>
          </div>
          <div>
            <h3>Konfiguracja Google Gemini API</h3>
            <p className="muted">Wersja bezpłatna (Google AI Studio Free Tier)</p>
          </div>
          <button className="gemini-modal-close" onClick={onClose} aria-label="Zamknij">✕</button>
        </div>

        <div className="gemini-modal-body">
          <div className="gemini-guide-steps">
            <h4>Jak uzyskać darmowy klucz API (bez podawania karty):</h4>
            <ol>
              <li>
                Wejdź na stronę:{' '}
                <a
                  href="https://aistudio.google.com/"
                  target="_blank"
                  rel="noreferrer"
                  className="gemini-link"
                >
                  https://aistudio.google.com/ ↗
                </a>
              </li>
              <li>Zaloguj się swoim zwykłym kontem Google (Gmail).</li>
              <li>Kliknij niebieski przycisk <strong>„Get API key”</strong> w menu.</li>
              <li>Wybierz <strong>„Create API key”</strong> ➔ <strong>„Create API key in new project”</strong>.</li>
              <li>Skopiuj wygenerowany klucz zaczynający się od <code>AIzaSy...</code> i wklej go poniżej.</li>
            </ol>
            <div className="gemini-free-badge">
              ✓ <strong>100% bezpłatny plan:</strong> do 15 zapytań na minutę i 1500 na dobę bez opłat i bez wymogu karty.
            </div>
          </div>

          <div className="gemini-input-group">
            <label htmlFor="gemini-key-input">Twój klucz Gemini API:</label>
            <input
              id="gemini-key-input"
              type="password"
              placeholder="Wklej klucz: AIzaSy..."
              value={key}
              onChange={e => setKey(e.target.value)}
              className="gemini-key-field"
            />
          </div>

          {errorMsg && <div className="gemini-error-msg">{errorMsg}</div>}
          {statusMsg && <div className="gemini-success-msg">{statusMsg}</div>}
        </div>

        <div className="gemini-modal-actions">
          {getStoredGeminiKey() && (
            <button type="button" className="text-button danger-text" onClick={handleClear}>
              Usuń klucz
            </button>
          )}
          <button type="button" className="text-button" onClick={onClose}>
            Anuluj
          </button>
          <button
            type="button"
            className="gemini-save-button"
            onClick={handleSave}
            disabled={saving || !key.trim()}
          >
            {saving ? 'Zapisywanie…' : 'Zapisz klucz'}
          </button>
        </div>
      </div>
    </div>
  );
}

interface GeminiVerificationProps {
  krs: string;
  collection: string;
  companyName: string;
  localVerification: 'confirmed' | 'rejected' | null;
  onApplyVerification?: (status: 'confirmed' | 'rejected' | null) => void;
  initialDbVerification?: any;
}

export function GeminiVerification({
  krs,
  collection,
  companyName,
  localVerification,
  onApplyVerification,
  initialDbVerification,
}: GeminiVerificationProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [hasKey, setHasKey] = useState(() => Boolean(getStoredGeminiKey()));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GeminiResult | null>(() => getCachedGeminiResult(krs));

  // Check key on mount & listen to changes
  useEffect(() => {
    const checkKey = async () => {
      const stored = getStoredGeminiKey();
      if (stored) {
        setHasKey(true);
        return;
      }
      try {
        const resp = await fetch('/api/profiles/gemini/status');
        if (resp.ok) {
          const data = await resp.json();
          if (data.has_key) setHasKey(true);
        }
      } catch {}
    };
    checkKey();

    const handleKeyChange = () => {
      setHasKey(Boolean(getStoredGeminiKey()));
    };
    window.addEventListener('company-lab:gemini-key-change', handleKeyChange);
    return () => window.removeEventListener('company-lab:gemini-key-change', handleKeyChange);
  }, []);

  // Sync cache or DB verification if KRS changes
  useEffect(() => {
    const cached = getCachedGeminiResult(krs);
    if (cached) {
      setResult(cached);
    } else if (initialDbVerification && (initialDbVerification.summary || initialDbVerification.details?.length)) {
      setResult({
        verdict: initialDbVerification.verdict || (initialDbVerification.status === 'confirmed' ? 'TAK' : 'NIE'),
        is_developer: initialDbVerification.status === 'confirmed' ? true : initialDbVerification.status === 'rejected' ? false : null,
        confidence: initialDbVerification.confidence || 'ŚREDNIA',
        summary: initialDbVerification.summary || '',
        details: initialDbVerification.details || [],
        sources: initialDbVerification.sources || [],
        search_queries: [],
        raw_text: initialDbVerification.raw_text || '',
        model_used: initialDbVerification.model_used,
        verified_at: initialDbVerification.updated_at ? new Date(initialDbVerification.updated_at).toLocaleString('pl-PL') : undefined,
      });
    } else {
      setResult(null);
    }
    setError(null);
  }, [krs, initialDbVerification]);

  const handleVerify = async () => {
    setError(null);
    setLoading(true);

    const key = getStoredGeminiKey();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (key) {
      headers['X-Gemini-Key'] = key;
    }

    try {
      const resp = await fetch(`/api/profiles/${krs}/verify-gemini?collection=${collection}`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ api_key: key || undefined }),
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({ detail: 'Błąd serwera' }));
        const msg = errData.detail || `Błąd HTTP ${resp.status}`;
        if (resp.status === 400 && msg.includes('Brak klucza')) {
          setModalOpen(true);
        }
        throw new Error(msg);
      }

      const data: GeminiResult = await resp.json();
      data.verified_at = new Date().toLocaleString('pl-PL');
      setResult(data);
      setCachedGeminiResult(krs, data);

      // Automatically apply verdict to qualification!
      if (data.is_developer === true) {
        onApplyVerification?.('confirmed');
      } else if (data.is_developer === false) {
        onApplyVerification?.('rejected');
      }
    } catch (err: any) {
      setError(err.message || 'Wystąpił błąd podczas weryfikacji w Gemini.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="gemini-overview-container">
      <div className="gemini-overview-card">
        {/* Card Header */}
        <div className="gemini-overview-header">
          <div className="gemini-brand-badge">
            <span className="gemini-sparkle-glow" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M12 2L14.4 9.6L22 12L14.4 14.4L12 22L9.6 14.4L2 12L9.6 9.6L12 2Z" />
              </svg>
            </span>
            <span className="gemini-header-title">Przegląd od AI</span>
            <span className="gemini-model-badge">Gemini 2.0 Flash · Google Search</span>
          </div>

          <div className="gemini-header-actions">
            <button
              type="button"
              className="gemini-config-btn"
              onClick={() => setModalOpen(true)}
              title="Konfiguracja klucza Gemini API"
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="7.5" cy="15.5" r="5.5" />
                <path d="m21 2-9.6 9.6M15.5 7.5l3 3M18.5 4.5l2 2" />
              </svg>
              {hasKey ? 'Klucz aktywny' : 'Skonfiguruj klucz API'}
            </button>
          </div>
        </div>

        {/* Card Content */}
        <div className="gemini-overview-content">
          {!result && !loading && (
            <div className="gemini-empty-state">
              <p>
                Sprawdź w czasie rzeczywistym, czy firma <strong>{companyName}</strong> jest deweloperem,
                wykorzystując model <strong>Google Gemini</strong> z przeszukiwaniem sieci <em>(Google Search Grounding)</em>.
              </p>
              <div className="gemini-action-row">
                <button
                  type="button"
                  className="gemini-primary-btn"
                  onClick={handleVerify}
                  disabled={loading}
                >
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
                    <path d="M12 2L14.4 9.6L22 12L14.4 14.4L12 22L9.6 14.4L2 12L9.6 9.6L12 2Z" />
                  </svg>
                  Sprawdź w Google AI (Gemini)
                </button>
                {!hasKey && (
                  <span className="gemini-hint-text">
                    Wymaga bezpłatnego klucza (bez karty) —{' '}
                    <button type="button" className="gemini-link-btn" onClick={() => setModalOpen(true)}>
                      pobierz tutaj
                    </button>
                  </span>
                )}
              </div>
            </div>
          )}

          {loading && (
            <div className="gemini-loading-state">
              <div className="gemini-spinner" />
              <p>Przeszukiwanie sieci i analiza przez Google Gemini…</p>
              <span className="muted">Weryfikacja inwestycji, stron www i rejestrów gospodarczych…</span>
            </div>
          )}

          {error && (
            <div className="gemini-error-box">
              <p><strong>Błąd weryfikacji:</strong> {error}</p>
              <div className="gemini-error-actions">
                <button type="button" className="gemini-small-btn" onClick={handleVerify}>
                  Spróbuj ponownie
                </button>
                <button type="button" className="gemini-small-btn" onClick={() => setModalOpen(true)}>
                  Zmień klucz API
                </button>
              </div>
            </div>
          )}

          {result && !loading && (
            <div className="gemini-result-view">
              {/* Verdict Banner */}
              <div className={`gemini-verdict-banner verdict-${result.verdict.toLowerCase()}`}>
                <div className="gemini-verdict-text">
                  <span className="gemini-verdict-tag">
                    {result.verdict === 'TAK' ? '✓ TAK, DEWELOPER' : result.verdict === 'NIE' ? '✕ TO NIE DEWELOPER' : '? NIEJEDNOZNACZNE'}
                  </span>
                  <span className="gemini-verdict-highlight">
                    {result.verdict === 'TAK'
                      ? `Tak, ${companyName} prowadzi działalność deweloperską.`
                      : result.verdict === 'NIE'
                      ? `Firma ${companyName} nie prowadzi działalności deweloperskiej.`
                      : `Brak jednoznacznego potwierdzenia działalności deweloperskiej.`}
                  </span>
                </div>
                {result.sources.length > 0 && (
                  <span className="gemini-source-count-badge" title="Liczba zweryfikowanych źródeł Google">
                    {result.sources.length} {result.sources.length === 1 ? 'źródło' : result.sources.length < 5 ? 'źródła' : 'źródeł'}
                  </span>
                )}
              </div>

              {/* Summary */}
              {result.summary && (
                <p className="gemini-summary-paragraph">{result.summary}</p>
              )}

              {/* Details list */}
              {result.details && result.details.length > 0 && (
                <div className="gemini-details-list">
                  <ul>
                    {result.details.map((item, idx) => (
                      <li key={idx}>
                        <span className="gemini-bullet-point" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Sources */}
              {result.sources && result.sources.length > 0 && (
                <div className="gemini-sources-section">
                  <span className="gemini-sources-title">Źródła wyszukiwania Google:</span>
                  <div className="gemini-sources-chips">
                    {result.sources.map((src, idx) => (
                      <a
                        key={idx}
                        href={src.url}
                        target="_blank"
                        rel="noreferrer"
                        className="gemini-source-chip"
                        title={src.url}
                      >
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <circle cx="12" cy="12" r="10" />
                          <line x1="2" y1="12" x2="22" y2="12" />
                          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                        </svg>
                        <span>{src.title || src.url}</span>
                        <span className="gemini-arrow">↗</span>
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {/* Action Bar */}
              <div className="gemini-action-bar">
                <div className="gemini-apply-actions">
                  <span className="gemini-apply-label">Decyzja:</span>
                  <button
                    type="button"
                    className={`gemini-apply-btn confirm ${localVerification === 'confirmed' ? 'active' : ''}`}
                    onClick={() => onApplyVerification?.('confirmed')}
                  >
                    ✓ Potwierdź jako dewelopera
                  </button>
                  <button
                    type="button"
                    className={`gemini-apply-btn reject ${localVerification === 'rejected' ? 'active' : ''}`}
                    onClick={() => onApplyVerification?.('rejected')}
                  >
                    ✕ Odrzuć (Nie deweloper)
                  </button>
                  {localVerification === 'rejected' && (
                    <span className="gemini-apply-note rejected-note">
                      ✓ Zastosowano: firma oznaczona w aplikacji jako „✕ Nie deweloper”.
                    </span>
                  )}
                  {localVerification === 'confirmed' && (
                    <span className="gemini-apply-note confirmed-note">
                      ✓ Zastosowano: firma oznaczona jako „✓ Deweloper”.
                    </span>
                  )}
                </div>

                <div className="gemini-meta-actions">
                  <button
                    type="button"
                    className="gemini-refresh-btn"
                    onClick={handleVerify}
                    title="Ponów sprawdzenie w sieci"
                  >
                    ↻ Odśwież analizę AI
                  </button>
                  {result.verified_at && (
                    <span className="gemini-timestamp">Sprawdzono: {result.verified_at}</span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <GeminiKeyModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={() => setHasKey(Boolean(getStoredGeminiKey()))}
      />
    </div>
  );
}
