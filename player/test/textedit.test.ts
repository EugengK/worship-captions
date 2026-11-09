// Run: node --experimental-strip-types --test test/textedit.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { boxLines, setBoxLines, editable } from '../src/textedit.ts'

const run = (text: string, size = 40) => ({ text, size })
const br = () => ({ text: '\n' })
const box = () => [
  { runs: [run('요한복음 15:14', 28)] },
  { runs: [run('14 '), run('너희는 내가 명하는 대로'), br(), run('행하면 곧 나의 친구라')] },
]

test('lines of a box, soft breaks included', () => {
  assert.deepEqual(boxLines(box()), ['요한복음 15:14', '14 너희는 내가 명하는 대로', '행하면 곧 나의 친구라'])
})

test('same number of lines keeps every run and style', () => {
  const p = box()
  assert.equal(setBoxLines(p, ['요한복음 15:15', '15 이제부터는', '종이라 하지 아니하리니']), true)
  assert.deepEqual(boxLines(p), ['요한복음 15:15', '15 이제부터는', '종이라 하지 아니하리니'])
  assert.equal(p[1]!.runs.length, 4) // run structure unchanged: words patched in place
  assert.equal((p[0]!.runs[0] as any).size, 28)
  assert.equal(setBoxLines(p, boxLines(p)), false)
})

test('added lines continue the last style, removed lines drop from the end', () => {
  const p = box()
  setBoxLines(p, ['제목', '첫 줄', '둘째 줄', '셋째 줄'])
  assert.deepEqual(boxLines(p), ['제목', '첫 줄', '둘째 줄', '셋째 줄'])
  assert.equal((p[1]!.runs.at(-1) as any).size, 40)
  const q = box()
  setBoxLines(q, ['제목만'])
  assert.deepEqual(boxLines(q), ['제목만'])
  assert.equal(q.length, 1)
  const r = box()
  setBoxLines(r, ['제목', '한 줄'])
  assert.deepEqual(boxLines(r), ['제목', '한 줄'])
})

test('slide-number fields and equations are not editable text', () => {
  assert.equal(editable([{ runs: [{ text: '7', field: { type: 'slidenum' } }] }]), false)
  assert.equal(editable(box()), true)
})
