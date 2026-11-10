// SPDX-License-Identifier: AGPL-3.0-only
// Pure catalog operations shared by the interface and the browser checks.
export function filterRecords(records, state, matchedIds = null, saved = [], followed = []) {
  return records.filter(p => (!matchedIds || matchedIds.has(p.id)) &&
    (!state.category || p.category === state.category) && (!state.topic || p.topic === state.topic) &&
    (!state.year || String(p.year) === state.year) && (!state.venue || p.venue === state.venue) &&
    (!state.source || p.sources.includes(state.source)) && (!state.type || p.review_type === state.type) &&
    (!state.tag || Object.values(p.tags).flat().includes(state.tag)) &&
    (!state.code || !!p.code_url) && (!state.saved || saved.includes(p.id)) &&
    (!state.followed || followed.includes(p.category)));
}
export function sortRecords(records, sort, relevance = null) {
  return [...records].sort((a,b) => {
    if (sort === 'relevance' && relevance) return relevance.get(a.id) - relevance.get(b.id);
    if (sort === 'citations' || sort === 'stars') {
      const key = sort === 'stars' ? 'stars' : 'citations';
      if ((a[key] == null) !== (b[key] == null)) return a[key] == null ? 1 : -1;
      if ((a[key] ?? 0) !== (b[key] ?? 0)) return (b[key] ?? 0) - (a[key] ?? 0);
    }
    return (b.year ?? 0) - (a.year ?? 0) || (b.date || '').localeCompare(a.date || '') || a.title.localeCompare(b.title) || a.id.localeCompare(b.id);
  });
}
export function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
export function safeURL(value) {
  try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username ? u.href : ''; }
  catch { return ''; }
}
export function csvCell(value) {
  let s = String(value ?? '');
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return '"' + s.replace(/"/g, '""') + '"';
}
