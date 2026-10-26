// Run with node tests/test_answer_whitespace.cjs; no dataset writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../static/viewer.js'), 'utf8');
const start = code.indexOf('function normalizeEditedAnswers(');
const end = code.indexOf('function cleanEditedAnswers(', start);
const normalize = vm.runInNewContext(code.slice(start, end) + '\nnormalizeEditedAnswers');
const model = {review: [
  {answer: '  Kyrie Irving把球交给Luka Dončić，P.J. Washington接应。\r\n'},
  {answer: 'Tim\t Hardaway\nJr. passes to\nCade Cunningham'},
  {answer: ' 中文\n答案  '},
  {answer: '  原有  答案\n'},
  {answer: '  源答案\n'},
], question: '  保留问题\n', other: '  保留其他字段\n'};
const baseline = {review: [{answer: '旧答案'}, {}, {}, {answer: model.review[3].answer}, {}]};
const source = {review: [{}, {}, {}, {}, {answer: model.review[4].answer}]};
assert.equal(normalize(model, baseline, source), 3);
assert.equal(model.review[0].answer, 'Kyrie Irving把球交给Luka Dončić，P.J. Washington接应。');
assert.equal(model.review[1].answer, 'Tim Hardaway Jr. passes to Cade Cunningham');
assert.equal(model.review[2].answer, '中文 答案');
assert.equal(model.review[3].answer, baseline.review[3].answer);
assert.equal(model.review[4].answer, source.review[4].answer);
assert.equal(model.question, '  保留问题\n');
assert.equal(model.other, '  保留其他字段\n');
assert.equal(normalize(model, baseline, source), 0);
console.log('Answer whitespace regression checks passed');
