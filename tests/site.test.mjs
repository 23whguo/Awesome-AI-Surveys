import {test} from 'node:test';
import assert from 'node:assert/strict';
import {filterRecords,sortRecords,escapeHTML,safeURL,csvCell} from '../site/assets/catalog.js';
import {searchCatalogMatches} from '../site/assets/upstream/catalog-search.js';

const records=[
 {id:'a',title:'Agent survey',year:2026,date:null,category:'agents',topic:'memory',tags:{methods:['rag']},sources:['arxiv'],citations:null,stars:null},
 {id:'b',title:'Vision survey',year:2026,date:'2026-02-01',category:'vision',tags:{methods:['deep']},sources:['venue'],citations:0,stars:0},
 {id:'c',title:'Memory review',year:2025,date:'2025-05-02',category:'agents',topic:'memory',tags:{methods:['rag']},sources:['arxiv'],citations:15,stars:2,code_url:'https://github.com/example/repo'}
];
test('unknown metrics stay after real zero; year-only follows dated records',()=>{
 assert.deepEqual(sortRecords(records,'citations').map(p=>p.id),['c','b','a']);
 assert.deepEqual(sortRecords(records,'time').map(p=>p.id),['b','a','c']);
});
test('combined facets, saved and followed use stable identities',()=>{
 assert.deepEqual(filterRecords(records,{category:'agents',tag:'rag',saved:true},null,['c']).map(p=>p.id),['c']);
 assert.equal(filterRecords(records,{followed:true},null,[],[]).length,0);
 assert.deepEqual(filterRecords(records,{code:true}).map(p=>p.id),['c']);
 assert.deepEqual(filterRecords(records,{source:'venue',year:'2026'}).map(p=>p.id),['b']);
});
test('search preserves partial-match metadata and handles CJK category names',()=>{
 const corpus=[{key:'a',name:'Agent Memory Survey',description:'',categories:['智能体与多智能体'],publisher:'arXiv',languages:[],modality:[],source:[]},{key:'b',name:'Agent Vision Survey',description:'',categories:['视觉'],publisher:'arXiv',languages:[],modality:[],source:[]}];
 const hits=searchCatalogMatches(corpus,'agent memory');
 assert.equal(hits[0].record.key,'a'); assert.equal(hits[0].missing.length,0);
 assert.ok(hits.some(h=>h.record.key==='b'&&h.missing.length));
 assert.equal(searchCatalogMatches(corpus,'智能体')[0].record.key,'a');
});
test('escape untrusted metadata and neutralize spreadsheet formula cells',()=>{
 assert.equal(escapeHTML('<img src=x onerror="x">'),'&lt;img src=x onerror=&quot;x&quot;&gt;');
 assert.equal(safeURL('javascript:alert(1)'),'');assert.equal(safeURL('https://user@x.org'),'');
 assert.equal(csvCell('=HYPERLINK("x")'),'"\'=HYPERLINK(""x"")"');
});
