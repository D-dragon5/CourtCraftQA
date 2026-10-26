// Run with node tests/test_panel_layout.cjs; pure layout calculations only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../static/viewer.js'), 'utf8');
function extract(start, end) {
  const from = code.indexOf(start), to = code.indexOf(end, from + start.length);
  assert.ok(from >= 0 && to > from, `Cannot extract ${start}`);
  return code.slice(from, to);
}
const constants = code.match(/^const DEFAULT_PANEL_LAYOUT=.*;$/m);
assert.ok(constants, 'Layout defaults must be defined');
const context = vm.createContext({});
vm.runInContext([
  constants[0],
  extract('function readPanelLayout(', 'let panelLayout='),
  extract('function fitQaContent(', 'function resizeCompactReview('),
  extract('function questionPair(', 'function visibleQuestionIndices('),
  extract('function navigationRefs(', 'function activateQuestion('),
  'let sectionFixtures=[];function sections(){return sectionFixtures}',
  extract('function boundedPanelFraction(', 'function updateSplitterValue('),
  'globalThis.layoutFns={readPanelLayout,fitQaContent,boundedPanelFraction,questionPair,navigationRefs,setSections:value=>{sectionFixtures=value},defaults:DEFAULT_PANEL_LAYOUT};',
].join('\n'), context);
const {readPanelLayout,fitQaContent,boundedPanelFraction,questionPair,navigationRefs,setSections,defaults} = context.layoutFns;
const plain = value => JSON.parse(JSON.stringify(value));
let checks = 0;
function same(actual, expected) { assert.deepEqual(plain(actual), plain(expected)); checks++; }
function near(actual, expected) { assert.ok(Math.abs(actual-expected)<1e-8, `${actual} != ${expected}`); checks++; }

// Only outer proportions persist; old manual content heights cannot freeze a new page.
for (const raw of [null, undefined, false, 42, 'invalid', [], {}, {columns:'0.7',media:null}, {columns:NaN,media:Infinity}]) {
  same(readPanelLayout(raw), defaults);
}
for (const raw of [{question:.3}, {answer:.4}, {question:0,answer:.4}, {question:-.1,answer:.4}, {question:.6,answer:.4}, {question:.7,answer:.4}, {question:NaN,answer:.2}]) {
  const restored=readPanelLayout(raw);
  assert.equal(restored.question,null);assert.equal(restored.answer,null);checks++;
}
const custom=readPanelLayout({columns:.7,media:.65,question:.2,answer:.5});
same(custom,{...plain(defaults),columns:.7,media:.65});
same(readPanelLayout(JSON.parse(JSON.stringify(custom))), custom);
same(readPanelLayout({columns:-100,media:100}), {...plain(defaults),columns:.15,media:.85});
same(readPanelLayout({question:.25,answer:.4,pairedQuestion:.2,pair:.6,references:.15}),defaults);
near(defaults.columns,1.12/2.12);near(defaults.media,.575);

// Default proportions survive normal windows; extreme drags retain panel minima.
near(boundedPanelFraction(defaults.columns,1200,280), defaults.columns);
near(boundedPanelFraction(defaults.media,640,105), defaults.media);
near(boundedPanelFraction(-999,1000,280),.28);
near(boundedPanelFraction(999,1000,280),.72);
near(boundedPanelFraction(-999,100,280),.45);
near(boundedPanelFraction(999,100,280),.55);
near(boundedPanelFraction(-999,0,280),.45);
near(boundedPanelFraction(999,-10,280),.55);
for(const room of [1,50,200,560,1000,4000]) {
  for(const minimum of [0,105,280]) {
    for(const desired of [-10,0,.2,.5,.8,1,10]) {
      const fraction=boundedPanelFraction(desired,room,minimum);
      assert.ok(Number.isFinite(fraction)&&fraction>=0&&fraction<=1);
      if(room>=minimum/.45) {
        assert.ok(fraction*room>=minimum-1e-8);
        assert.ok((1-fraction)*room>=minimum-1e-8);
      }
      checks++;
    }
  }
}

// All three prediction types pair real source indices, including an active lower question.
for(const type of ['action','tactic','outcome']) {
  const section={type,qa:Array.from({length:6},(_,i)=>({question:`Q${i+1}`}))};
  for(const index of [0,1,2,3,4,5])same(questionPair(section,index),[index%3,index%3+3]);
}
for(const type of ['review','other',undefined]) {
  for(let index=0;index<6;index++)same(questionPair({type,qa:new Array(6)},index),[index]);
}
for(const count of [0,1,2,3,5,7,8]) {
  for(let index=0;index<count;index++)same(questionPair({type:'action',qa:new Array(count)},index),[index]);
}
same(questionPair(undefined,0),[0]);
const fixture=(type,n)=>({type,qa:Array.from({length:n},()=>({}))});
setSections([fixture('action',6),fixture('tactic',6),fixture('outcome',6),fixture('review',3)]);
same(navigationRefs(),Array.from({length:4},(_,s)=>[0,1,2].map(q=>({s,q}))).flat());
setSections([fixture('action',5),fixture('review',6),fixture('other',6),{type:'tactic'}]);
same(navigationRefs(),[...Array.from({length:5},(_,q)=>({s:0,q})),...Array.from({length:6},(_,q)=>({s:1,q})),...Array.from({length:6},(_,q)=>({s:2,q}))]);
setSections([]);same(navigationRefs(),[]);

// Prioritize the complete question/options whenever the real answer also fits.
same(fitQaContent(500,180,200,null,100),[180,320]);
same(fitQaContent(280,180,200,null,100),[180,100]);
same(fitQaContent(0,180,200,null,100),[0,0]);
same(fitQaContent(500,180,200,.5,100),[250,250]);
same(fitQaContent(500,180,200,0,100),[32,468]);
same(fitQaContent(500,180,200,1,100),[457,43]);
near(fitQaContent(140,180,200,null,100)[0],90);
for(const room of [0,.1,1,20,50,75,90,160,260,500,1000,10000]) {
  for(const qDesired of [32,48,150,500,1e6]) {
    for(const aDesired of [43,68,180,500,1e6]) {
      for(const answerBase of [43,68,180,500]) {
        for(const manual of [null,-10,0,.2,.5,.8,1,10]) {
          const [q,a]=fitQaContent(room,qDesired,aDesired,manual,answerBase);
          assert.ok(Number.isFinite(q)&&Number.isFinite(a));
          assert.ok(q>=Math.min(32,room*.4)-1e-8);
          assert.ok(a>=Math.min(43,room*.4)-1e-8);
          near(q+a,room);
          if(manual===null&&room>=qDesired+answerBase)near(q,qDesired);
          checks++;
        }
      }
    }
  }
}
console.log(`Panel layout regression checks passed (${checks} cases)`);
