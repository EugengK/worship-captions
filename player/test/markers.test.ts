// Run: node --experimental-strip-types --test test/markers.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { autoplayIds, notesMarker, translationStates } from '../src/markers.ts'

test('notes markers', () => {
  assert.equal(notesMarker('설교 시작 [번역 ON]'), true)
  assert.equal(notesMarker('[번역 off] 찬송'), false)
  assert.equal(notesMarker('[ 번역 ON ]'), true)
  assert.equal(notesMarker('[번역 ON] 실수로 [번역 OFF]'), false)
  assert.equal(notesMarker('그냥 메모'), null)
})

test('markers carry forward; off before the first marker', () => {
  assert.deepEqual(translationStates([null, false, null, true, null, null, false, null]),
    [false, false, false, true, true, true, false, false])
  assert.deepEqual(translationStates([null, null]), [true, true]) // no markers: always on
})

test('audio that PowerPoint starts by itself', () => {
  const auto = '<p:cTn id="5" presetID="1" presetClass="mediacall" presetSubtype="0" fill="hold" nodeType="afterEffect"><p:stCondLst/><p:childTnLst><p:cmd type="call" cmd="playFrom(0.0)"><p:cBhvr><p:cTn id="6"/><p:tgtEl><p:spTgt spid="2"/></p:tgtEl></p:cBhvr></p:cmd></p:childTnLst></p:cTn>'
  const click = auto.replace('afterEffect', 'clickEffect').replace('spid="2"', 'spid="7"')
  assert.deepEqual([...autoplayIds(auto + click)], ['2'])
})

test('prepared caption file', async () => {
  const { parseCaptionFile, mismatchedSlides, liveTranslation } = await import('../src/markers.ts')
  const f = parseCaptionFile(JSON.stringify({
    title: '2026-11-01',
    slides: { '38': { ko: '교독문 1 시편 1편', en: 'Blessed is the one\nwho does not walk', th: '' }, x: { en: 'bad' }, '0': { en: 'bad' } },
  }))
  assert.equal(f.title, '2026-11-01')
  assert.deepEqual([...f.slides.keys()], [38])
  assert.deepEqual(f.slides.get(38), { en: 'Blessed is the one\nwho does not walk' }) // empty th dropped, ko is a check
  assert.deepEqual(mismatchedSlides(f, () => '교독문 1  시편 1편 복 있는 사람은'), [])
  assert.deepEqual(mismatchedSlides(f, () => '찬송 300장'), [38])
  assert.throws(() => parseCaptionFile('{"x":1}'))
  assert.equal(liveTranslation(true, null, true), false) // prepared captions: no live cost
  assert.equal(liveTranslation(true, true, true), true) // unless the notes ask for it
  assert.equal(liveTranslation(false, null, false), false)
})
