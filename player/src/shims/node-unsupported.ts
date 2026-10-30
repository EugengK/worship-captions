// node:fs, node:stream/promises, node:zlib are used only when saving or editing a deck,
// which the player never does.
const fail = (name: string) => () => {
  throw new Error(`${name} is not available in the worship player`)
}
export const deflateSync = fail('deflateSync')
export const createWriteStream = fail('createWriteStream')
export const pipeline = fail('pipeline')
export default {}
