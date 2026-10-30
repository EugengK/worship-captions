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
