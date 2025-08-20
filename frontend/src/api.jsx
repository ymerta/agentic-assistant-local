// src/api.jsx
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function plan(user_input, conversationId) {
  const res = await fetch(`${API_BASE}/plan`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Conversation-Id": conversationId || "",   // <— mevcutsa gönder
    },
    body: JSON.stringify({ user_input }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data; // { conversation_id, plan_text, tool_call, tool_output, final_answer }
}

// History uçları (opsiyonel UI için)
export async function listConversations() {
  const r = await fetch(`${API_BASE}/conversations`);
  return await r.json();
}
export async function getConversation(cid) {
  const r = await fetch(`${API_BASE}/conversations/${cid}`);
  return await r.json();
}
export async function deleteConversation(cid) {
  const r = await fetch(`${API_BASE}/conversations/${cid}`, { method: "DELETE" });
  return await r.json();
}