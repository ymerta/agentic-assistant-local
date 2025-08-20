import { useState, useEffect } from "react";
import { plan } from "./api";
import "./App.css";

function Section({ title, children }) {
  return (
    <div className="section">
      <h3>{title}</h3>
      <div className="surface">{children}</div>
    </div>
  );
}

function EmailsList({ emails=[] }) {
  if (!emails.length) return <div className="muted">Sonuç yok.</div>;
  return (
    <ul className="list">
      {emails.map((m) => (
        <li key={m.id} className="item">
          <div className="item-title">{m.subject || "(no subject)"}</div>
          <div className="item-sub">
            {m.from || "unknown"} • {m.date || ""}
          </div>
          {m.snippet && <div className="item-snippet">{m.snippet}</div>}
        </li>
      ))}
    </ul>
  );
}

function SlotsTable({ slots=[] }) {
  if (!slots.length) return <div className="muted">Uygun blok bulunamadı.</div>;
  return (
    <div className="grid">
      {slots.map((s, i) => (
        <div key={i} className="chip">
          <span>{new Date(s.start).toLocaleString()}</span>
          <span> → </span>
          <span>{new Date(s.end).toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

function EventCard({ created }) {
  if (!created) return null;
  return (
    <div className="event-card">
      <div className="item-title">{created.summary || "Etkinlik"}</div>
      <div className="item-sub">
        {new Date(created.start).toLocaleString()} – {new Date(created.end).toLocaleString()}
      </div>
      {created.htmlLink && (
        <a className="link" href={created.htmlLink} target="_blank" rel="noreferrer">
          Google Calendar’da aç
        </a>
      )}
    </div>
  );
}

export default function App() {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const [showDebug, setShowDebug] = useState(false);
  const [convId, setConvId] = useState(localStorage.getItem("conv_id") || null);

useEffect(() => {
  let id = localStorage.getItem("conv_id");
  if (!id) {
    id = (crypto?.randomUUID && crypto.randomUUID()) ||
         Math.random().toString(36).slice(2);
    localStorage.setItem("conv_id", id);
  }
  setConvId(id);
}, []); 

const resetConversation = () => {
  const id = (crypto?.randomUUID && crypto.randomUUID()) ||
             Math.random().toString(36).slice(2);
  localStorage.setItem("conv_id", id);
  setConvId(id);
  setRes(null);     // ekranda temizle
};

const askPlan = async () => {
  if (!input.trim()) return;
  setBusy(true); setErr(""); setRes(null);
  try {
    const data = await plan(input.trim(), convId);
    // id yeni geldiyse sakla
    if (data.conversation_id && data.conversation_id !== convId) {
      localStorage.setItem("conv_id", data.conversation_id);
      setConvId(data.conversation_id);
    }
    setRes(data);
  } catch (e) {
    setErr(String(e.message || e));
  } finally { setBusy(false); }
};

// Yeni sohbet başlat butonu istersen:
const newConversation = () => {
  localStorage.removeItem("conv_id");
  setConvId(null);
  setRes(null);
  setInput("");
};
  const toolOut = res?.tool_output || {};
  const emails   = toolOut.emails;
  const slots    = toolOut.free_slots;
  const created  = toolOut.created;

  return (
    <div className="page">
      <div className="shell">
        <h1>Agentic Assistant</h1>

        <div className="card">
          <div className="row">
            <input
              className="input"
              value={input}
              onChange={(e)=>setInput(e.target.value)}
              placeholder="Örn: Son 7 gündeki önemli e-postaları özetle • Yarın 15:00 toplantı ekle • Önümüzdeki hafta 2 saatlik boş blokları öner"
            />
            <button className="btn" onClick={askPlan} disabled={busy}>
              {busy ? "Çalışıyor…" : "Gönder"}
            </button>
          </div>

          <div className="row mt">
            <label className="toggle">
              <input type="checkbox" checked={showDebug} onChange={e=>setShowDebug(e.target.checked)} />
              <span>Detayları göster (debug)</span>
            </label>

            <button className="btn ghost" onClick={resetConversation} style={{marginLeft: "auto"}}>
              Yeni konuşma
            </button>
          </div>

          <div className="small mt muted">convId: {convId}</div>
          {err && <div className="small mt">Hata: {err}</div>}
      
        </div>

        {res && (
          <div className="card mt">
            {/* ÖZET */}
            <Section title="Özet">
              <div className="final">{res.final_answer || "—"}</div>
            </Section>

            {/* TOOL TÜRÜNE GÖRE GÖRSEL SUNUM */}
            {Array.isArray(emails) && (
              <Section title="E-postalar (önemli)">
                <EmailsList emails={emails} />
              </Section>
            )}

            {Array.isArray(slots) && (
              <Section title="Uygun zaman blokları">
                <SlotsTable slots={slots} />
              </Section>
            )}

            {created && (
              <Section title="Oluşturulan etkinlik">
                <EventCard created={created} />
              </Section>
            )}

            {/* DEBUG: ham metin/JSON (isteğe bağlı) */}
            {showDebug && (
              <>
                <Section title="plan_text">
                  <pre>{res.plan_text}</pre>
                </Section>
                <Section title="tool_call">
                  <pre>{JSON.stringify(res.tool_call, null, 2)}</pre>
                </Section>
                {res.tool_output && (
                  <Section title="tool_output">
                    <pre>{JSON.stringify(res.tool_output, null, 2)}</pre>
                  </Section>
                )}
              </>
            )}
          </div>
        )}

        {!res && <div className="small mt">Henüz sonuç yok. Üstte bir örnek istek gönder.</div>}
      </div>
    </div>
  );
}